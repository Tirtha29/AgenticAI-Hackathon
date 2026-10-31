from datetime import datetime, timezone


def heartbeat(name: str) -> dict[str, dict[str, str]]:
    return {"agent_heartbeat": {name: datetime.now(timezone.utc).isoformat()}}
