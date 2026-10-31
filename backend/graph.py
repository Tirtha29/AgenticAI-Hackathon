from __future__ import annotations

from datetime import datetime
from threading import Lock
from time import perf_counter
from typing import Any

from langgraph.graph import END, START, StateGraph

from backend.agents import (
    connectivity_agent,
    correlation_agent,
    health_agent,
    infrastructure_agent,
    normalize_node,
    performance_agent,
    report_agent,
    utm_agent,
    web_research_agent,
)
from backend.common.classes.workflow_state import WorkflowState

HEARTBEATS: dict[str, datetime] = {}
AGENT_RUNS: dict[str, dict[str, Any]] = {}
_AGENT_RUNS_LOCK = Lock()


def _track_agent(name: str, agent: Any) -> Any:
    def tracked(state: WorkflowState) -> dict[str, Any]:
        started = perf_counter()
        succeeded = False
        try:
            result = agent(state)
            succeeded = True
            return result
        finally:
            completed_at = datetime.now().astimezone()
            with _AGENT_RUNS_LOCK:
                AGENT_RUNS[name] = {
                    "last_execution": completed_at,
                    "latency_ms": round((perf_counter() - started) * 1000, 2),
                    "last_run_succeeded": succeeded,
                }

    return tracked


def build_workflow():
    graph = StateGraph(WorkflowState)
    graph.add_node("normalization", _track_agent("Normalization Agent", normalize_node))
    graph.add_node("performance", _track_agent("Performance Agent", performance_agent))
    graph.add_node("infrastructure", _track_agent("Infrastructure Agent", infrastructure_agent))
    graph.add_node("health", _track_agent("Health Check Agent", health_agent))
    graph.add_node("connectivity", _track_agent("Connectivity Agent", connectivity_agent))
    graph.add_node("utm", _track_agent("UTM Agent", utm_agent))
    graph.add_node("web_research", _track_agent("Web Research Agent", web_research_agent))
    graph.add_node("correlation", _track_agent("Correlation Agent", correlation_agent))
    graph.add_node("reporting", _track_agent("Reporting Agent", report_agent))
    graph.add_edge(START, "normalization")
    graph.add_edge("normalization", "performance")
    graph.add_edge("performance", "infrastructure")
    graph.add_edge("infrastructure", "health")
    graph.add_edge("health", "connectivity")
    graph.add_edge("connectivity", "utm")
    graph.add_edge("utm", "web_research")
    graph.add_edge("web_research", "correlation")
    graph.add_edge("correlation", "reporting")
    graph.add_edge("reporting", END)
    return graph.compile()


WORKFLOW = build_workflow()


def run_workflow(
    event: dict[str, Any],
    device: dict[str, Any] | None = None,
    history: list[dict[str, Any]] | None = None,
    telemetry_window: list[dict[str, Any]] | None = None,
    human_answers: dict[str, bool | str | float] | None = None,
    device_inventory: list[dict[str, Any]] | None = None,
    connection_hops: int = 3,
    llm: Any = None,
    event_context: dict[str, Any] | None = None,
    event_simulation: dict[str, Any] | None = None,
) -> dict[str, Any]:
    result = WORKFLOW.invoke({
        "telemetry": event,
        "device": device or {},
        "history": history or [],
        "telemetry_window": telemetry_window or [],
        "human_answers": human_answers or {},
        "device_inventory": device_inventory or [],
        "connection_hops": connection_hops,
        "event_context": event_context,
        "event_simulation": event_simulation,
        "llm": llm,
    })
    HEARTBEATS.update({
        name: datetime.fromisoformat(value)
        for name, value in result.get("agent_heartbeat", {}).items()
    })
    return result["report"]
