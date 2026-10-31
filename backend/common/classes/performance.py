from typing import Literal

from pydantic import Field

from backend.common.classes.base import StrictModel


class NormalRange(StrictModel):
    minimum: float
    maximum: float
    unit: str


class MetricFinding(StrictModel):
    metric: str
    observed: float
    normal_minimum: float
    normal_maximum: float
    unit: str
    deviation: Literal["below", "within", "above"]
    severity: Literal["healthy", "warning", "critical"]


class PerformanceAgentOutput(StrictModel):
    device_id: str
    severity: Literal["healthy", "warning", "critical"]
    findings: list[MetricFinding]
    missing_baseline_metrics: list[str] = Field(default_factory=list)
