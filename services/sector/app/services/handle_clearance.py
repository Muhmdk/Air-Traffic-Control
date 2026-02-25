"""Handle runway.assigned events — set clearance flags for the radar simulation."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis

from shared.events import ATCEvent

logger = logging.getLogger(__name__)


async def handle(
    event: ATCEvent,
    redis: aioredis.Redis,
    sector_id: str,
) -> None:
    """When runway is assigned to an aircraft, write clearance to Redis."""
    operation = event.data.get("operation", "")
    runway_id = event.data.get("runway_id", "")

    logger.info(
        "ATC CLEARANCE: %s cleared for %s on %s",
        event.aircraft_id,
        operation,
        runway_id,
    )

    # Set clearance flag — radar reads this to transition aircraft state
    await redis.set(
        f"clearance:{event.aircraft_id}",
        operation,  # "takeoff" or "landing"
        ex=120,     # expires after 2 minutes
    )

    # Store assigned runway — radar reads this to select the correct path
    if runway_id:
        await redis.set(f"runway:{event.aircraft_id}", runway_id, ex=120)
