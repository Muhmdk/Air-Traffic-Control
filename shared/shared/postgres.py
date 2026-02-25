"""Postgres helpers using asyncpg for event log and flight plan persistence."""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import datetime, timezone

import asyncpg

logger = logging.getLogger(__name__)

_MAX_RETRIES = 10
_RETRY_DELAY = 3


async def get_pool(dsn: str) -> asyncpg.Pool:
    """Create a connection pool with startup retry."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            pool = await asyncpg.create_pool(dsn, min_size=2, max_size=10)
            return pool
        except Exception:
            logger.warning(
                "Postgres not ready (attempt %d/%d), retrying in %ds …",
                attempt,
                _MAX_RETRIES,
                _RETRY_DELAY,
            )
            await asyncio.sleep(_RETRY_DELAY)
    raise RuntimeError("Could not connect to Postgres")


async def insert_event_log(
    pool: asyncpg.Pool,
    event_id: str,
    event_type: str,
    aircraft_id: str,
    source_service: str,
    timestamp: str,
    payload: str,
) -> None:
    """Insert a row into the event_log table."""
    await pool.execute(
        """
        INSERT INTO event_log (id, event_id, event_type, aircraft_id,
                               source_service, timestamp, payload)
        VALUES ($1, $2, $3, $4, $5, $6, $7::jsonb)
        ON CONFLICT (event_id) DO NOTHING
        """,
        str(uuid.uuid4()),
        event_id,
        event_type,
        aircraft_id,
        source_service,
        datetime.fromisoformat(timestamp),
        payload,
    )
