from typing import Literal

from pydantic import Field

from backend.common.classes.base import StrictModel


class ProbableCause(StrictModel):
    rule_id: str
    cause: str
    probability: float = Field(ge=0, le=1)
    evidence: list[str]
    missing_evidence: list[str] = Field(default_factory=list)
    recommended_action: str


class CorrelationAgentOutput(StrictModel):
    status: Literal["sufficient", "needs_human", "insufficient_information"]
    confidence_threshold: float = Field(default=0.9, ge=0, le=1)
    verified_causes: list[ProbableCause]
    below_threshold_causes: list[ProbableCause]
    missing_information: list[str]
    questions: list[str]
    explanation: str
