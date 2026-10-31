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
from redis import Redis as SyncRedis
from redis.asyncio import Redis
from redis.exceptions import RedisError

from backend.common.classes.api import HumanInformationIn, ReviewIn, TelemetryIn
from backend.common.classes.event_hub import EventHub
from backend.common.demo_inventory import build_iit_bhubaneswar_inventory
from backend.common.metrics import ACCEPTED_UNITS, METRIC_ALIASES, METRIC_UNITS, NORMAL_RANGES
from backend.common.rules import BASE_RULES, FACT_CATALOG
from backend.graph import AGENT_RUNS, HEARTBEATS, WORKFLOW, run_workflow

load_dotenv()

DB_PATH = os.getenv("DATABASE_PATH", "./netcoop.db")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "change-this-in-production")
BLAST_RADIUS_KM = float(os.getenv("BLAST_RADIUS_KM", "5"))
QUEUE_STREAM = os.getenv("TELEMETRY_STREAM", "netcoop:telemetry")
GEO_KEY = os.getenv("REDIS_GEO_KEY", "netcoop:device-coordinates")
DEVICE_DETAILS_KEY = os.getenv("REDIS_DEVICE_DETAILS_KEY", "netcoop:device-details")
WORKER_HEARTBEAT_KEY = os.getenv("WORKER_HEARTBEAT_KEY", "netcoop:worker:heartbeat")
logger = logging.getLogger(__name__)
redis_client: Redis | None = None
LLM = None
if os.getenv("OPENAI_API_KEY"):
    from langchain_openai import ChatOpenAI

    LLM = ChatOpenAI(model=os.getenv("OPENAI_MODEL", "gpt-4o-mini"), temperature=0)


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


def initialize_db() -> None:
    Path(DB_PATH).parent.mkdir(parents=True, exist_ok=True)
    with connect_db() as connection:
        connection.executescript("""
            CREATE TABLE IF NOT EXISTS devices (
                device_id TEXT PRIMARY KEY, name TEXT, latitude REAL NOT NULL,
                longitude REAL NOT NULL, device_type TEXT, vendor TEXT,
                status TEXT NOT NULL DEFAULT 'unknown', last_seen TEXT,
                neighbors_json TEXT NOT NULL DEFAULT '[]',
                location_known INTEGER NOT NULL DEFAULT 0,
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
        device_columns = {
            row["name"] for row in connection.execute("PRAGMA table_info(devices)")
        }
        if "neighbors_json" not in device_columns:
            connection.execute(
                "ALTER TABLE devices ADD COLUMN neighbors_json TEXT NOT NULL DEFAULT '[]'"
            )
        if "location_known" not in device_columns:
            connection.execute(
                "ALTER TABLE devices ADD COLUMN location_known INTEGER NOT NULL DEFAULT 0"
            )
        if "risk_probability" not in device_columns:
            connection.execute(
                "ALTER TABLE devices ADD COLUMN risk_probability REAL NOT NULL DEFAULT 0"
            )


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


def redis_geo_lookup(longitude: float, latitude: float, radius_km: float) -> list[dict[str, Any]]:
    with SyncRedis.from_url(REDIS_URL, decode_responses=True, socket_timeout=5) as client:
        results = client.execute_command(
            "GEOSEARCH",
            GEO_KEY,
            "FROMLONLAT",
            longitude,
            latitude,
            "BYRADIUS",
            radius_km,
            "km",
            "WITHDIST",
            "WITHCOORD",
            "ASC",
            "COUNT",
            200,
        )
        devices = []
        for device_id, distance_km, coordinates in results:
            details = client.hget(DEVICE_DETAILS_KEY, device_id)
            metadata = json.loads(details) if details else {}
            devices.append({
                "device_id": device_id,
                "distance_km": float(distance_km),
                "longitude": float(coordinates[0]),
                "latitude": float(coordinates[1]),
                "device_type": metadata.get("device_type", "network device"),
                "name": metadata.get("name", device_id),
            })
        return devices


async def index_devices(devices: list[dict[str, Any]]) -> None:
    if redis_client is None:
        raise RedisError("Redis connection is not initialized")
    async with redis_client.pipeline(transaction=False) as pipeline:
        for device in devices:
            pipeline.execute_command(
                "GEOADD",
                GEO_KEY,
                device["longitude"],
                device["latitude"],
                str(device["device_id"]),
            )
            pipeline.hset(
                DEVICE_DETAILS_KEY,
                str(device["device_id"]),
                json.dumps({
                    "name": device["name"],
                    "device_type": device["device_type"],
                }),
            )
        await pipeline.execute()


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
        window_rows = connection.execute(
            """SELECT t.device_id, t.timestamp, t.severity, t.metrics_json,
                      d.device_type, d.latitude, d.longitude, d.location_known
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
                "latitude": row["latitude"] or 0,
                "longitude": row["longitude"] or 0,
                "location_known": bool(row["location_known"]),
            }
            for row in window_rows
        ]
    report = await run_in_threadpool(
        run_workflow,
        event,
        device,
        history,
        telemetry_window,
        {},
        redis_geo_lookup,
        BLAST_RADIUS_KM,
        LLM,
    )
    queue_status = "needs_human" if report["human_questions"] else "processed"
    with connect_db() as connection:
        connection.execute(
            "UPDATE telemetry SET queue_status=?, severity=?, report_json=? WHERE event_id=?",
            (queue_status, report["severity"], json.dumps(report), event["event_id"]),
        )
        stale_cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        connection.execute(
            """UPDATE devices SET risk_probability=0,
               status=CASE WHEN last_seen >= ? THEN 'healthy' ELSE 'unknown' END""",
            (stale_cutoff,),
        )
        connection.execute(
            """INSERT OR IGNORE INTO devices(device_id, latitude, longitude, status, last_seen)
               VALUES (?, 0, 0, ?, ?)""",
            (event["device_id"], report["severity"], event["timestamp"]),
        )
        for issue in report["device_statuses"]:
            connection.execute(
                "UPDATE devices SET status=?, risk_probability=? WHERE device_id=?",
                (issue["severity"], issue["probability"], issue["device_id"]),
            )
        connection.execute(
            "UPDATE devices SET status=?, risk_probability=?, last_seen=? WHERE device_id=?",
            (report["severity"], 0.96 if report["severity"] == "critical" else (0.78 if report["severity"] == "warning" else 0.05), event["timestamp"], event["device_id"]),
        )
    await hub.broadcast({"type": "incident_report", "incident": report})
    return {"status": queue_status, "event_id": event["event_id"]}


