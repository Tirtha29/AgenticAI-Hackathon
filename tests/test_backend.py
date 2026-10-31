import json
import unittest
from unittest.mock import Mock, patch

from backend.agents.reporting_agent import build_report_parser
from backend.agents.correlation_agent import (
    SCORING_WEIGHTS,
    _score_with_groq,
    _weighted_score,
    build_cause_scoring_parser,
)
from backend.agents.web_research_agent import has_local_rule_match, web_research_agent
from backend.common.classes.api import TelemetryIn
from backend.common.classes.correlation import CauseScoreFactors, ProbableCause
from backend.common.rules import BASE_RULES, CAUSE_RULES, FACT_CATALOG
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

    def test_pydantic_correlation_parser_and_weighted_score(self):
        parsed = build_cause_scoring_parser().parse(
            '{"assessments":[{"rule_id":"NET-01","factors":'
            '{"rule_match":1,"cross_metric":0.8,"severity":0.7,'
            '"history":0.5,"topology":0.5,"client_confirmation":0.5}}]}'
        )
        self.assertEqual(parsed.assessments[0].rule_id, "NET-01")
        score = _weighted_score(parsed.assessments[0].factors)
        expected = (
            1.0 * SCORING_WEIGHTS["rule_match"]
            + 0.8 * SCORING_WEIGHTS["cross_metric"]
            + 0.7 * SCORING_WEIGHTS["severity"]
            + 0.5 * SCORING_WEIGHTS["history"]
            + 0.5 * SCORING_WEIGHTS["topology"]
            + 0.5 * SCORING_WEIGHTS["client_confirmation"]
        )
        self.assertAlmostEqual(score, expected)
        with self.assertRaises(ValueError):
            CauseScoreFactors(
                rule_match=1.1,
                cross_metric=0.8,
                severity=0.7,
                history=0.5,
                topology=0.5,
                client_confirmation=0.5,
            )

    def test_groq_cause_scores_are_weighted_and_attached_to_report_candidate(self):
        from langchain_core.messages import AIMessage
        from langchain_core.runnables import RunnableLambda

        model = RunnableLambda(lambda _: AIMessage(content=(
            '{"assessments":[{"rule_id":"NET-01","factors":'
            '{"rule_match":1,"cross_metric":0.8,"severity":0.7,'
            '"history":0.5,"topology":0.5,"client_confirmation":0.5}}]}'
        )))
        candidate = ProbableCause(
            rule_id="NET-01",
            cause="Link congestion",
            probability=0.93,
            evidence=["link utilization is elevated"],
            recommended_action="Review congestion",
        )
        scored, web_candidates = _score_with_groq(
            model, [candidate], {"severity": "critical"}, {}
        )
        self.assertAlmostEqual(scored[0].probability, 0.755)
        self.assertEqual(scored[0].score_breakdown.rule_match, 1)
        self.assertEqual(web_candidates, [])

    def test_tavily_runs_only_when_abnormal_metrics_have_no_local_rule_match(self):
        state = {
            "telemetry": {"metrics": {"bandwidth_mbps": 50}},
            "performance": {"severity": "warning"},
        }
        self.assertFalse(has_local_rule_match(state["telemetry"]["metrics"]))
        response = Mock()
        response.json.return_value = {"results": [{
            "title": "Network latency troubleshooting",
            "url": "https://example.org/network-latency",
            "content": "Check queue depth and path changes.",
            "score": 0.91,
        }]}
        with patch("backend.agents.web_research_agent.httpx.post", return_value=response) as post:
            result = web_research_agent(state, api_key="test-key")["web_research"]
        self.assertEqual(result["status"], "searched")
        self.assertEqual(result["sources"][0]["url"], "https://example.org/network-latency")
        self.assertEqual(post.call_args.kwargs["json"]["max_results"], 5)

    def test_tavily_skips_when_a_local_rule_matches(self):
        state = {
            "telemetry": {"metrics": {
                "interface_errors": 120,
                "packet_loss_pct": 12,
            }},
            "performance": {"severity": "critical"},
        }
        with patch("backend.agents.web_research_agent.httpx.post") as post:
            result = web_research_agent(state, api_key="test-key")["web_research"]
        self.assertTrue(has_local_rule_match(state["telemetry"]["metrics"]))
        self.assertEqual(result["status"], "local_match_found")
        post.assert_not_called()

    def test_groq_web_hypotheses_require_and_preserve_tavily_citations(self):
        from langchain_core.messages import AIMessage
        from langchain_core.runnables import RunnableLambda

        model = RunnableLambda(lambda _: AIMessage(content=(
            '{"assessments":[],"web_suggestions":[{"cause":"Possible queue congestion",'
            '"source_ids":[0],"factors":{"rule_match":0.8,"cross_metric":0.9,'
            '"severity":0.9,"history":0.5,"topology":0.5,'
            '"client_confirmation":0.5},"recommended_action":"Check queue counters '
            'and compare with the device vendor guidance before changing settings."}]}'
        )))
        research = {
            "status": "searched",
            "sources": [{
                "source_id": 0,
                "title": "Queue diagnostics",
                "url": "https://example.org/queues",
                "snippet": "Review queue depth and drops.",
                "relevance": 0.9,
            }],
        }
        _, candidates = _score_with_groq(model, [], {}, research)
        self.assertEqual(candidates[0].rule_id, "WEB-01")
        self.assertEqual(candidates[0].sources[0].url, "https://example.org/queues")

    def test_diagnostic_rule_set_has_broader_metric_and_correlation_coverage(self):
        self.assertGreaterEqual(len(BASE_RULES), 10)
        self.assertGreaterEqual(len(CAUSE_RULES), 20)
        self.assertGreater(len(FACT_CATALOG), 2000)

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
        self.assertEqual(report["scoring_method"], "static_fallback")
        self.assertEqual(sum(report["scoring_weights"].values()), 1)

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
            {"device_id": "RTR1", "device_type": "router"},
            [{"metrics": {"latency_ms": 20}}],
            device_inventory=[
                {"device_id": "RTR1", "device_type": "router", "neighbors_json": '["SW2"]'},
                {"device_id": "SW2", "device_type": "switch", "neighbors_json": "[]"},
            ],
        )
        self.assertEqual(report["historical_context"][0]["two_hour_average"], 20)
        self.assertEqual(report["nearby_connections"][0]["device_id"], "SW2")
        self.assertGreater(report["nearby_connections"][0]["probability"], 0.45)
        self.assertEqual(report["nearby_connections"][0]["connection_hops"], 1)

    def test_catalog_contains_more_than_one_thousand_context_facts(self):
        self.assertEqual(len(FACT_CATALOG), 2640)

    def test_csv_inventory_parsing(self):
        devices = parse_inventory(
            b"device_id,name,device_type,connected_to\nSW1,Core Switch,switch,RTR1;FW1\n",
            "devices.csv",
        )
        self.assertEqual(devices[0]["device_id"], "SW1")
        self.assertEqual(devices[0]["device_type"], "switch")
        self.assertEqual(json.loads(devices[0]["neighbors_json"]), ["FW1", "RTR1"])

    def test_json_inventory_parsing_uses_topology_without_device_coordinates(self):
        inventory = [{
            "device_id": "R1",
            "device_type": "router",
            "connected_to": ["SW1"],
        }]
        devices = parse_inventory(json.dumps(inventory).encode(), "devices.json")
        self.assertEqual(devices[0]["device_id"], "R1")
        self.assertEqual(json.loads(devices[0]["neighbors_json"]), ["SW1"])
        self.assertNotIn("latitude", devices[0])


if __name__ == "__main__":
    unittest.main()
