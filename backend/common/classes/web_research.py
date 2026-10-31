from typing import Literal

from pydantic import Field

from backend.common.classes.base import StrictModel
from backend.common.classes.correlation import WebSource


class WebResearchOutput(StrictModel):
    status: Literal[
        "disabled",
        "skipped_healthy",
        "local_match_found",
        "searched",
        "unavailable",
    ]
    query: str | None = None
    sources: list[WebSource] = Field(default_factory=list)
    message: str | None = None
