from pydantic import Field

from backend.common.classes.base import StrictModel
from backend.common.classes.device import DeviceRisk


class ConnectivityAgentOutput(StrictModel):
    radius_km: float = Field(gt=0)
    blast_radius: list[DeviceRisk]
