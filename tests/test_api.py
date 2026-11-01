import json
import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.main as main


class FakePipeline:
    def __init__(self):
        self.commands = []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def execute_command(self, *args):
        self.commands.append(args)

    def hset(self, *args):
        self.commands.append(args)

    async def execute(self):
        return []


class FakeRedis:
    def __init__(self):
        self.deleted_keys = []

    def pipeline(self, **_kwargs):
        return FakePipeline()

    async def delete(self, *keys):
        self.deleted_keys.extend(keys)
        return len(keys)

    async def ping(self):
        return True

    async def exists(self, _key):
        return 1

    async def xadd(self, *_args, **_kwargs):
        return "1-0"


class ApiTests(unittest.TestCase):
    def test_iit_bhubaneswar_demo_replaces_inventory_with_15_synthetic_devices(self):
        with tempfile.TemporaryDirectory() as directory:
            fake_redis = FakeRedis()
            with patch.object(main, "DB_PATH", f"{directory}/netcoop.db"), \
                    patch.object(main, "redis_client", fake_redis), \
                    TestClient(main.app) as client:
                upload = client.post(
                    "/devices/upload",
                    files={"file": ("devices.csv", b"device_id,latitude,longitude\nOLD_DEVICE,37.7,-122.4\n", "text/csv")},
                )
                self.assertEqual(upload.status_code, 200)

                demo = client.post("/devices/demo/iit-bhubaneswar")
                self.assertEqual(demo.status_code, 200)
                self.assertEqual(demo.json()["site"], "IIT Bhubaneswar")
                self.assertTrue(demo.json()["synthetic"])
                self.assertEqual(demo.json()["uploaded"], 15)
                self.assertIn(main.GEO_KEY, fake_redis.deleted_keys)
                self.assertIn(main.DEVICE_DETAILS_KEY, fake_redis.deleted_keys)

                devices = client.get("/overview").json()["devices"]
                self.assertEqual(len(devices), 15)
                self.assertNotIn("OLD_DEVICE", {device["device_id"] for device in devices})
                self.assertTrue(all(20.14 < device["latitude"] < 20.16 for device in devices))
                self.assertTrue(all(85.67 < device["longitude"] < 85.69 for device in devices))
                self.assertTrue(all(device["location_known"] for device in devices))

    def test_inventory_ingestion_queue_pipeline_and_human_review(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "DB_PATH", f"{directory}/netcoop.db"), \
                    patch.object(main, "redis_client", FakeRedis()), \
                    patch.object(main, "LLM", None), \
                    TestClient(main.app) as client:
                upload = client.post(
                    "/devices/upload",
                    files={"file": ("devices.csv", b"device_id,latitude,longitude,device_type\nSW1,47.6,-122.3,switch\n", "text/csv")},
                )
                self.assertEqual(upload.status_code, 200)
                self.assertEqual(upload.json()["uploaded"], 1)

                queued = client.post("/telemetry", json={
                    "device_id": "SW1",
                    "metrics": {"latency_s": 0.3, "packet_loss_pct": 2},
                    "status": "Warning",
                })
                self.assertEqual(queued.status_code, 202)
                event_id = queued.json()["event_id"]
                with main.connect_db() as connection:
                    telemetry_row = connection.execute(
                        "SELECT timestamp, metrics_json, severity FROM telemetry WHERE event_id=?",
                        (event_id,),
                    ).fetchone()
                event = {
                    "event_id": event_id,
                    "device_id": "SW1",
                    "timestamp": telemetry_row["timestamp"],
                    "metrics": {"latency_ms": 300.0, "packet_loss_pct": 2.0},
                    "severity": telemetry_row["severity"],
                }
                processed = client.post(
                    "/internal/process",
                    json=event,
                    headers={"x-internal-token": main.INTERNAL_TOKEN},
                )
                self.assertEqual(processed.status_code, 200)
                self.assertEqual(processed.json()["status"], "needs_human")

                information = client.post(f"/incidents/{event_id}/information", json={
                    "answers": {
                        "utm_alerts": False,
                        "recent_firewall_change": False,
                        "interface_errors_present": False,
                        "recent_route_change": False,
                    },
                    "event_context": {"event_happening": False},
                })
                self.assertEqual(information.status_code, 200)
                self.assertEqual(information.json()["status"], "processed")

                review = client.post(f"/incidents/{event_id}/review", json={
                    "reviewer": "Network operator",
                    "decision": "confirmed",
                    "feedback": "Confirmed against interface counters",
                })
                self.assertEqual(review.status_code, 200)
                overview = client.get("/overview").json()
                self.assertEqual(overview["devices"][0]["status"], "warning")
                self.assertEqual(overview["devices"][0]["location_known"], 1)
                self.assertEqual(overview["incidents"][0]["human_review"]["status"], "confirmed")
                report_file = client.get(f"/incidents/{event_id}/report")
                self.assertEqual(report_file.status_code, 200)
                self.assertIn("path delay", report_file.text.lower())
                health = client.get("/health").json()
                self.assertEqual(health["status"], "healthy")
                self.assertEqual(health["agents"]["UTM Agent"]["status"], "healthy")
                self.assertEqual(health["agents"]["Web Research Agent"]["status"], "healthy")
                self.assertIsInstance(health["agents"]["Performance Agent"]["latency_ms"], float)

    def test_knowledge_rule_search_returns_matching_contexts(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "DB_PATH", f"{directory}/netcoop.db"), TestClient(main.app) as client:
                response = client.get("/knowledge/rules", params={"q": "latency", "limit": 5})
                self.assertEqual(response.status_code, 200)
                result = response.json()
                self.assertGreater(result["total"], 0)
                self.assertLessEqual(len(result["rules"]), 5)
                self.assertTrue(all(
                    "latency" in json.dumps(rule).lower()
                    for rule in result["rules"]
                ))

    def test_unknown_metric_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "DB_PATH", f"{directory}/netcoop.db"), TestClient(main.app) as client:
                response = client.post("/telemetry", json={
                    "device_id": "SW1",
                    "metrics": {"made_up_metric": 1},
                })
                self.assertEqual(response.status_code, 422)

    def test_telemetry_schema_publishes_required_and_accepted_units(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "DB_PATH", f"{directory}/netcoop.db"), TestClient(main.app) as client:
                schema = client.get("/telemetry/schema").json()
                self.assertEqual(schema["metrics"]["bandwidth_mbps"]["canonical_unit"], "Mbps")
                self.assertIn("Gbps", schema["metrics"]["bandwidth_mbps"]["accepted_input_units"])

    def test_telemetry_endpoint_normalizes_selected_gbps_unit(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "DB_PATH", f"{directory}/netcoop.db"), \
                    patch.object(main, "redis_client", FakeRedis()), \
                    TestClient(main.app) as client:
                response = client.post("/telemetry", json={
                    "device_id": "RTR1",
                    "metrics": {"bandwidth": 2.5},
                    "units": {"bandwidth": "Gbps"},
                })
                self.assertEqual(response.status_code, 202)
                self.assertEqual(response.json()["units"]["bandwidth_mbps"], "Mbps")


if __name__ == "__main__":
    unittest.main()
