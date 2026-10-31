from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.correlation import CorrelationAgentOutput, ProbableCause
from backend.common.classes.workflow_state import WorkflowState
from backend.common.metrics import METRIC_UNITS
from backend.common.rules import BASE_RULES, FACT_CATALOG


def _rule_matches(rule: dict[str, Any], metrics: dict[str, float]) -> tuple[bool, list[str]]:
    evidence = []
    for metric, threshold in rule["required"].items():
        observed = metrics.get(metric)
        if observed is None or observed < threshold:
            return False, []
        evidence.append(
            f"{metric}={observed:g} {METRIC_UNITS[metric]} (rule threshold {threshold:g})"
        )
    alternatives = rule.get("alternatives", ())
    if alternatives and not any(
        metrics.get(metric, 0) >= threshold for metric, threshold in alternatives
    ):
        return False, []
    for metric, threshold in alternatives:
        if metrics.get(metric, 0) >= threshold:
            evidence.append(f"{metric}={metrics[metric]:g} (rule threshold {threshold:g})")
            break
    return True, evidence


def correlation_agent(state: WorkflowState) -> dict[str, Any]:
    metrics = state["telemetry"]["metrics"]
    answers = state.get("human_answers", {})
    causes: list[ProbableCause] = []
    for rule in BASE_RULES:
        matched, evidence = _rule_matches(rule, metrics)
        if matched:
            causes.append(ProbableCause(
                rule_id=rule["id"],
                cause=rule["cause"],
                probability=rule["probability"],
                evidence=evidence,
                recommended_action=rule["action"],
            ))

    if metrics.get("firewall_drops", 0) >= 100:
        if answers.get("recent_firewall_change") is True and answers.get("utm_alerts") is True:
            causes.append(ProbableCause(
                rule_id="UTM-01",
                cause="Firewall policy change or UTM security event",
                probability=0.94,
                evidence=[
                    f"firewall_drops={metrics['firewall_drops']:g} events",
                    "Client reported a recent firewall policy change",
                    "Client reported a related UTM alert",
                ],
                recommended_action="Review the firewall change and UTM event logs; validate policy scope and rollback only through change control.",
            ))

    for finding in state["performance"]["findings"]:
        if finding["deviation"] == "within":
            continue
        rule = next((item for item in FACT_CATALOG if item["metric"] == finding["metric"]), None)
        if rule is None:
            continue
        causes.append(ProbableCause(
            rule_id=rule["fact_id"],
            cause=rule["cause"],
            probability=0.82 if finding["severity"] == "warning" else 0.88,
            evidence=[
                f"{finding['metric']}={finding['observed']:g} {finding['unit']} outside normal range "
                f"{finding['normal_minimum']:g}-{finding['normal_maximum']:g} {finding['unit']}"
            ],
            recommended_action=rule["action"],
        ))

    deduplicated: dict[str, ProbableCause] = {}
    for cause in causes:
        previous = deduplicated.get(cause.cause)
        if previous is None or cause.probability > previous.probability:
            deduplicated[cause.cause] = cause
    ranked = sorted(deduplicated.values(), key=lambda cause: cause.probability, reverse=True)
    verified = [cause for cause in ranked if cause.probability >= 0.9]
    below = [cause for cause in ranked if cause.probability < 0.9]

    questions = list(state["utm"]["questions"])
    missing = list(state["utm"]["missing_information"])
    if state["performance"]["severity"] != "healthy":
        if metrics.get("packet_loss_pct", 0) > 0 and "interface_errors" not in metrics:
            missing.append("interface_errors")
            questions.append("Are interface/CRC errors increasing on the affected device or adjacent link?")
        if metrics.get("latency_ms", 0) >= 100 and not answers.get("recent_route_change"):
            missing.append("recent_route_change")
            questions.append("Was there a routing, QoS, or network configuration change near the time symptoms began?")
    questions = list(dict.fromkeys(questions))
    missing = sorted(set(missing))

    if questions and not answers:
        status = "needs_human"
    elif verified:
        status = "sufficient"
    elif state["performance"]["severity"] == "healthy":
        status = "sufficient"
    else:
        status = "insufficient_information"
    output = CorrelationAgentOutput(
        status=status,
        verified_causes=verified,
        below_threshold_causes=below,
        missing_information=missing if status != "sufficient" else [],
        questions=questions if status == "needs_human" else [],
        explanation=(
            "At least one static correlation rule met the 90% confidence threshold."
            if verified else "No rule reached the 90% threshold; additional evidence is required."
        ),
    )
    return {"correlation": output.model_dump(), **heartbeat("Correlation Agent")}
