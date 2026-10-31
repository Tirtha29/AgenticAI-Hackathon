from typing import Literal

from backend.common.classes.base import StrictModel
from backend.common.classes.correlation import ProbableCause
from backend.common.classes.device import DeviceRisk
from backend.common.classes.performance import MetricFinding
from backend.common.classes.web_research import WebResearchOutput


class IncidentReport(StrictModel):
    incident_id: str
    timestamp: str
    severity: Literal["healthy", "warning", "critical"]
    conclusion: Literal["probable_causes_ranked", "insufficient_information"]
    summary: str
    confidence_threshold: float
    scoring_method: Literal["groq_weighted", "static_fallback"]
    scoring_weights: dict[str, float]
    probable_causes: list[ProbableCause]
    unverified_candidates: list[ProbableCause]
    issue_devices: list[DeviceRisk]
    device_statuses: list[DeviceRisk]
    nearby_connections: list[DeviceRisk]
    event_context: dict[str, object] | None
    event_simulation: dict[str, object] | None
    telemetry: dict[str, float]
    units: dict[str, str]
    infrastructure_findings: list[MetricFinding]
    historical_context: list[dict[str, float | int | str | None]]
    human_questions: list[str]
    human_answers: dict[str, bool | str | float]
    human_review: dict[str, str | None]
    web_research: WebResearchOutput
    limitations: str


class ReportNarrative(StrictModel):
    summary: str
    limitations: str
