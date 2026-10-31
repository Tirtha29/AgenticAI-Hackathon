from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.connectivity import ConnectivityAgentOutput
from backend.common.classes.device import DeviceRisk
from backend.common.classes.workflow_state import WorkflowState


def connectivity_agent(state: WorkflowState) -> dict[str, Any]:
    radius_km = float(state.get("radius_km", 5.0))
    lookup = state.get("geo_lookup")
    centers = state["health"]["problematic_routers"]
    by_device: dict[str, dict[str, Any]] = {}
    for center in centers:
        if not lookup or (center["latitude"] == 0 and center["longitude"] == 0):
            continue
        for nearby in lookup(center["longitude"], center["latitude"], radius_km):
            device_id = nearby["device_id"]
            if device_id == center["device_id"]:
                continue
            distance = float(nearby["distance_km"])
            proximity = max(0.0, 1.0 - distance / radius_km)
            probability = round(center["probability"] * proximity, 3)
            candidate = DeviceRisk(
                device_id=device_id,
                device_type=nearby.get("device_type") or "network device",
                latitude=float(nearby["latitude"]),
                longitude=float(nearby["longitude"]),
                severity="critical" if probability >= 0.8 else ("warning" if probability >= 0.45 else "healthy"),
                probability=probability,
                distance_km=distance,
                evidence=[f"Within {distance:.2f} km of problematic router {center['device_id']}"],
            ).model_dump()
            previous = by_device.get(device_id)
            if previous is None or candidate["probability"] > previous["probability"]:
                by_device[device_id] = candidate
    output = ConnectivityAgentOutput(
        radius_km=radius_km,
        blast_radius=sorted(by_device.values(), key=lambda item: item["probability"], reverse=True),
    )
    return {"connectivity": output.model_dump(), **heartbeat("Connectivity Agent")}
