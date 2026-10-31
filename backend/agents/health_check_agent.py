from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.device import DeviceRisk
from backend.common.classes.health import HealthAgentOutput
from backend.common.classes.workflow_state import WorkflowState
from backend.common.metrics import METRIC_UNITS, NORMAL_RANGES


def health_agent(state: WorkflowState) -> dict[str, Any]:
    event = state["telemetry"]
    current_device = state.get("device") or {}
    samples = list(state.get("telemetry_window", []))
    samples.append({
        "device_id": event["device_id"],
        "timestamp": event["timestamp"],
        "device_type": current_device.get("device_type") or "network device",
        "latitude": current_device.get("latitude", 0.0),
        "longitude": current_device.get("longitude", 0.0),
        "location_known": current_device.get("location_known", False),
        "severity": state["performance"]["severity"],
        "metrics": event["metrics"],
    })
    latest: dict[str, dict[str, Any]] = {}
    for sample in sorted(samples, key=lambda row: row["timestamp"]):
        latest[sample["device_id"]] = sample

    affected = []
    routers = []
    statuses = []
    for sample in latest.values():
        metrics = sample.get("metrics", {})
        evidence = [
            f"{metric}={value:g} {METRIC_UNITS[metric]}"
            for metric, value in metrics.items()
            if metric in NORMAL_RANGES and (
                value > NORMAL_RANGES[metric].maximum or value < NORMAL_RANGES[metric].minimum
            )
        ]
        severity = sample["severity"]
        risk = DeviceRisk(
            device_id=sample["device_id"],
            device_type=sample.get("device_type") or "network device",
            latitude=float(sample.get("latitude") or 0),
            longitude=float(sample.get("longitude") or 0),
            severity=severity,
            probability=0.96 if severity == "critical" else (0.78 if severity == "warning" else 0.05),
            evidence=evidence,
        )
        statuses.append(risk.model_dump())
        if severity == "healthy":
            continue
        affected.append(risk.model_dump())
        if "router" in risk.device_type.lower():
            routers.append(risk.model_dump())
    output = HealthAgentOutput(
        evaluated_devices=len(latest),
        problematic_routers=routers,
        affected_devices=affected,
        device_statuses=statuses,
        historical_samples=len(state.get("telemetry_window", [])),
    )
    return {"health": output.model_dump(), **heartbeat("Health Check Agent")}
