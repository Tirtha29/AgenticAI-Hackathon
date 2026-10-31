from __future__ import annotations

import os
from typing import Any
from urllib.parse import urlparse

import httpx

from backend.agents.utils import heartbeat
from backend.common.classes.web_research import WebResearchOutput, WebSource
from backend.common.classes.workflow_state import WorkflowState
from backend.common.classes.correlation import WebSource
from backend.common.metrics import NORMAL_RANGES
from backend.common.rules import BASE_RULES, CAUSE_RULES


TAVILY_SEARCH_URL = "https://api.tavily.com/search"


def has_local_rule_match(metrics: dict[str, float]) -> bool:
    for rule in BASE_RULES:
        if any(metrics.get(key, float("-inf")) < threshold for key, threshold in rule["required"].items()):
            continue
        alternatives = rule.get("alternatives", ())
        if alternatives and not any(
            metrics.get(key, 0) >= threshold
            for key, threshold in alternatives
        ):
            continue
        if all(metrics.get(key) is not None for key in rule["required"]):
            return True
    return any(
        metrics.get(metric) is not None and metrics[metric] >= threshold
        for _, metric, threshold, _ in CAUSE_RULES
    )


def _build_search_query(metrics: dict[str, float]) -> str:
    abnormal = [
        metric.replace("_", " ")
        for metric, observed in metrics.items()
        if metric in NORMAL_RANGES
        and (
            observed < NORMAL_RANGES[metric].minimum
            or observed > NORMAL_RANGES[metric].maximum
        )
    ]
    return "network troubleshooting causes for " + ", ".join(abnormal[:6])


def _is_web_url(value: str) -> bool:
    parsed = urlparse(value)
    return parsed.scheme in {"https", "http"} and bool(parsed.netloc)


def web_research_agent(
    state: WorkflowState,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    metrics = state["telemetry"]["metrics"]
    if state["performance"]["severity"] == "healthy":
        output = WebResearchOutput(
            status="skipped_healthy",
            message="Web lookup is skipped for healthy telemetry.",
        )
        return {"web_research": output.model_dump(), **heartbeat("Web Research Agent")}

    if has_local_rule_match(metrics):
        output = WebResearchOutput(
            status="local_match_found",
            message="A local diagnostic rule matched; external search was not needed.",
        )
        return {"web_research": output.model_dump(), **heartbeat("Web Research Agent")}

    key = api_key if api_key is not None else os.getenv("TAVILY_API_KEY")
    if not key:
        output = WebResearchOutput(
            status="disabled",
            message="No TAVILY_API_KEY is configured.",
        )
        return {"web_research": output.model_dump(), **heartbeat("Web Research Agent")}

    query = _build_search_query(metrics)
    try:
        response = httpx.post(
            TAVILY_SEARCH_URL,
            json={
                "api_key": key,
                "query": query,
                "search_depth": "basic",
                "max_results": 5,
                "include_answer": False,
                "include_raw_content": False,
            },
            timeout=10,
        )
        response.raise_for_status()
        payload = response.json()
        results = payload.get("results", [])
        sources = []
        for item in results[:5]:
            url = str(item.get("url", ""))
            if not _is_web_url(url):
                continue
            sources.append(WebSource(
                source_id=len(sources),
                title=str(item.get("title") or "Untitled result")[:200],
                url=url[:2048],
                snippet=str(item.get("content") or "")[:1200],
                relevance=max(0.0, min(1.0, float(item.get("score") or 0))),
            ))
        output = WebResearchOutput(
            status="searched",
            query=query,
            sources=sources,
            message="Search results are external references, not verified device facts.",
        )
    except (httpx.HTTPError, ValueError, TypeError) as error:
        output = WebResearchOutput(
            status="unavailable",
            query=query,
            message=f"Tavily search failed ({type(error).__name__}).",
        )
    return {"web_research": output.model_dump(), **heartbeat("Web Research Agent")}
