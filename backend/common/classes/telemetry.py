from pydantic import Field

from backend.common.classes.base import StrictModel


class TelemetryEvent(StrictModel):
    event_id: str
    timestamp: str
    device_id: str
    metrics: dict[str, float]
    units: dict[str, str]
    source_units: dict[str, str] = Field(default_factory=dict)
    severity: str
