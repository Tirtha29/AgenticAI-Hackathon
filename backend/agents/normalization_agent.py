from typing import Any

from backend.common.classes.telemetry import TelemetryEvent
from backend.common.classes.workflow_state import WorkflowState
from backend.common.metrics import METRIC_UNITS
from backend.agents.utils import heartbeat


def normalize_node(state: WorkflowState) -> dict[str, Any]:
    telemetry = TelemetryEvent.model_validate(state["telemetry"])
    unsupported = set(telemetry.metrics) - set(METRIC_UNITS)
    if unsupported:
        raise ValueError(f"Telemetry contains unsupported normalized metrics: {', '.join(sorted(unsupported))}")
    return {"telemetry": telemetry.model_dump(), **heartbeat("Normalization Agent")}
