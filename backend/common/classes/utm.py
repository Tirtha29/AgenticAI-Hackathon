from pydantic import Field

from backend.common.classes.base import StrictModel


class UTMAgentOutput(StrictModel):
    observed_firewall_drops: float | None = Field(default=None, ge=0)
    findings: list[str] = Field(default_factory=list)
    missing_information: list[str] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)
