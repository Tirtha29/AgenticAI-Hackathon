import json
from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.connectivity import ConnectivityAgentOutput
from backend.common.classes.device import DeviceRisk
from backend.common.classes.workflow_state import WorkflowState


def connectivity_agent(state: WorkflowState) -> dict[str, Any]:
    hop_limit = max(1, min(3, int(state.get("connection_hops", 3))))
    inventory = state.get("device_inventory", [])
    device_types = {
        str(item["device_id"]): str(item.get("device_type") or "network device")
        for item in inventory
    }
    adjacency: dict[str, set[str]] = {device_id: set() for device_id in device_types}
    for item in inventory:
        device_id = str(item["device_id"])
        raw_neighbors = item.get("neighbors_json") or item.get("neighbors") or []
        if isinstance(raw_neighbors, str):
            try:
                raw_neighbors = json.loads(raw_neighbors)
            except json.JSONDecodeError:
                raw_neighbors = [
                    part.strip()
                    for part in raw_neighbors.replace(",", ";").split(";")
                    if part.strip()
                ]
        if not isinstance(raw_neighbors, list):
            continue
        for neighbor in raw_neighbors:
            neighbor_id = str(neighbor)
            if neighbor_id in adjacency and neighbor_id != device_id:
                adjacency[device_id].add(neighbor_id)
                adjacency[neighbor_id].add(device_id)

    centers = state["health"]["affected_devices"]
    by_device: dict[str, dict[str, Any]] = {}
    for center in centers:
        start = center["device_id"]
        frontier = {start}
        visited = {start}
        for hops in range(1, hop_limit + 1):
            frontier = {
                neighbor
                for current in frontier
                for neighbor in adjacency.get(current, ())
                if neighbor not in visited
            }
            visited.update(frontier)
            for device_id in frontier:
                probability = round(float(center["probability"]) * (0.78 ** hops), 3)
                candidate = DeviceRisk(
                    device_id=device_id,
                    device_type=device_types.get(device_id, "network device"),
                    severity="warning",
                    probability=probability,
                    connection_hops=hops,
                    evidence=[
                        f"{hops} connection hop(s) from affected device {start}; "
                        "topology proximity is a warning signal, not a confirmed fault."
                    ],
                ).model_dump()
                previous = by_device.get(device_id)
                if previous is None or candidate["probability"] > previous["probability"]:
                    by_device[device_id] = candidate
    output = ConnectivityAgentOutput(
        hop_limit=hop_limit,
        nearby_connections=sorted(
            by_device.values(),
            key=lambda item: (
                -item["probability"],
                item["connection_hops"],
                item["device_id"],
            ),
        ),
    )
    return {"connectivity": output.model_dump(), **heartbeat("Connectivity Agent")}
