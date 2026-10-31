import json
import unittest

from backend.agents.reporting_agent import build_report_parser
from backend.common.classes.api import TelemetryIn
from backend.common.rules import FACT_CATALOG
from backend.graph import run_workflow
from backend.main import normalize_payload, parse_inventory


class TelemetryTests(unittest.TestCase):
    def test_metric_aliases_normalize_to_canonical_units(self):
        event = normalize_payload(TelemetryIn(
            device_id="SW_CAMPUS_1",
            metrics={"cpu_utilization": 0.5, "latency_s": 0.2, "queue_drops": 4},
        ))
        self.assertEqual(event["metrics"], {
            "cpu_utilization_pct": 50.0,
            "latency_ms": 200.0,
            "queue_drops": 4.0,
        })
        self.assertEqual(event["units"]["latency_ms"], "ms")

    def test_client_selected_bandwidth_unit_is_converted(self):
        event = normalize_payload(TelemetryIn(
            device_id="RTR_CAMPUS_1",
            metrics={"bandwidth": 2.5},
            units={"bandwidth": "Gbps"},
        ))
        self.assertEqual(event["metrics"]["bandwidth_mbps"], 2500)
        self.assertEqual(event["units"]["bandwidth_mbps"], "Mbps")
        self.assertEqual(event["source_units"]["bandwidth_mbps"], "Gbps")

    def test_pydantic_output_parser_validates_report_narrative(self):
        parsed = build_report_parser().parse('{"summary":"Insufficient information.","limitations":"Static thresholds only."}')
        self.assertEqual(parsed.summary, "Insufficient information.")

    def test_hardware_fault_is_critical(self):
        event = normalize_payload(TelemetryIn(
            device_id="SW_CAMPUS_1",
            metrics={"packet_loss_pct": 20, "latency_ms": 700, "queue_drops": 8000},
        ))
        report = run_workflow(event, {"device_type": "switch"})
        self.assertEqual(report["severity"], "critical")

    def test_graph_returns_ranked_causes_and_canonical_units(self):
        event = normalize_payload(TelemetryIn(
            device_id="SW_CAMPUS_1",
            metrics={
                "cpu_utilization_pct": 99.9,
                "link_utilization_pct": 100,
                "packet_loss_pct": 22,
                "latency_ms": 720,
                "queue_drops": 8500,
                "interface_errors": 120,
                "firewall_drops": 300,
            },
        ))
        report = run_workflow(event, {"device_type": "switch"})
        self.assertEqual(report["severity"], "critical")
        self.assertTrue(report["probable_causes"])
        self.assertEqual(report["units"]["latency_ms"], "ms")
        self.assertTrue(report["human_review"]["status"] == "pending")
        self.assertEqual(report["probable_causes"][0]["probability"], 0.97)

    def test_answered_high_confidence_case_is_ranked_and_verified(self):
        event = normalize_payload(TelemetryIn(
            device_id="RTR_CAMPUS_1",
            metrics={
                "cpu_utilization_pct": 99.9,
                "packet_loss_pct": 22,
                "interface_errors": 120,
            },
        ))
        report = run_workflow(
            event,
            {"device_type": "router", "latitude": 47.6, "longitude": -122.3, "location_known": True},
            human_answers={
                "utm_alerts": False,
                "recent_firewall_change": False,
                "interface_errors_present": True,
            },
        )
        self.assertEqual(report["conclusion"], "probable_causes_ranked")
        self.assertGreaterEqual(report["probable_causes"][0]["probability"], 0.9)
        self.assertEqual(report["human_questions"], [])

    def test_utm_rule_uses_client_information_before_high_confidence_claim(self):
        event = normalize_payload(TelemetryIn(
            device_id="FW1",
            metrics={"firewall_drops": 300},
        ))
        waiting = run_workflow(event, {"device_type": "firewall"})
        self.assertEqual(waiting["human_review"]["status"], "pending")
        self.assertIn("policy change", waiting["human_questions"][0])

        answered = run_workflow(
            event,
            {"device_type": "firewall"},
            human_answers={"recent_firewall_change": True, "utm_alerts": True},
        )
        self.assertEqual(answered["conclusion"], "probable_causes_ranked")
        self.assertEqual(answered["probable_causes"][0]["rule_id"], "UTM-01")
        self.assertEqual(answered["probable_causes"][0]["probability"], 0.94)

    def test_graph_includes_history_and_adjacent_device_context(self):
        event = normalize_payload(TelemetryIn(
            device_id="RTR1",
            metrics={"latency_ms": 300},
        ))
        report = run_workflow(
            event,
            {
                "device_type": "router",
                "latitude": 47.6,
                "longitude": -122.3,
                "location_known": True,
            },
            [{"metrics": {"latency_ms": 20}}],
            geo_lookup=lambda *_: [{
                "device_id": "SW2",
                "device_type": "switch",
                "latitude": 47.61,
                "longitude": -122.31,
                "distance_km": 0.9,
            }],
        )
        self.assertEqual(report["historical_context"][0]["two_hour_average"], 20)
        self.assertEqual(report["blast_radius"][0]["device_id"], "SW2")
        self.assertGreater(report["blast_radius"][0]["probability"], 0.45)

    def test_catalog_contains_more_than_one_thousand_context_facts(self):
        self.assertEqual(len(FACT_CATALOG), 1320)

    def test_csv_inventory_parsing(self):
        devices = parse_inventory(
            b"device_id,latitude,longitude,device_type\nSW1,47.6,-122.3,switch\n",
            "devices.csv",
        )
        self.assertEqual(devices[0]["device_id"], "SW1")
        self.assertEqual(devices[0]["device_type"], "switch")

    def test_geojson_inventory_parsing(self):
        inventory = {
            "type": "FeatureCollection",
            "features": [{
                "type": "Feature",
                "properties": {"device_id": "R1", "device_type": "router"},
                "geometry": {"type": "Point", "coordinates": [-122.3, 47.6]},
            }],
        }
        devices = parse_inventory(json.dumps(inventory).encode(), "devices.geojson")
        self.assertEqual(devices[0]["latitude"], 47.6)
        self.assertEqual(devices[0]["longitude"], -122.3)


if __name__ == "__main__":
    unittest.main()
