from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
from typing import Any

import httpx
from dotenv import load_dotenv
from redis.asyncio import Redis
from redis.exceptions import ResponseError

load_dotenv()

REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000").rstrip("/")
INTERNAL_TOKEN = os.getenv("INTERNAL_TOKEN", "change-this-in-production")
TELEMETRY_STREAM = os.getenv("TELEMETRY_STREAM", "netcoop:telemetry")
DEAD_LETTER_STREAM = os.getenv("DEAD_LETTER_STREAM", "netcoop:telemetry:dead")
CONSUMER_GROUP = os.getenv("TELEMETRY_CONSUMER_GROUP", "netcoop-workers")
HEARTBEAT_KEY = os.getenv("WORKER_HEARTBEAT_KEY", "netcoop:worker:heartbeat")
MAX_DELIVERIES = int(os.getenv("WORKER_MAX_DELIVERIES", "5"))
BLOCK_MS = int(os.getenv("WORKER_BLOCK_MS", "5000"))
CLAIM_IDLE_MS = int(os.getenv("WORKER_CLAIM_IDLE_MS", "30000"))
RETRY_KEY = "netcoop:telemetry:attempts"
logger = logging.getLogger("netcoop.worker")


async def ensure_consumer_group(redis: Redis) -> None:
    try:
        await redis.xgroup_create(TELEMETRY_STREAM, CONSUMER_GROUP, id="0", mkstream=True)
    except ResponseError as error:
        if "BUSYGROUP" not in str(error):
            raise


async def process_entry(
    redis: Redis,
    client: httpx.AsyncClient,
    message_id: str,
    fields: dict[str, Any],
) -> None:
    try:
        payload = fields.get("payload")
        if payload is None:
            raise ValueError(f"Queue event {message_id} has no payload")
        response = await client.post(
            f"{BACKEND_URL}/internal/process",
            json=json.loads(payload),
            headers={"x-internal-token": INTERNAL_TOKEN},
        )
        response.raise_for_status()
    except (ValueError, json.JSONDecodeError, httpx.HTTPError) as error:
        attempts = await redis.hincrby(RETRY_KEY, message_id, 1)
        logger.exception("Telemetry queue entry %s failed (attempt %s)", message_id, attempts)
        if attempts >= MAX_DELIVERIES:
            await redis.xadd(DEAD_LETTER_STREAM, {
                "original_id": message_id,
                "payload": fields.get("payload", ""),
                "error": str(error),
            })
            await redis.xack(TELEMETRY_STREAM, CONSUMER_GROUP, message_id)
            await redis.hdel(RETRY_KEY, message_id)
        return

    await redis.xack(TELEMETRY_STREAM, CONSUMER_GROUP, message_id)
    await redis.hdel(RETRY_KEY, message_id)


async def worker_loop() -> None:
    redis = Redis.from_url(REDIS_URL, decode_responses=True)
    consumer = f"{socket.gethostname()}-{os.getpid()}"
    await ensure_consumer_group(redis)
    headers = {"x-internal-token": INTERNAL_TOKEN}
    try:
        async with httpx.AsyncClient(timeout=30, headers=headers) as client:
            while True:
                await redis.set(HEARTBEAT_KEY, consumer, ex=30)
                _, reclaimed, _ = await redis.xautoclaim(
                    TELEMETRY_STREAM,
                    CONSUMER_GROUP,
                    consumer,
                    min_idle_time=CLAIM_IDLE_MS,
                    start_id="0-0",
                    count=10,
                )
                if reclaimed:
                    entries = [(TELEMETRY_STREAM, reclaimed)]
                else:
                    entries = await redis.xreadgroup(
                        CONSUMER_GROUP,
                        consumer,
                        {TELEMETRY_STREAM: ">"},
                        count=10,
                        block=BLOCK_MS,
                    ) or []
                for _, messages in entries:
                    for message_id, fields in messages:
                        await process_entry(redis, client, message_id, fields)
    finally:
        await redis.aclose()


def main() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    try:
        asyncio.run(worker_loop())
    except KeyboardInterrupt:
        logger.info("Worker stopped.")


if __name__ == "__main__":
    main()
