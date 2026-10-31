from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.performance import MetricFinding, PerformanceAgentOutput
from backend.common.classes.workflow_state import WorkflowState
from backend.common.metrics import METRIC_UNITS, NORMAL_RANGES

CRITICAL_LIMITS = {
    "cpu_utilization_pct": 95,
    "memory_utilization_pct": 98,
    "link_utilization_pct": 98,
    "packet_loss_pct": 10,
    "latency_ms": 500,
    "jitter_ms": 100,
    "queue_drops": 1000,
    "interface_errors": 100,
    "temperature_c": 85,
    "firewall_drops": 1000,
}


def performance_agent(state: WorkflowState) -> dict[str, Any]:
    telemetry = state["telemetry"]
    findings = []
    severity = "healthy"
    for metric, observed in telemetry["metrics"].items():
        normal = NORMAL_RANGES.get(metric)
        if normal is None:
            continue
        if observed < normal.minimum:
            deviation = "below"
            finding_severity = "warning"
        elif observed > normal.maximum:
            deviation = "above"
            finding_severity = "warning"
        else:
            deviation = "within"
            finding_severity = "healthy"
        critical_max = CRITICAL_LIMITS.get(metric)
        if deviation == "above" and critical_max is not None and observed >= critical_max:
            finding_severity = "critical"
        finding = MetricFinding(
            metric=metric,
            observed=observed,
            normal_minimum=normal.minimum,
            normal_maximum=normal.maximum,
            unit=normal.unit or METRIC_UNITS[metric],
            deviation=deviation,
            severity=finding_severity,
        )
        findings.append(finding.model_dump())
        if finding_severity == "critical":
            severity = "critical"
        elif finding_severity == "warning" and severity == "healthy":
            severity = "warning"
    output = PerformanceAgentOutput(
        device_id=telemetry["device_id"],
        severity=severity,
        findings=findings,
        missing_baseline_metrics=sorted(set(NORMAL_RANGES) - set(telemetry["metrics"])),
    )
    return {"performance": output.model_dump(), **heartbeat("Performance Agent")}
