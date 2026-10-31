from typing import Literal

from pydantic import Field

from backend.common.classes.base import StrictModel


class DeviceRisk(StrictModel):
    device_id: str
    device_type: str
    latitude: float
    longitude: float
    severity: Literal["healthy", "warning", "critical"]
    probability: float = Field(ge=0, le=1)
    distance_km: float | None = Field(default=None, ge=0)
    evidence: list[str] = Field(default_factory=list)
