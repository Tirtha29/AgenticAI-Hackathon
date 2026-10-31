from typing import Any

from backend.agents.utils import heartbeat
from backend.common.classes.performance import MetricFinding
from backend.common.classes.report import IncidentReport, ReportNarrative
from backend.common.classes.web_research import WebResearchOutput
from backend.common.classes.workflow_state import WorkflowState
from backend.common.metrics import METRIC_UNITS


def build_report_parser():
    from langchain_core.output_parsers import PydanticOutputParser

    return PydanticOutputParser(pydantic_object=ReportNarrative)


def report_agent(state: WorkflowState) -> dict[str, Any]:
    telemetry = state["telemetry"]
    correlation = state["correlation"]
    performance = state["performance"]
    health = state["health"]
    connectivity = state["connectivity"]

    issue_by_id = {item["device_id"]: item for item in health["affected_devices"]}
    for nearby in connectivity["blast_radius"]:
        if nearby["probability"] >= 0.45:
            issue_by_id[nearby["device_id"]] = nearby

    ranked = correlation["verified_causes"]
    if correlation["status"] == "needs_human":
        summary = "Awaiting client information before confirming a cause at 90% confidence."
    elif correlation["status"] == "insufficient_information":
        summary = "Insufficient information: no probable cause met the 90% confidence threshold."
    elif ranked:
        summary = f"Top probable cause: {ranked[0]['cause']} ({ranked[0]['probability']:.0%})."
    else:
        summary = f"No abnormal telemetry found for {telemetry['device_id']}."

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
        "Nearby-device probability is a proximity heuristic, not evidence that the device has failed."
    )
    if correlation["scoring_method"] == "static_fallback":
        limitations = (
            "Groq scoring was not configured; cause scores use static fallback values and are "
            "not calibrated statistical forecasts. Nearby-device probability is a proximity "
            "heuristic, not evidence that the device has failed."
        )
    web_research = state.get("web_research", {})
    if web_research.get("status") == "searched":
        limitations += " External search results are references only and may be outdated or unrelated."
    if state.get("llm") is not None:
        from langchain_core.prompts import ChatPromptTemplate

        parser = build_report_parser()
        prompt = ChatPromptTemplate.from_messages([
            (
                "system",
                "Summarize only verified telemetry and findings. Do not invent causes or "
                "change scores. State that confidence scores are not statistically calibrated.\n"
                "{format_instructions}",
            ),
            ("human", "Report data: {report_data}"),
        ])
        narrative: ReportNarrative = (prompt | state["llm"] | parser).invoke({
            "format_instructions": parser.get_format_instructions(),
            "report_data": {
                "severity": performance["severity"],
                "conclusion": correlation["status"],
                "verified_causes": ranked,
                "questions": correlation["questions"],
                "telemetry": telemetry["metrics"],
                "web_research": web_research,
            },
        })
        summary = narrative.summary
        limitations = narrative.limitations

    map_statuses = {item["device_id"]: item for item in health["device_statuses"]}
    for nearby in connectivity["blast_radius"]:
        current = map_statuses.get(nearby["device_id"])
        if current is None or nearby["probability"] > current["probability"]:
            map_statuses[nearby["device_id"]] = nearby

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
        blast_radius=connectivity["blast_radius"],
        telemetry=telemetry["metrics"],
        units=telemetry["units"],
        infrastructure_findings=[
            MetricFinding.model_validate(item) for item in state["infrastructure"]["findings"]
        ],
        historical_context=historical_context,
        human_questions=correlation["questions"],
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