def parse_inventory(data: bytes, filename: str) -> list[dict[str, Any]]:
    try:
        text = data.decode("utf-8-sig")
        if filename.lower().endswith((".geojson", ".json")):
            source = json.loads(text)
            features = source.get("features", []) if source.get("type") == "FeatureCollection" else [source]
            rows = []
            for feature in features:
                properties = feature.get("properties") or {}
                geometry = feature.get("geometry") or {}
                if geometry.get("type") != "Point" or len(geometry.get("coordinates", [])) < 2:
                    continue
                longitude, latitude = geometry["coordinates"][:2]
                rows.append({**properties, "latitude": latitude, "longitude": longitude})
        elif filename.lower().endswith(".csv"):
            rows = list(csv.DictReader(io.StringIO(text)))
        else:
            raise HTTPException(status_code=415, detail="Upload a CSV or GeoJSON file")
    except (UnicodeDecodeError, json.JSONDecodeError, csv.Error) as error:
        raise HTTPException(status_code=400, detail=f"Invalid inventory file: {error}") from error
    devices = []
    for row in rows:
        device_id = str(row.get("device_id") or row.get("id") or "").strip()
        try:
            latitude = float(row["latitude"])
            longitude = float(row["longitude"])
        except (KeyError, TypeError, ValueError):
            continue
        if not device_id or not -90 <= latitude <= 90 or not -180 <= longitude <= 180:
            continue
        devices.append({
            "device_id": device_id,
            "name": str(row.get("name") or device_id),
            "latitude": latitude,
            "longitude": longitude,
            "device_type": str(row.get("device_type") or "network device").lower(),
            "vendor": str(row.get("vendor") or ""),
            "neighbors_json": json.dumps(
                row.get("neighbors", [])
                if isinstance(row.get("neighbors"), list)
                else [item.strip() for item in str(row.get("neighbors") or "").split(";") if item.strip()]
            ),
        })
    if not devices:
        raise HTTPException(status_code=422, detail="No valid devices found; each row needs a device_id and valid latitude/longitude")
    return devices


