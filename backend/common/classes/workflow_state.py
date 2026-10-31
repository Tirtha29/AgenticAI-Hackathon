import operator
from collections.abc import Callable
from typing import Annotated, Any, TypedDict


class WorkflowState(TypedDict, total=False):
    telemetry: dict[str, Any]
    device: dict[str, Any]
    history: list[dict[str, Any]]
    telemetry_window: list[dict[str, Any]]
    human_answers: dict[str, bool | str | float]
    geo_lookup: Callable[[float, float, float], list[dict[str, Any]]]
    radius_km: float
    performance: dict[str, Any]
    infrastructure: dict[str, Any]
    health: dict[str, Any]
    connectivity: dict[str, Any]
    utm: dict[str, Any]
    web_research: dict[str, Any]
    correlation: dict[str, Any]
    report: dict[str, Any]
    llm: Any
    agent_heartbeat: Annotated[dict[str, str], operator.or_]
