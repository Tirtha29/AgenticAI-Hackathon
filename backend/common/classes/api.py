from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, FiniteFloat, model_validator


class TelemetryIn(BaseModel):
    timestamp: datetime | None = None
    device_id: str = Field(min_length=1, max_length=128)
    metrics: dict[str, FiniteFloat] = Field(min_length=1)
    units: dict[str, str] = Field(default_factory=dict)


class HumanInformationIn(BaseModel):
    answers: dict[str, bool | str | FiniteFloat] = Field(default_factory=dict)
    event_context: EventContextIn | None = None

    @model_validator(mode="after")
    def require_information(self) -> HumanInformationIn:
        if not self.answers and self.event_context is None:
            raise ValueError("Provide diagnostic answers or event context.")
        return self


class EventContextIn(BaseModel):
    event_happening: bool
    event_name: str | None = Field(default=None, max_length=80)
    event_type: Literal["festival", "sports", "livestream", "exam", "outage"] = "festival"
    latitude: FiniteFloat | None = Field(default=None, ge=-90, le=90)
    longitude: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    anchor_device_id: str | None = Field(default=None, min_length=1, max_length=128)
    attendance: int | None = Field(default=None, ge=1, le=500_000)
    radius_hops: int | None = Field(default=None, ge=1, le=3)
    duration_min: int | None = Field(default=None, ge=15, le=720)
    capacity_boost_pct: FiniteFloat = Field(default=0, ge=0, le=300)
    traffic_shaping_pct: FiniteFloat = Field(default=0, ge=0, le=80)

    @model_validator(mode="after")
    def require_event_location_and_anchor(self) -> EventContextIn:
        if self.event_happening and (
            self.latitude is None
            or self.longitude is None
            or not self.anchor_device_id
        ):
            raise ValueError(
                "For an active event, provide its coordinates and the serving/anchor device."
            )
        return self


class ReviewIn(BaseModel):
    reviewer: str = Field(min_length=1, max_length=120)
    decision: str = Field(pattern="^(confirmed|rejected)$")
    feedback: str | None = Field(default=None, max_length=2000)


class SimulationIn(BaseModel):
    """Validated what-if event scenario; omitted values use preset defaults."""

    event_name: str | None = Field(default=None, max_length=80)
    event_type: Literal["festival", "sports", "livestream", "exam", "outage"] = "festival"
    anchor_device_id: str = Field(min_length=1, max_length=128)
    latitude: FiniteFloat | None = Field(default=None, ge=-90, le=90)
    longitude: FiniteFloat | None = Field(default=None, ge=-180, le=180)
    attendance: int | None = Field(default=None, ge=1, le=500_000)
    radius_hops: int | None = Field(default=None, ge=1, le=3)
    duration_min: int | None = Field(default=None, ge=15, le=720)
    capacity_boost_pct: FiniteFloat = Field(default=0, ge=0, le=300)
    traffic_shaping_pct: FiniteFloat = Field(default=0, ge=0, le=80)
    use_live_health: bool = True