@app.post("/devices/upload")
async def upload_inventory(file: UploadFile = File(...)) -> dict[str, Any]:
    data = await file.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="Inventory upload must be 10 MB or smaller")
    devices = parse_inventory(data, file.filename or "")
    with connect_db() as connection:
        connection.executemany(
            """INSERT INTO devices(device_id, name, latitude, longitude, device_type, vendor, status,
               neighbors_json, location_known)
               VALUES (:device_id, :name, :latitude, :longitude, :device_type, :vendor, 'unknown', :neighbors_json, 1)
               ON CONFLICT(device_id) DO UPDATE SET name=excluded.name, latitude=excluded.latitude,
               longitude=excluded.longitude, device_type=excluded.device_type, vendor=excluded.vendor,
               neighbors_json=excluded.neighbors_json, location_known=1""",
            devices,
        )
    try:
        await index_devices(devices)
    except RedisError as error:
        logger.exception("Unable to index uploaded inventory in Redis GEO")
        raise HTTPException(
            status_code=503,
            detail=f"Inventory was saved, but Redis geospatial indexing failed: {error}",
        ) from error
    return {"uploaded": len(devices), "device_ids": [device["device_id"] for device in devices]}


@app.post("/devices/demo/iit-bhubaneswar")
async def load_iit_bhubaneswar_demo_inventory() -> dict[str, Any]:
    devices = build_iit_bhubaneswar_inventory()
    with connect_db() as connection:
        connection.execute("DELETE FROM devices")
        connection.executemany(
            """INSERT INTO devices(device_id, name, latitude, longitude, device_type, vendor, status,
               neighbors_json, location_known)
               VALUES (:device_id, :name, :latitude, :longitude, :device_type, :vendor, 'unknown', :neighbors_json, 1)""",
            devices,
        )
    try:
        if redis_client is None:
            raise RedisError("Redis connection is not initialized")
        await redis_client.delete(GEO_KEY, DEVICE_DETAILS_KEY)
        await index_devices(devices)
    except RedisError as error:
        logger.exception("Unable to index IIT Bhubaneswar demo inventory in Redis GEO")
        raise HTTPException(
            status_code=503,
            detail=f"Demo inventory was saved, but Redis geospatial indexing failed: {error}",
        ) from error
    return {
        "site": "IIT Bhubaneswar",
        "synthetic": True,
        "replaced_existing_inventory": True,
        "uploaded": len(devices),
        "device_ids": [device["device_id"] for device in devices],
    }


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


def load_incident_context(event_id: str) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]], list[dict[str, Any]]]:
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
                      d.device_type, d.latitude, d.longitude, d.location_known
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
                "latitude": item["latitude"] or 0,
                "longitude": item["longitude"] or 0,
                "location_known": bool(item["location_known"]),
            }
            for item in window_rows
        ]
    return event, device, history, telemetry_window


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
    event, device, history, telemetry_window = load_incident_context(incident_id)
    answers = {
        **previous_report.get("human_answers", {}),
        **information.answers,
    }
    if isinstance(answers.get("firewall_drops"), (int, float)):
        event["metrics"]["firewall_drops"] = float(answers["firewall_drops"])
        event["units"]["firewall_drops"] = "events"
    if answers.get("firewall_alerts") is True or answers.get("utm_alerts") is True:
        answers["utm_alerts"] = True
    report = await run_in_threadpool(
        run_workflow,
        event,
        device,
        history,
        telemetry_window,
        answers,
        redis_geo_lookup,
        BLAST_RADIUS_KM,
        LLM,
    )
    queue_status = "needs_human" if report["human_questions"] else "processed"
    with connect_db() as connection:
        connection.execute(
            "UPDATE telemetry SET queue_status=?, report_json=? WHERE event_id=?",
            (queue_status, json.dumps(report), incident_id),
        )
        stale_cutoff = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
        connection.execute(
            """UPDATE devices SET risk_probability=0,
               status=CASE WHEN last_seen >= ? THEN 'healthy' ELSE 'unknown' END""",
            (stale_cutoff,),
        )
        for issue in report["device_statuses"]:
            connection.execute(
                "UPDATE devices SET status=?, risk_probability=? WHERE device_id=?",
                (issue["severity"], issue["probability"], issue["device_id"]),
            )
        connection.execute(
            "UPDATE devices SET status=?, risk_probability=? WHERE device_id=?",
            (
                report["severity"],
                0.96 if report["severity"] == "critical" else (0.78 if report["severity"] == "warning" else 0.05),
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
                f"- Evidence: {'; '.join(cause['evidence'])}",
                f"- Recommended action: {cause['recommended_action']}",
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
    lines.extend(["", "## Device issue map input", ""])
    for device in report["issue_devices"]:
        lines.append(
            f"- `{device['device_id']}` ({device['device_type']}) — "
            f"{device['probability']:.0%} risk, {device['severity']}, "
            f"{device['latitude']}, {device['longitude']}"
        )
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
