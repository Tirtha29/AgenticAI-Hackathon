from __future__ import annotations

import csv
import io
import json
import os
import secrets
import sqlite3
import logging
from collections.abc import Generator
from contextlib import asynccontextmanager, contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Header, HTTPException, Query, UploadFile, WebSocket, WebSocketDisconnect
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import Response
from redis.asyncio import Redis
from redis.exceptions import RedisError

from backend.common.classes.api import HumanInformationIn, ReviewIn, SimulationIn, TelemetryIn
from backend.common.classes.event_hub import EventHub
from backend.common.demo_inventory import build_iit_bhubaneswar_inventory
from backend.common.metrics import ACCEPTED_UNITS, METRIC_ALIASES, METRIC_UNITS, NORMAL_RANGES
from backend.common.rules import BASE_RULES, CAUSE_RULES, FACT_CATALOG
from backend.graph import AGENT_RUNS, HEARTBEATS, WORKFLOW, run_workflow
from backend.simulation import EVENT_PRESETS, run_simulation

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "./netcoop.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "change-this-in-production")
CONNECTION_HOPS = 3
QUEUE_STREAM = os.getenv("TELEMETRY_STREAM", "netcoop:telemetry")
WORKER_HEARTBEAT_KEY = os.getenv("WORKER_HEARTBEAT_KEY", "netcoop:worker:heartbeat")
GEO_KEY = os.getenv("GEO_KEY", "netcoop:geo:devices")
DEVICE_DETAILS_KEY = os.getenv("DEVICE_DETAILS_KEY", "netcoop:device:details")
logger = logging.getLogger(__name__)
redis_client: Redis | None = None
LLM = None
if os.getenv("GROQ_API_KEY"):
    from langchain_groq import ChatGroq

    LLM = ChatGroq(
        model=os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile"),
        temperature=0,
    )


@contextmanager
def connect_db() -> Generator[sqlite3.Connection, None, None]:
    connection = sqlite3.connect(DB_PATH, timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        yield connection
        connection.commit()
    except sqlite3.Error:
        connection.rollback()
        raise
    finally:
        connection.close()


def ensure_device_columns(connection: sqlite3.Connection) -> None:
    device_columns = {
        row["name"] for row in connection.execute("PRAGMA table_info(devices)")
    }
    if "neighbors_json" not in device_columns:
        connection.execute(
            "ALTER TABLE devices ADD COLUMN neighbors_json TEXT NOT NULL DEFAULT '[]'"
        )
    if "risk_probability" not in device_columns:
        connection.execute(
            "ALTER TABLE devices ADD COLUMN risk_probability REAL NOT NULL DEFAULT 0"
        )
    if "latitude" not in device_columns:
        connection.execute("ALTER TABLE devices ADD COLUMN latitude REAL")
    if "longitude" not in device_columns:
        connection.execute("ALTER TABLE devices ADD COLUMN longitude REAL")
    if "location_known" not in device_columns:
        connection.execute("ALTER TABLE devices ADD COLUMN location_known INTEGER NOT NULL DEFAULT 0")

    if {"latitude", "longitude"} & device_columns:
        connection.execute("""
            CREATE TABLE IF NOT EXISTS devices_topology (
                device_id TEXT PRIMARY KEY, name TEXT, device_type TEXT, vendor TEXT,
                status TEXT NOT NULL DEFAULT 'unknown', last_seen TEXT,
                latitude REAL, longitude REAL, location_known INTEGER NOT NULL DEFAULT 0,
                neighbors_json TEXT NOT NULL DEFAULT '[]',
                risk_probability REAL NOT NULL DEFAULT 0
            )
        """)
        legacy_exists = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='devices_topology'"
        ).fetchone()
        if legacy_exists is not None:
            connection.execute("""
                INSERT OR IGNORE INTO devices_topology
                    (device_id, name, device_type, vendor, status, last_seen, latitude, longitude, location_known, neighbors_json, risk_probability)
                SELECT device_id, name, device_type, vendor, status, last_seen, latitude, longitude, location_known, neighbors_json, risk_probability
                FROM devices
            """)
            connection.execute("DROP TABLE devices")
            connection.execute("ALTER TABLE devices_topology RENAME TO devices")


