from typing import Literal

from pydantic import Field

from backend.common.classes.base import StrictModel


class CauseScoreFactors(StrictModel):
    rule_match: float = Field(ge=0, le=1)
    cross_metric: float = Field(ge=0, le=1)
    severity: float = Field(ge=0, le=1)
    history: float = Field(ge=0, le=1)
    topology: float = Field(ge=0, le=1)
    client_confirmation: float = Field(ge=0, le=1)


class CauseScoreAssessment(StrictModel):
    rule_id: str
    factors: CauseScoreFactors


class CorrelationScoringOutput(StrictModel):
    assessments: list[CauseScoreAssessment] = Field(default_factory=list)
    web_suggestions: list["WebCauseSuggestion"] = Field(default_factory=list)


class WebSource(StrictModel):
    source_id: int = Field(ge=0)
    title: str
    url: str
    snippet: str
    relevance: float = Field(ge=0, le=1)


class WebSourceReference(StrictModel):
    source_id: int = Field(ge=0)
    title: str
    url: str


class WebCauseSuggestion(StrictModel):
    cause: str = Field(min_length=3, max_length=200)
    source_ids: list[int] = Field(min_length=1, max_length=3)
    factors: CauseScoreFactors
    recommended_action: str = Field(min_length=5, max_length=500)


CorrelationScoringOutput.model_rebuild()


class ProbableCause(StrictModel):
    rule_id: str
    cause: str
    probability: float = Field(ge=0, le=1)
    evidence: list[str]
    missing_evidence: list[str] = Field(default_factory=list)
    recommended_action: str
    score_breakdown: CauseScoreFactors | None = None
    sources: list[WebSourceReference] = Field(default_factory=list)


class CorrelationAgentOutput(StrictModel):
    status: Literal["sufficient", "needs_human", "insufficient_information"]
    confidence_threshold: float = Field(default=0.9, ge=0, le=1)
    scoring_method: Literal["groq_weighted", "static_fallback"]
    scoring_weights: dict[str, float]
    verified_causes: list[ProbableCause]
    below_threshold_causes: list[ProbableCause]
    missing_information: list[str]
    questions: list[str]
    explanation: str
