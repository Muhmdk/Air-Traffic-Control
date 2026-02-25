"""Redis helpers: JSON get/set, distributed lock, list queue, deduplication."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import redis.asyncio as aioredis

logger = logging.getLogger(__name__)

_MAX_RETRIES = 10
_RETRY_DELAY = 3


async def get_redis(redis_url: str) -> aioredis.Redis:
    """Create a Redis client with startup retry."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            client = aioredis.from_url(redis_url, decode_responses=True)
            await client.ping()
            return client
        except Exception:
            logger.warning(
                "Redis not ready (attempt %d/%d), retrying in %ds …",
                attempt,
                _MAX_RETRIES,
                _RETRY_DELAY,
            )
            await asyncio.sleep(_RETRY_DELAY)
    raise RuntimeError("Could not connect to Redis")


# ── JSON helpers ────────────────────────────────────────────────


async def json_set(
    r: aioredis.Redis, key: str, value: Any, ttl: int | None = None
) -> None:
    await r.set(key, json.dumps(value), ex=ttl)


async def json_get(r: aioredis.Redis, key: str) -> Any | None:
    raw = await r.get(key)
    return json.loads(raw) if raw else None


# ── Distributed lock (simple SETNX + TTL) ──────────────────────


async def acquire_lock(
    r: aioredis.Redis, key: str, ttl: int = 30
) -> bool:
    return bool(await r.set(key, "locked", nx=True, ex=ttl))


async def release_lock(r: aioredis.Redis, key: str) -> None:
    await r.delete(key)


# ── List queue helpers ──────────────────────────────────────────


async def enqueue(r: aioredis.Redis, key: str, value: str) -> None:
    await r.rpush(key, value)


async def dequeue(r: aioredis.Redis, key: str) -> str | None:
    return await r.lpop(key)


async def queue_length(r: aioredis.Redis, key: str) -> int:
    return await r.llen(key)


# ── Deduplication ───────────────────────────────────────────────


async def is_duplicate(
    r: aioredis.Redis, event_id: str, ttl: int = 300
) -> bool:
    """Return True if event_id was already seen (sets key on first call)."""
    key = f"dedup:{event_id}"
    already = await r.set(key, "1", nx=True, ex=ttl)
    return not already  # set returns True when key was NEW
