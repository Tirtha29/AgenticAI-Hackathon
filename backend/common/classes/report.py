from typing import Literal

from backend.common.classes.base import StrictModel
from backend.common.classes.correlation import ProbableCause
from backend.common.classes.device import DeviceRisk
from backend.common.classes.performance import MetricFinding


class IncidentReport(StrictModel):
    incident_id: str
    timestamp: str
    severity: Literal["healthy", "warning", "critical"]
    conclusion: Literal["probable_causes_ranked", "insufficient_information"]
    summary: str
    confidence_threshold: float
    probable_causes: list[ProbableCause]
    unverified_candidates: list[ProbableCause]
    issue_devices: list[DeviceRisk]
    device_statuses: list[DeviceRisk]
    blast_radius: list[DeviceRisk]
    telemetry: dict[str, float]
    units: dict[str, str]
    infrastructure_findings: list[MetricFinding]
    historical_context: list[dict[str, float | int | str | None]]
    human_questions: list[str]
    human_answers: dict[str, bool | str | float]
    human_review: dict[str, str | None]
    limitations: str


class ReportNarrative(StrictModel):
    summary: str
    limitations: str
