"""Business logic: assign a runway to an aircraft from the queue."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from aio_pika.abc import AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import publish
from shared.redis_utils import acquire_lock, dequeue, release_lock

from app.domain.runway import RUNWAYS, conflicts_with_active

logger = logging.getLogger(__name__)

LOCK_TTL = 30  # seconds runway is reserved


async def _get_active_runways(redis: aioredis.Redis, airport_id: str) -> set[str]:
    """Return the set of runway IDs currently locked at this airport."""
    active: set[str] = set()
    for rwy in RUNWAYS.get(airport_id, []):
        if await redis.exists(f"runwaylock:{rwy}"):
            active.add(rwy)
    return active


async def try_assign(
    redis: aioredis.Redis,
    exchange: AbstractExchange,
    airport_id: str,
) -> bool:
    """Attempt to dequeue one aircraft and assign a free, non-conflicting runway."""
    queue_key = f"runwayq:{airport_id}"
    runways = RUNWAYS.get(airport_id, [])

    # Snapshot of currently occupied runways
    active = await _get_active_runways(redis, airport_id)

    for runway_id in runways:
        # Skip if this runway would conflict with an already-active one
        if conflicts_with_active(runway_id, active):
            logger.debug(
                "Skipping %s — conflicts with active runways %s", runway_id, active,
            )
            continue

        lock_key = f"runwaylock:{runway_id}"
        if await acquire_lock(redis, lock_key, ttl=LOCK_TTL):
            aircraft_id = await dequeue(redis, queue_key)
            if aircraft_id is None:
                await release_lock(redis, lock_key)
                return False

            # Retrieve the operation type stored during enqueue
            operation = await redis.get(f"rwyop:{aircraft_id}") or "landing"

            logger.info(
                "ASSIGNED %s -> %s for %s at %s",
                runway_id, aircraft_id, operation, airport_id,
            )

            event = ATCEvent(
                type=RoutingKeys.RUNWAY_ASSIGNED,
                aircraft_id=aircraft_id,
                source_service="runway",
                data={
                    "airport_id": airport_id,
                    "runway_id": runway_id,
                    "operation": operation,
                },
            )
            await publish(exchange, event)
            return True

    return False  # All runways locked or conflicting
