"""Detect separation violations among tracked aircraft."""

from __future__ import annotations

import logging
from itertools import combinations

import redis.asyncio as aioredis
from aio_pika.abc import AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import publish
from shared.redis_utils import json_get

from app.domain.rules import is_conflict

logger = logging.getLogger(__name__)

# Known aircraft IDs (updated on each position event)
_tracked: set[str] = set()


async def check(
    event: ATCEvent,
    redis: aioredis.Redis,
    exchange: AbstractExchange,
) -> None:
    """On each position update, compare the reporting aircraft against all others."""
    _tracked.add(event.aircraft_id)

    current = event.data
    for other_id in list(_tracked):
        if other_id == event.aircraft_id:
            continue

        other = await json_get(redis, f"pos:{other_id}")
        if other is None:
            continue

        if is_conflict(
            current["lat"],
            current["lon"],
            current.get("altitude", 0),
            other["lat"],
            other["lon"],
            other.get("altitude", 0),
        ):
            logger.warning(
                "CONFLICT between %s and %s", event.aircraft_id, other_id
            )
            alert = ATCEvent(
                type=RoutingKeys.CONFLICT_ALERT,
                aircraft_id=event.aircraft_id,
                source_service="conflict",
                data={
                    "conflicting_aircraft": other_id,
                    "aircraft_a": {
                        "id": event.aircraft_id,
                        "lat": current["lat"],
                        "lon": current["lon"],
                        "altitude": current.get("altitude", 0),
                    },
                    "aircraft_b": {
                        "id": other_id,
                        "lat": other["lat"],
                        "lon": other["lon"],
                        "altitude": other.get("altitude", 0),
                    },
                },
            )
            await publish(exchange, alert)
