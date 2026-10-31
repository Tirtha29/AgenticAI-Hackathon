from pydantic import Field

from backend.common.classes.base import StrictModel
from backend.common.classes.device import DeviceRisk


class HealthAgentOutput(StrictModel):
    window_hours: float = 2
    evaluated_devices: int = Field(ge=0)
    problematic_routers: list[DeviceRisk]
    affected_devices: list[DeviceRisk]
    device_statuses: list[DeviceRisk]
    historical_samples: int = Field(ge=0)
