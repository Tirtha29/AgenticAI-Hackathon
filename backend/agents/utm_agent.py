from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.utm import UTMAgentOutput
from backend.common.classes.workflow_state import WorkflowState
from backend.common.metrics import NORMAL_RANGES


def utm_agent(state: WorkflowState) -> dict[str, Any]:
    metrics = state["telemetry"]["metrics"]
    answers = state.get("human_answers", {})
    drops = metrics.get("firewall_drops")
    findings = []
    missing = []
    questions = []
    if drops is not None and drops > NORMAL_RANGES["firewall_drops"].maximum:
        findings.append(f"Firewall drop count {drops:g} events exceeds normal range.")
        if not (answers.get("recent_firewall_change") is True and answers.get("utm_alerts") is True):
            missing.extend(("recent_firewall_change", "utm_alerts"))
            questions.append("Was there a recent firewall policy change, and did the UTM report a related alert?")
    elif state["performance"]["severity"] != "healthy":
        missing.append("firewall_drops")
        questions.append(
            "Did the firewall or UTM produce a spike in denied events or a security alert? If available, provide firewall_drops."
        )
    output = UTMAgentOutput(
        observed_firewall_drops=drops,
        findings=findings,
        missing_information=missing,
        questions=questions,
    )
    return {"utm": output.model_dump(), **heartbeat("UTM Agent")}
