import tempfile
import unittest
from unittest.mock import patch

from fastapi.testclient import TestClient

import backend.main as main
from backend.common.demo_inventory import IIT_BHUBANESWAR_DEMO_DEVICES
from backend.simulation import EVENT_PRESETS, run_simulation



class _Pipeline:
    async def __aenter__(self):
        return self

    async def __aexit__(self, *_):
        return None

    def execute_command(self, *_args):
        return None

    def hset(self, *_args):
        return None

    async def execute(self):
        return []


class FakeRedis:
    def pipeline(self, **_kwargs):
        return _Pipeline()

    async def delete(self, *keys):
        return len(keys)


LIBRARY = {
    "anchor_device_id": "IITBBS-AP-02",
    "latitude": 20.1520,
    "longitude": 85.6748,
}


def devices():
    return [dict(device) for device in IIT_BHUBANESWAR_DEMO_DEVICES]


class SimulationEngineTests(unittest.TestCase):
    def test_event_overloads_nearby_devices_first(self):
        result = run_simulation(devices(), {"event_type": "festival", **LIBRARY})
        by_id = {d["device_id"]: d for d in result["devices"]}
        near = by_id["IITBBS-AP-02"]  # library access point, ~20 m away
        far = by_id["IITBBS-AP-03"]  # hostel north, several topology hops away
        self.assertEqual(near["severity"], "critical")
        self.assertEqual(near["role"], "direct")
        self.assertGreater(near["peak_utilization"], far["peak_utilization"])
        self.assertEqual(result["summary"]["epicentre_area"], "Library")
        self.assertIsNotNone(near["time_to_overload_min"])

    def test_other_areas_are_affected_by_spillover_and_shared_uplinks(self):
        result = run_simulation(devices(), {"event_type": "festival", **LIBRARY})
        self.assertGreater(result["summary"]["knock_on_devices"], 0)
        self.assertTrue(result["spill_flows"])
        knock_on = [d for d in result["devices"] if d["role"] in {"spillover", "collateral", "upstream"} and d["severity"] != "healthy"]
        self.assertTrue(knock_on)
        self.assertTrue(all(d["connection_hops"] > 0 for d in knock_on))

    def test_bigger_crowd_is_never_better(self):
        small = run_simulation(devices(), {"event_type": "festival", "attendance": 1000, **LIBRARY})["summary"]
        large = run_simulation(devices(), {"event_type": "festival", "attendance": 12000, **LIBRARY})["summary"]
        self.assertGreaterEqual(large["critical"], small["critical"])
        self.assertGreater(large["peak_network_load_pct"], small["peak_network_load_pct"])

    def test_mitigation_reduces_load_and_is_reported(self):
        result = run_simulation(devices(), {"event_type": "festival", "capacity_boost_pct": 100,
                                            "traffic_shaping_pct": 25, **LIBRARY})
        effect = result["mitigation_effect"]
        self.assertLess(effect["critical_after"], effect["critical_before"])
        self.assertLess(effect["peak_load_after_pct"], effect["peak_load_before_pct"])

    def test_outage_takes_devices_offline_and_shifts_users(self):
        result = run_simulation(devices(), {
            "event_type": "outage",
            "anchor_device_id": "IITBBS-RTR-01",
            "latitude": 20.1513,
            "longitude": 85.6761,
        })
        roles = result["summary"]["roles"]
        self.assertGreater(roles["offline"], 0)
        self.assertGreater(roles["spillover"], 0)
        offline = [d for d in result["devices"] if d["role"] == "offline"]
        self.assertTrue(all(d["peak_packet_loss_pct"] == 100.0 for d in offline))

    def test_is_deterministic_and_frames_are_consistent(self):
        first = run_simulation(devices(), {"event_type": "sports", **LIBRARY})
        second = run_simulation(devices(), {"event_type": "sports", **LIBRARY})
        self.assertEqual(first["devices"], second["devices"])
        count = len(first["frames"]["minutes"])
        self.assertLessEqual(count, 61)
        self.assertEqual(len(first["timeline"]), count)
        self.assertTrue(all(len(v) == count for v in first["frames"]["utilization"].values()))

    def test_disconnected_inventory_is_not_silently_connected(self):
        result = run_simulation(devices(), {"event_type": "exam", **LIBRARY})
        self.assertEqual(result["inferred_links"], [])

    def test_event_coordinates_do_not_replace_topology_anchor(self):
        first = run_simulation(devices(), {"event_type": "festival", **LIBRARY})
        second = run_simulation(devices(), {
            **LIBRARY,
            "latitude": -20.30,
            "longitude": -85.90,
        })
        self.assertEqual(first["devices"], second["devices"])
        self.assertEqual(first["scenario"]["anchor_device_id"], "IITBBS-AP-02")

    def test_every_preset_runs(self):
        for name in EVENT_PRESETS:
            result = run_simulation(devices(), {"event_type": name, **LIBRARY})
            self.assertEqual(result["summary"]["devices"], 15)


class SimulationApiTests(unittest.TestCase):
    def test_presets_and_run_endpoint(self):
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(main, "DB_PATH", f"{directory}/netcoop.db"), \
                    patch.object(main, "redis_client", FakeRedis()), \
                    TestClient(main.app) as client:
                self.assertEqual(client.post("/simulation/run", json={
                    "anchor_device_id": "IITBBS-AP-02",
                }).status_code, 409)
                client.post("/devices/demo/iit-bhubaneswar")
                self.assertIn("festival", client.get("/simulation/presets").json()["presets"])
                response = client.post("/simulation/run", json={"event_type": "festival", **LIBRARY})
                self.assertEqual(response.status_code, 200)
                body = response.json()
                self.assertEqual(body["summary"]["devices"], 15)
                self.assertTrue(body["recommendations"])
                self.assertEqual(client.post("/simulation/run", json={
                    "anchor_device_id": "IITBBS-AP-02",
                    "attendance": 0,
                }).status_code, 422)
                # what-if only: nothing is written
                self.assertTrue(all(d["status"] == "unknown" for d in client.get("/overview").json()["devices"]))


if __name__ == "__main__":
    unittest.main()
