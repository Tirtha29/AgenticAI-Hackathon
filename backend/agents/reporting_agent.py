import logging
from typing import Any

from groq import APIError
from langchain_core.exceptions import OutputParserException

from backend.agents.utils import heartbeat
from backend.common.classes.performance import MetricFinding
from backend.common.classes.report import IncidentReport, ReportNarrative
from backend.common.classes.web_research import WebResearchOutput
from backend.common.classes.workflow_state import WorkflowState
from backend.common.metrics import METRIC_UNITS

logger = logging.getLogger(__name__)


def build_report_parser():
    from langchain_core.output_parsers import PydanticOutputParser

    return PydanticOutputParser(pydantic_object=ReportNarrative)


def report_agent(state: WorkflowState) -> dict[str, Any]:
    telemetry = state["telemetry"]
    correlation = state["correlation"]
    performance = state["performance"]
    health = state["health"]
    connectivity = state["connectivity"]
    event_context = state.get("event_context")
    event_simulation = state.get("event_simulation")

    issue_by_id = {item["device_id"]: item for item in health["affected_devices"]}
    for nearby in connectivity["nearby_connections"]:
        if nearby["probability"] >= 0.45:
            issue_by_id[nearby["device_id"]] = nearby
    if event_simulation:
        for simulated in event_simulation["devices"]:
            if simulated["severity"] == "healthy":
                continue
            issue_by_id[simulated["device_id"]] = {
                "device_id": simulated["device_id"],
                "device_type": simulated["device_type"],
                "severity": simulated["severity"],
                "probability": simulated["risk_probability"],
                "connection_hops": simulated["connection_hops"],
                "evidence": [
                    f"Event simulation predicts {simulated['severity']} load "
                    f"({simulated['peak_utilization']:.0%}) at {simulated['peak_minute']} minutes."
                ],
            }

    ranked = correlation["verified_causes"]
    if correlation["status"] == "needs_human":
        summary = "Awaiting client information before confirming a cause at 90% confidence."
    elif correlation["status"] == "insufficient_information":
        summary = "Insufficient information: no probable cause met the 90% confidence threshold."
    elif ranked:
        summary = f"Top probable cause: {ranked[0]['cause']} ({ranked[0]['probability']:.0%})."
    else:
        summary = f"No abnormal telemetry found for {telemetry['device_id']}."
    if event_simulation:
        overloads = event_simulation["summary"]["critical"] + event_simulation["summary"]["warning"]
        summary += (
            f" Event what-if estimates {overloads} device(s) may be overloaded or at warning "
            f"risk near {event_context['anchor_device_id']}."
        )

    historical_context = []
    for metric, current in telemetry["metrics"].items():
        previous = [
            entry["metrics"][metric]
            for entry in state.get("history", [])
            if metric in entry.get("metrics", {})
        ]
        if previous:
            baseline = sum(previous) / len(previous)
            historical_context.append({
                "metric": metric,
                "unit": METRIC_UNITS[metric],
                "current": current,
                "two_hour_average": round(baseline, 3),
                "delta": round(current - baseline, 3),
                "samples": len(previous),
            })

    limitations = (
        "Groq scores are weighted evidence-based confidence estimates, not calibrated statistical forecasts. "
        "Connection-hop risk is a topology heuristic, not evidence that a neighboring device has failed."
    )
    if correlation["scoring_method"] == "static_fallback":
        limitations = (
            f"{correlation['explanation']} Cause scores are not calibrated statistical forecasts. "
            "Connection-hop risk is a topology heuristic, "
            "not evidence that a neighboring device has failed."
        )
    if event_simulation:
        limitations += (
            " Event simulation is a deterministic what-if estimate using assumed device capacities "
            "and traffic rates; event coordinates are operator-provided context and do not locate devices."
        )
    web_research = state.get("web_research", {})
    if web_research.get("status") == "searched":
        limitations += " External search results are references only and may be outdated or unrelated."
    if state.get("llm") is not None and correlation["scoring_method"] != "static_fallback":
        from langchain_core.prompts import ChatPromptTemplate

        parser = build_report_parser()
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "Summarize only verified telemetry and findings. Do not invent causes or "
                "change scores. Describe the event simulation only as a what-if estimate, "
                "never as observed device health. State that confidence scores are not statistically calibrated.\n"
                "{format_instructions}",
            ),
            ("human", "Report data: {report_data}"),
        ])
        try:
            narrative: ReportNarrative = (prompt | state["llm"] | parser).invoke({
                "format_instructions": parser.get_format_instructions(),
                "report_data": {
                    "severity": performance["severity"],
                    "conclusion": correlation["status"],
                    "verified_causes": ranked,
                    "questions": correlation["questions"],
                    "telemetry": telemetry["metrics"],
                    "web_research": web_research,
                    "event_context": event_context,
                    "event_simulation_summary": event_simulation["summary"] if event_simulation else None,
                },
            })
        except (APIError, OutputParserException) as error:
            logger.warning(
                "Groq report narrative failed (%s); retaining deterministic report text.",
                type(error).__name__,
            )
            limitations += (
                f" Groq report narrative failed ({type(error).__name__}); "
                "deterministic report text is shown."
            )
        else:
            summary = narrative.summary
            limitations = narrative.limitations
            if event_simulation:
                limitations += (
                    " Event simulation is a deterministic what-if estimate using assumed device capacities "
                    "and traffic rates; event coordinates are operator-provided context and do not locate devices."
                )

    map_statuses = {item["device_id"]: item for item in health["device_statuses"]}
    questions = list(correlation["questions"])
    if event_context is None and correlation["status"] == "needs_human":
        questions.append(
            "Is a crowd-gathering event happening? If yes, provide its coordinates and the serving device."
        )

    report = IncidentReport(
        incident_id=telemetry["event_id"],
        timestamp=telemetry["timestamp"],
        severity=performance["severity"],
        conclusion=(
            "insufficient_information"
            if correlation["status"] in {"needs_human", "insufficient_information"}
            else "probable_causes_ranked"
        ),
        summary=summary,
        confidence_threshold=correlation["confidence_threshold"],
        scoring_method=correlation["scoring_method"],
        scoring_weights=correlation["scoring_weights"],
        probable_causes=ranked,
        unverified_candidates=correlation["below_threshold_causes"],
        issue_devices=sorted(issue_by_id.values(), key=lambda item: item["probability"], reverse=True),
        device_statuses=sorted(map_statuses.values(), key=lambda item: item["probability"], reverse=True),
        nearby_connections=connectivity["nearby_connections"],
        event_context=event_context,
        event_simulation=event_simulation,
        telemetry=telemetry["metrics"],
        units=telemetry["units"],
        infrastructure_findings=[
            MetricFinding.model_validate(item) for item in state["infrastructure"]["findings"]
        ],
        historical_context=historical_context,
        human_questions=questions,
        human_answers=state.get("human_answers", {}),
        human_review={
            "status": "pending" if correlation["status"] == "needs_human" else correlation["status"],
            "reviewer": None,
            "feedback": None,
        },
        web_research=WebResearchOutput.model_validate(state["web_research"]),
        limitations=limitations,
    )
    return {"report": report.model_dump(), **heartbeat("Reporting Agent")}
