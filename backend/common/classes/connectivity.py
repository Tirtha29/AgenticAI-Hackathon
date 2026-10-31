from pydantic import Field

from backend.common.classes.base import StrictModel
from backend.common.classes.device import DeviceRisk


class ConnectivityAgentOutput(StrictModel):
    hop_limit: int = Field(ge=1, le=3)
    nearby_connections: list[DeviceRisk]