def initialize_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY, name TEXT, device_type TEXT, vendor TEXT,
                status TEXT NOT NULL DEFAULT 'unknown', last_seen TEXT,
                latitude REAL, longitude REAL, location_known INTEGER NOT NULL DEFAULT 0,
                neighbors_json TEXT NOT NULL DEFAULT '[]',
                risk_probability REAL NOT NULL DEFAULT 0
            );
            CREATE TABLE IF NOT EXISTS telemetry (
                event_id TEXT PRIMARY KEY, device_id TEXT NOT NULL,
                timestamp TEXT NOT NULL, severity TEXT NOT NULL,
                metrics_json TEXT NOT NULL, report_json TEXT,
                queue_status TEXT NOT NULL DEFAULT 'queued'
            );
            CREATE TABLE IF NOT EXISTS reviews (
                incident_id TEXT PRIMARY KEY, reviewer TEXT NOT NULL,
                decision TEXT NOT NULL, feedback TEXT, reviewed_at TEXT NOT NULL
            );
        """)
        ensure_device_columns(connection)


hub = EventHub()


def normalize_metric(key: str, value: float, source_unit: str | None = None) -> tuple[str, float, str] | None:
    canonical = METRIC_ALIASES.get(key, key)
    if canonical not in METRIC_UNITS:
        return None
    unit = source_unit
    if unit is None:
        unit = {
            "latency_s": "s",
            "jitter_s": "s",
            "cpu_utilization": "fraction" if 0 <= value <= 1 else "%",
            "memory_utilization": "fraction" if 0 <= value <= 1 else "%",
            "link_utilization": "fraction" if 0 <= value <= 1 else "%",
        }.get(key, METRIC_UNITS[canonical])
    conversion = ACCEPTED_UNITS[canonical].get(unit)
    if conversion is None:
        choices = ", ".join(ACCEPTED_UNITS[canonical])
        raise HTTPException(status_code=422, detail=f"Unsupported unit '{unit}' for {key}; accepted units: {choices}")
    normalized = float(value) * conversion
    if canonical.endswith("_pct") and not 0 <= normalized <= 100:
        raise HTTPException(status_code=422, detail=f"{key} must normalize to a value between 0 and 100")
    if normalized < 0:
        raise HTTPException(status_code=422, detail=f"{key} cannot be negative")
    return canonical, round(normalized, 3), unit


def normalize_payload(payload: TelemetryIn) -> dict[str, Any]:
    metrics = {}
    source_units = {}
    accepted_unit_keys = {
        key
        for metric in payload.metrics
        for key in (metric, METRIC_ALIASES.get(metric, metric))
    }
    unused_units = set(payload.units) - accepted_unit_keys
    if unused_units:
        raise HTTPException(
            status_code=422,
            detail=f"Units were supplied without matching metrics: {', '.join(sorted(unused_units))}",
        )
    for key, value in payload.metrics.items():
        canonical = METRIC_ALIASES.get(key, key)
        supplied_unit = payload.units.get(key, payload.units.get(canonical))
        normalized = normalize_metric(key, value, supplied_unit)
        if normalized is None:
            raise HTTPException(status_code=422, detail=f"Unsupported telemetry metric: {key}")
        metrics[normalized[0]] = normalized[1]
        source_units[normalized[0]] = normalized[2]
    timestamp = payload.timestamp or datetime.now(timezone.utc)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=timezone.utc)
    timestamp = timestamp.astimezone(timezone.utc).isoformat()
    return {
        "event_id": str(uuid4()),
        "timestamp": timestamp,
        "device_id": payload.device_id.strip(),
        "metrics": metrics,
        "units": {key: METRIC_UNITS[key] for key in metrics},
        "source_units": source_units,
        "severity": "healthy",
    }


@asynccontextmanager
async def lifespan(_: FastAPI):
    global redis_client
    initialize_db()
    owns_redis_client = redis_client is None
    if owns_redis_client:
        redis_client = Redis.from_url(REDIS_URL, decode_responses=True)
    try:
        yield
    finally:
        if owns_redis_client and redis_client is not None:
            await redis_client.aclose()
            redis_client = None


app = FastAPI(title="NetCoop AI API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
async def health() -> dict[str, Any]:
    now = datetime.now(timezone.utc)
    graph_nodes = set(WORKFLOW.get_graph().nodes)
    graph_node_by_agent = {
        "Normalization Agent": "normalization",
        "Performance Agent": "performance",
        "Infrastructure Agent": "infrastructure",
        "Health Check Agent": "health",
        "Connectivity Agent": "connectivity",
        "UTM Agent": "utm",
        "Web Research Agent": "web_research",
        "Correlation Agent": "correlation",
        "Reporting Agent": "reporting",
    }
    queue_status = "unavailable"
    worker_status = "unavailable"
    try:
        if redis_client is None:
            raise RedisError("Redis connection is not initialized")
        await redis_client.ping()
        queue_status = "healthy"
        worker_status = "healthy" if await redis_client.exists(WORKER_HEARTBEAT_KEY) else "unavailable"
    except RedisError:
        queue_status = "unavailable"
    database_status = "healthy"
    try:
        with connect_db() as connection:
            connection.execute("SELECT 1")
    except sqlite3.Error:
        database_status = "unavailable"
    agents = {}
    for name, graph_node in graph_node_by_agent.items():
        run_details = AGENT_RUNS.get(name, {})
        last_execution = HEARTBEATS.get(name)
        if graph_node not in graph_nodes:
            agent_status = "unavailable"
        elif run_details and not run_details["last_run_succeeded"]:
            agent_status = "degraded"
        elif last_execution is None:
            agent_status = "ready"
        elif (now - last_execution).total_seconds() <= 300:
            agent_status = "healthy"
        else:
            agent_status = "stale"
        agents[name] = {
            "status": agent_status,
            "last_execution": last_execution.isoformat() if last_execution else None,
            "latency_ms": run_details.get("latency_ms"),
            "last_run_succeeded": run_details.get("last_run_succeeded"),
        }
    agents_ready = all(agent["status"] in {"ready", "healthy"} for agent in agents.values())
    common_agent_status = (
        "healthy"
        if queue_status == "healthy" and worker_status == "healthy" and database_status == "healthy" and agents_ready
        else "degraded"
    )
    agents["Common Monitoring Agent"] = {
        "status": common_agent_status,
        "last_check": now.isoformat(),
    }
    return {
        "status": common_agent_status,
        "common_monitoring_agent": common_agent_status,
        "agents": agents,
        "queue": queue_status,
        "worker": worker_status,
        "database": database_status,
        "cause_scoring": "groq_configured" if LLM is not None else "static_fallback",
        "web_research": "tavily_configured" if os.getenv("TAVILY_API_KEY") else "disabled",
        "diagnostic_rules": len(BASE_RULES) + len(CAUSE_RULES),
        "static_rules": len(FACT_CATALOG),
    }


@app.get("/telemetry/schema")
async def telemetry_schema() -> dict[str, Any]:
    return {
        "unit_policy": "Send the source unit per metric in the units object. Values are converted to these canonical units before agent analysis.",
        "metrics": {
            metric: {
                "canonical_unit": unit,
                "accepted_input_units": list(ACCEPTED_UNITS[metric]),
                "normal_range": {
                    "minimum": NORMAL_RANGES[metric].minimum,
                    "maximum": NORMAL_RANGES[metric].maximum,
                    "unit": NORMAL_RANGES[metric].unit,
                },
            }
            for metric, unit in METRIC_UNITS.items()
        },
        "example": {
            "device_id": "RTR_CAMPUS_1",
            "metrics": {"bandwidth": 2.5, "latency_ms": 35},
            "units": {"bandwidth": "Gbps", "latency_ms": "ms"},
        },
    }


@app.post("/telemetry", status_code=202)
async def ingest_telemetry(payload: TelemetryIn) -> dict[str, Any]:
    event = normalize_payload(payload)
    with connect_db() as connection:
        connection.execute(
            """INSERT INTO telemetry(event_id, device_id, timestamp, severity, metrics_json)
               VALUES (?, ?, ?, ?, ?)""",
            (event["event_id"], event["device_id"], event["timestamp"], event["severity"], json.dumps(event["metrics"])),
        )
    try:
        if redis_client is None:
            raise RedisError("Redis connection is not initialized")
        await redis_client.xadd(QUEUE_STREAM, {"payload": json.dumps(event)})
    except RedisError as error:
        with connect_db() as connection:
            connection.execute("UPDATE telemetry SET queue_status='enqueue_failed' WHERE event_id=?", (event["event_id"],))
        logger.exception("Unable to enqueue telemetry event %s", event["event_id"])
        raise HTTPException(status_code=503, detail=f"Telemetry stored but Redis enqueue failed: {error}") from error
    await hub.broadcast({"type": "telemetry_queued", "event_id": event["event_id"], "device_id": event["device_id"], "severity": event["severity"]})
    return {
        "event_id": event["event_id"],
        "status": "queued",
        "severity": "pending_analysis",
        "units": event["units"],
    }


@app.post("/internal/process")
async def process_telemetry(
    event: dict[str, Any],
    x_internal_token: str | None = Header(default=None),
) -> dict[str, Any]:
    if not x_internal_token or not secrets.compare_digest(x_internal_token, INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="Invalid internal worker token")
    event["units"] = {metric: METRIC_UNITS[metric] for metric in event["metrics"]}
    with connect_db() as connection:
        existing = connection.execute(
            "SELECT queue_status, report_json FROM telemetry WHERE event_id=?", (event["event_id"],)
        ).fetchone()
        if existing is None:
            raise HTTPException(status_code=404, detail="Telemetry event was not found")
        if existing["queue_status"] in {"processed", "needs_human"}:
            return {"status": existing["queue_status"], "event_id": event["event_id"]}
        device_row = connection.execute("SELECT * FROM devices WHERE device_id=?", (event["device_id"],)).fetchone()
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        history_rows = connection.execute(
            """SELECT timestamp, metrics_json FROM telemetry
               WHERE device_id=? AND event_id != ? AND timestamp >= ? AND report_json IS NOT NULL
               ORDER BY timestamp DESC LIMIT 100""",
            (event["device_id"], event["event_id"], cutoff),
        ).fetchall()
        history = [
            {"timestamp": row["timestamp"], "metrics": json.loads(row["metrics_json"])}
            for row in history_rows
        ]
        device = dict(device_row) if device_row else {}
        inventory_rows = connection.execute(
            "SELECT device_id, name, device_type, status, neighbors_json FROM devices ORDER BY device_id"
        ).fetchall()
        device_inventory = [dict(row) for row in inventory_rows]
        window_rows = connection.execute(
            """SELECT t.device_id, t.timestamp, t.severity, t.metrics_json,
                      d.device_type
               FROM telemetry t LEFT JOIN devices d ON d.device_id=t.device_id
               WHERE t.timestamp >= ? AND t.report_json IS NOT NULL
               ORDER BY t.timestamp DESC LIMIT 1000""",
            (cutoff,),
        ).fetchall()
        telemetry_window = [
            {
                "device_id": row["device_id"],
                "timestamp": row["timestamp"],
                "severity": row["severity"],
                "metrics": json.loads(row["metrics_json"]),
                "device_type": row["device_type"] or "network device",
            }
            for row in window_rows
        ]
    report = await run_in_threadpool(
        run_workflow,
        event=event,
        device=device,
        history=history,
        telemetry_window=telemetry_window,
        device_inventory=device_inventory,
        connection_hops=CONNECTION_HOPS,
        llm=LLM,
    )
    queue_status = "needs_human" if report["human_questions"] else "processed"
    with connect_db() as connection:
        connection.execute(
            "UPDATE telemetry SET queue_status=?, severity=?, report_json=? WHERE event_id=?",
            (queue_status, report["severity"], json.dumps(report), event["event_id"]),
        )
        connection.execute(
            """INSERT OR IGNORE INTO devices(device_id, status, last_seen)
               VALUES (?, ?, ?)""",
            (event["device_id"], report["severity"], event["timestamp"]),
        )
        processed_ids = set()
        for issue in report.get("device_statuses", []):
            device_id = issue.get("device_id")
            if not device_id:
                continue
            processed_ids.add(device_id)
            connection.execute(
                "UPDATE devices SET status=?, risk_probability=?, last_seen=? WHERE device_id=?",
                (issue["severity"], issue["probability"], event["timestamp"], device_id),
            )
        if event["device_id"] not in processed_ids:
            connection.execute(
                "UPDATE devices SET status=?, risk_probability=?, last_seen=? WHERE device_id=?",
                (
                    report["severity"],
                    0.96 if report["severity"] == "critical" else (0.78 if report["severity"] == "warning" else 0.05),
                    event["timestamp"],
                    event["device_id"],
                ),
            )
    await hub.broadcast({"type": "incident_report", "incident": report})
    return {"status": queue_status, "event_id": event["event_id"]}


def parse_inventory(data: bytes, filename: str) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8-sig")
        if filename.lower().endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(text)))
        elif filename.lower().endswith(".json"):
            source = json.loads(text)
            rows = source if isinstance(source, list) else source.get("devices", [])
            if not isinstance(rows, list):
                raise HTTPException(status_code=400, detail="JSON inventory must be a list of devices or contain a devices list")
        else:
            raise HTTPException(status_code=415, detail="Upload a CSV or JSON topology inventory")
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as error:
        raise HTTPException(status_code=400, detail=f"Invalid inventory file: {error}") from error
    devices = []
    for row in rows:
        device_id = str(row.get("device_id") or row.get("id") or "").strip()
        if not device_id:
            continue
        raw_connections = (
            row.get("connected_to")
            or row.get("neighbors")
            or row.get("connections")
            or row.get("neighbors_json")
            or []
        )
        if isinstance(raw_connections, str):
            try:
                parsed_connections = json.loads(raw_connections)
            except json.JSONDecodeError:
                parsed_connections = None
            if isinstance(parsed_connections, list):
                raw_connections = parsed_connections
        if isinstance(raw_connections, str):
            connections = [
                item.strip()
                for item in raw_connections.replace(",", ";").split(";")
                if item.strip()
            ]
        elif isinstance(raw_connections, list):
            connections = [str(item).strip() for item in raw_connections if str(item).strip()]
        else:
            raise HTTPException(
                status_code=422,
                detail=f"Connections for {device_id} must be a list or semicolon-separated string.",
            )
        if device_id in connections:
            raise HTTPException(status_code=422, detail=f"Device {device_id} cannot connect to itself.")
        latitude = row.get("latitude")
        longitude = row.get("longitude")
        location_known = 0
        if latitude is not None and longitude is not None:
            try:
                latitude = float(latitude)
                longitude = float(longitude)
                if -90 <= latitude <= 90 and -180 <= longitude <= 180:
                    location_known = 1
            except (TypeError, ValueError):
                latitude = None
                longitude = None
        device_data = {
            "device_id": device_id,
            "name": str(row.get("name") or device_id),
            "device_type": str(row.get("device_type") or "network device").lower(),
            "vendor": str(row.get("vendor") or ""),
            "location_known": location_known,
            "neighbors_json": json.dumps(sorted(set(connections))),
        }
        if latitude is not None:
            device_data["latitude"] = latitude
        if longitude is not None:
            device_data["longitude"] = longitude
        devices.append(device_data)
    if not devices:
        raise HTTPException(status_code=422, detail="No valid devices found; each row needs a device_id.")
    if len({device["device_id"] for device in devices}) != len(devices):
        raise HTTPException(status_code=422, detail="Device IDs must be unique within an inventory upload.")
    return devices


@app.post("/devices/upload")
async def upload_inventory(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Inventory upload must be 10 MB or smaller")
    devices = parse_inventory(data, file.filename or "")
    with connect_db() as connection:
        existing_ids = {
            row["device_id"] for row in connection.execute("SELECT device_id FROM devices")
        }
        uploaded_ids = {device["device_id"] for device in devices}
        unknown = sorted({
            neighbor
            for device in devices
            for neighbor in json.loads(device["neighbors_json"])
            if neighbor not in existing_ids | uploaded_ids
        })
        if unknown:
            raise HTTPException(
                status_code=422,
                detail=f"Connections reference unknown device IDs: {', '.join(unknown)}",
            )
        connection.executemany(
            """INSERT INTO devices(device_id, name, device_type, vendor, status, latitude, longitude, location_known, neighbors_json)
               VALUES (:device_id, :name, :device_type, :vendor, 'unknown', :latitude, :longitude, :location_known, :neighbors_json)
               ON CONFLICT(device_id) DO UPDATE SET name=excluded.name, device_type=excluded.device_type,
               vendor=excluded.vendor, latitude=excluded.latitude, longitude=excluded.longitude,
               location_known=excluded.location_known, neighbors_json=excluded.neighbors_json""",
            devices,
        )
    return {"uploaded": len(devices), "device_ids": [device["device_id"] for device in devices]}


@app.post("/devices/demo/iit-bhubaneswar")
async def load_iit_bhubaneswar_demo_inventory() -> dict[str, Any]:
    devices = build_iit_bhubaneswar_inventory()
    with connect_db() as connection:
        connection.execute("DELETE FROM devices")
        connection.executemany(
            """INSERT INTO devices(device_id, name, device_type, vendor, status, latitude, longitude, location_known, neighbors_json)
               VALUES (:device_id, :name, :device_type, :vendor, 'unknown', :latitude, :longitude, :location_known, :neighbors_json)
               ON CONFLICT(device_id) DO UPDATE SET name=excluded.name, device_type=excluded.device_type,
               vendor=excluded.vendor, latitude=excluded.latitude, longitude=excluded.longitude,
               location_known=excluded.location_known, neighbors_json=excluded.neighbors_json""",
            devices,
        )
    if redis_client is not None:
        await redis_client.delete(GEO_KEY, DEVICE_DETAILS_KEY)
    return {
        "site": "IIT Bhubaneswar",
        "synthetic": True,
        "replaced_existing_inventory": True,
        "uploaded": len(devices),
        "device_ids": [device["device_id"] for device in devices],
    }


@app.get("/simulation/presets")
async def simulation_presets() -> dict[str, Any]:
    return {"presets": EVENT_PRESETS}


@app.post("/simulation/run")
async def simulate_event(scenario: SimulationIn) -> dict[str, Any]:
    """Run a deterministic what-if simulation without changing inventory or telemetry."""
    with connect_db() as connection:
        rows = connection.execute(
            """SELECT device_id, name, device_type, status, neighbors_json
               FROM devices ORDER BY device_id"""
        ).fetchall()
    devices = [dict(row) for row in rows]
    if not devices:
        raise HTTPException(
            status_code=409,
            detail="Load or upload a connected-device inventory before simulating an event.",
        )
    try:
        return await run_in_threadpool(run_simulation, devices, scenario.model_dump())
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error


@app.get("/overview")
async def overview() -> dict[str, Any]:
    with connect_db() as connection:
        devices = [dict(row) for row in connection.execute("SELECT * FROM devices ORDER BY device_id")]
        events = connection.execute(
            "SELECT report_json, queue_status, event_id, device_id, timestamp FROM telemetry ORDER BY timestamp DESC LIMIT 100"
        ).fetchall()
    incidents = []
    for row in events:
        if row["report_json"]:
            incident = json.loads(row["report_json"])
            review = None
            with connect_db() as connection:
                review = connection.execute("SELECT * FROM reviews WHERE incident_id=?", (row["event_id"],)).fetchone()
            if review:
                incident["human_review"] = {
                    "status": review["decision"], "reviewer": review["reviewer"], "feedback": review["feedback"],
                }
            incidents.append(incident)
    return {"devices": devices, "incidents": incidents, "queued": sum(row["queue_status"] == "queued" for row in events)}


@app.get("/knowledge/rules")
async def search_knowledge_rules(
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=50, ge=1, le=100),
) -> dict[str, Any]:
    search = q.strip().casefold()
    rules = [
        {
            "rule_id": rule["id"],
            "cause": rule["cause"],
            "metrics": sorted(rule["required"]),
            "thresholds": rule["required"],
            "confidence": rule["probability"],
            "recommended_action": rule["action"],
            "kind": "correlation",
        }
        for rule in BASE_RULES
    ]
    rules.extend(
        {
            "rule_id": fact["fact_id"],
            "cause": fact["cause"],
            "metrics": [fact["metric"]],
            "thresholds": {fact["metric"]: fact["threshold"]},
            "confidence": 0.88,
            "recommended_action": fact["action"],
            "kind": "fact",
            "device_role": fact["device_role"],
            "vendor_context": fact["vendor_context"],
        }
        for fact in FACT_CATALOG
    )
    matching = [
        rule for rule in rules
        if not search or search in json.dumps(rule, ensure_ascii=False).casefold()
    ]
    return {
        "query": q,
        "total": len(matching),
        "rules": matching[:limit],
    }


@app.post("/incidents/{incident_id}/review")
async def review_incident(incident_id: str, review: ReviewIn) -> dict[str, Any]:
    now = datetime.now(timezone.utc).isoformat()
    with connect_db() as connection:
        row = connection.execute("SELECT report_json FROM telemetry WHERE event_id=?", (incident_id,)).fetchone()
        if row is None or row["report_json"] is None:
            raise HTTPException(status_code=404, detail="Processed incident was not found")
        report = json.loads(row["report_json"])
        if report["conclusion"] != "probable_causes_ranked" or not report["probable_causes"]:
            raise HTTPException(status_code=409, detail="A diagnosis cannot be reviewed until a cause meets the 90% confidence threshold")
        connection.execute(
            """INSERT INTO reviews(incident_id, reviewer, decision, feedback, reviewed_at)
               VALUES (?, ?, ?, ?, ?) ON CONFLICT(incident_id) DO UPDATE SET reviewer=excluded.reviewer,
               decision=excluded.decision, feedback=excluded.feedback, reviewed_at=excluded.reviewed_at""",
            (incident_id, review.reviewer, review.decision, review.feedback, now),
        )
    await hub.broadcast({"type": "incident_review", "incident_id": incident_id, "decision": review.decision})
    return {"incident_id": incident_id, "decision": review.decision, "reviewed_at": now}


def load_incident_context(
    event_id: str,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    with connect_db() as connection:
        row = connection.execute(
            """SELECT event_id, device_id, timestamp, severity, metrics_json, queue_status
               FROM telemetry WHERE event_id=?""",
            (event_id,),
        ).fetchone()
        if row is None:
            raise HTTPException(status_code=404, detail="Incident was not found")
        event = {
            "event_id": row["event_id"],
            "device_id": row["device_id"],
            "timestamp": row["timestamp"],
            "metrics": json.loads(row["metrics_json"]),
            "units": {key: METRIC_UNITS[key] for key in json.loads(row["metrics_json"])},
            "severity": row["severity"],
        }
        device_row = connection.execute("SELECT * FROM devices WHERE device_id=?", (row["device_id"],)).fetchone()
        device = dict(device_row) if device_row else {}
        inventory_rows = connection.execute(
            "SELECT device_id, name, device_type, status, neighbors_json FROM devices ORDER BY device_id"
        ).fetchall()
        device_inventory = [dict(item) for item in inventory_rows]
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        historical_rows = connection.execute(
            """SELECT timestamp, metrics_json FROM telemetry WHERE device_id=?
               AND event_id != ? AND timestamp >= ? AND report_json IS NOT NULL
               ORDER BY timestamp DESC LIMIT 100""",
            (row["device_id"], event_id, cutoff),
        ).fetchall()
        history = [
            {"timestamp": item["timestamp"], "metrics": json.loads(item["metrics_json"])}
            for item in historical_rows
        ]
        window_rows = connection.execute(
            """SELECT t.device_id, t.timestamp, t.severity, t.metrics_json,
                      d.device_type
               FROM telemetry t LEFT JOIN devices d ON d.device_id=t.device_id
               WHERE t.timestamp >= ? AND t.event_id != ? AND t.report_json IS NOT NULL
               ORDER BY t.timestamp DESC LIMIT 1000""",
            (cutoff, event_id),
        ).fetchall()
        telemetry_window = [
            {
                "device_id": item["device_id"],
                "timestamp": item["timestamp"],
                "severity": item["severity"],
                "metrics": json.loads(item["metrics_json"]),
                "device_type": item["device_type"] or "network device",
            }
            for item in window_rows
        ]
    return event, device, history, telemetry_window, device_inventory


@app.post("/incidents/{incident_id}/information")
async def provide_incident_information(
    incident_id: str,
    information: HumanInformationIn,
) -> dict[str, Any]:
    with connect_db() as connection:
        incident_row = connection.execute(
            "SELECT queue_status, report_json FROM telemetry WHERE event_id=?",
            (incident_id,),
        ).fetchone()
    if incident_row is None or incident_row["report_json"] is None:
        raise HTTPException(status_code=404, detail="Processed incident was not found")
    if incident_row["queue_status"] != "needs_human":
        raise HTTPException(status_code=409, detail="This incident is not awaiting client information")
    previous_report = json.loads(incident_row["report_json"])
    event, device, history, telemetry_window, device_inventory = load_incident_context(incident_id)
    answers = {
        **previous_report.get("human_answers", {}),
        **information.answers,
    }
    if isinstance(answers.get("firewall_drops"), (int, float)):
        event["metrics"]["firewall_drops"] = float(answers["firewall_drops"])
        event["units"]["firewall_drops"] = "events"
    if answers.get("firewall_alerts") is True or answers.get("utm_alerts") is True:
        answers["utm_alerts"] = True
    event_context = (
        information.event_context.model_dump(exclude_none=True)
        if information.event_context is not None
        else previous_report.get("event_context")
    )
    event_simulation = None
    if event_context and event_context.get("event_happening"):
        scenario = {
            key: value
            for key, value in event_context.items()
            if key != "event_happening"
        }
        try:
            event_simulation = await run_in_threadpool(
                run_simulation, device_inventory, scenario
            )
        except ValueError as error:
            raise HTTPException(status_code=422, detail=str(error)) from error
    report = await run_in_threadpool(
        run_workflow,
        event=event,
        device=device,
        history=history,
        telemetry_window=telemetry_window,
        human_answers=answers,
        device_inventory=device_inventory,
        connection_hops=CONNECTION_HOPS,
        llm=LLM,
        event_context=event_context,
        event_simulation=event_simulation,
    )
    queue_status = "needs_human" if report["human_questions"] else "processed"
    with connect_db() as connection:
        connection.execute(
            "UPDATE telemetry SET queue_status=?, report_json=? WHERE event_id=?",
            (queue_status, json.dumps(report), incident_id),
        )
        processed_ids = set()
        for issue in report.get("device_statuses", []):
            device_id = issue.get("device_id")
            if not device_id:
                continue
            processed_ids.add(device_id)
            connection.execute(
                "UPDATE devices SET status=?, risk_probability=?, last_seen=? WHERE device_id=?",
                (issue["severity"], issue["probability"], event["timestamp"], device_id),
            )
        if event["device_id"] not in processed_ids:
            connection.execute(
                "UPDATE devices SET status=?, risk_probability=?, last_seen=? WHERE device_id=?",
                (
                    report["severity"],
                    0.96 if report["severity"] == "critical" else (0.78 if report["severity"] == "warning" else 0.05),
                    event["timestamp"],
                    event["device_id"],
                ),
            )
    await hub.broadcast({"type": "incident_report", "incident": report})
    return {"incident_id": incident_id, "status": queue_status, "report": report}


@app.get("/incidents/{incident_id}/report")
async def download_incident_report(incident_id: str) -> Response:
    with connect_db() as connection:
        row = connection.execute(
            "SELECT report_json FROM telemetry WHERE event_id=?",
            (incident_id,),
        ).fetchone()
    if row is None or row["report_json"] is None:
        raise HTTPException(status_code=404, detail="Incident report was not found")
    report = json.loads(row["report_json"])
    lines = [
        f"# Network Incident Report: {report['incident_id']}",
        "",
        f"- **Timestamp:** {report['timestamp']}",
        f"- **Severity:** {report['severity']}",
        f"- **Conclusion:** {report['conclusion']}",
        f"- **Confidence threshold:** {report['confidence_threshold']:.0%}",
        f"- **Scoring method:** `{report.get('scoring_method', 'static_fallback')}`",
        f"- **Scoring weights:** {', '.join(f'{name}={value:.0%}' for name, value in report.get('scoring_weights', {}).items())}",
        "",
        report["summary"],
        "",
        "## Ranked probable causes",
    ]
    if report["probable_causes"]:
        for index, cause in enumerate(report["probable_causes"], 1):
            lines.extend([
                f"### {index}. {cause['cause']} — {cause['probability']:.0%}",
                f"- Rule: `{cause['rule_id']}`",
                *(
                    [f"- Score factors: {', '.join(f'{name}={value:.0%}' for name, value in cause['score_breakdown'].items())}"]
                    if cause.get("score_breakdown") else []
                ),
                f"- Evidence: {'; '.join(cause['evidence'])}",
                f"- Recommended action: {cause['recommended_action']}",
                *(
                    [f"- Sources: {', '.join(source['url'] for source in cause['sources'])}"]
                    if cause.get("sources") else []
                ),
            ])
    else:
        lines.append("No cause met the required 90% confidence.")
    if report["unverified_candidates"]:
        lines.extend(["", "## Unverified candidates (below threshold)", ""])
        lines.extend(
            f"- {cause['cause']} — {cause['probability']:.0%}; "
            f"evidence: {'; '.join(cause['evidence'])}"
            for cause in report["unverified_candidates"]
        )
    web_research = report.get("web_research", {})
    if web_research.get("sources"):
        lines.extend(["", "## External research (unverified)", ""])
        lines.extend(
            f"- [{source['title']}]({source['url']}): {source['snippet']}"
            for source in web_research["sources"]
        )
    lines.extend(["", "## Device issue map input", ""])
    for device in report["issue_devices"]:
        hops = device.get("connection_hops")
        lines.append(
            f"- `{device['device_id']}` ({device['device_type']}) — "
            f"{device['probability']:.0%} risk, {device['severity']}"
            + (f", {hops} topology hop(s)" if hops is not None else "")
        )
    if report.get("event_simulation"):
        lines.extend(["", "## Event simulation"])
        simulation_summary = report["event_simulation"]["summary"]
        lines.append(
            f"Predicted {simulation_summary['critical']} critical and "
            f"{simulation_summary['warning']} warning device(s) around "
            f"{report['event_context']['anchor_device_id']}."
        )
        for recommendation in report["event_simulation"]["recommendations"]:
            lines.append(f"- **{recommendation['title']}:** {recommendation['action']}")
    lines.extend(["", "## Human-in-the-loop", ""])
    lines.extend(f"- {question}" for question in report["human_questions"])
    lines.extend(["", "## Limitations", "", report["limitations"], ""])
    return Response(
        content="\n".join(lines),
        media_type="text/markdown",
        headers={"Content-Disposition": f'attachment; filename="incident-{incident_id}.md"'},
    )


@app.websocket("/ws/events")
async def websocket_events(socket: WebSocket) -> None:
    await hub.connect(socket)
    try:
        while True:
            await socket.receive_text()
    except WebSocketDisconnect:
        hub.disconnect(socket)
