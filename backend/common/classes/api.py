from datetime import datetime

from pydantic import BaseModel, Field, FiniteFloat


class TelemetryIn(BaseModel):
    timestamp: datetime | None = None
    device_id: str = Field(min_length=1, max_length=128)
    metrics: dict[str, FiniteFloat] = Field(min_length=1)
    units: dict[str, str] = Field(default_factory=dict)


class HumanInformationIn(BaseModel):
    answers: dict[str, bool | str | FiniteFloat] = Field(min_length=1)


class ReviewIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    decision: str = Field(pattern="^(confirmed|rejected)$")
    feedback: str | None = Field(default=None, max_length=2000)
