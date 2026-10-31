from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.infrastructure import InfrastructureAgentOutput
from backend.common.classes.performance import MetricFinding
from backend.common.classes.workflow_state import WorkflowState


def infrastructure_agent(state: WorkflowState) -> dict[str, Any]:
    findings = [
        MetricFinding.model_validate(item)
        for item in state["performance"]["findings"]
        if item["metric"] in {"queue_drops", "interface_errors", "temperature_c"}
        and item["deviation"] != "within"
    ]
    actions = []
    if any(item.metric == "queue_drops" for item in findings):
        actions.append("Review queue depth, QoS classes, and sustained burst traffic.")
    if any(item.metric == "interface_errors" for item in findings):
        actions.append("Inspect optics, cabling, CRC counters, and interface negotiation at both link ends.")
    if any(item.metric == "temperature_c" for item in findings):
        actions.append("Check device airflow, fan status, and rack temperature.")
    output = InfrastructureAgentOutput(findings=findings, maintenance_actions=actions)
    return {"infrastructure": output.model_dump(), **heartbeat("Infrastructure Agent")}
