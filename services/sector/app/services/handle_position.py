"""Handle incoming aircraft position events."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from aio_pika.abc import AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import publish
from shared.redis_utils import json_set

from app.domain.sector import SECTORS, find_target_sector, is_inside

logger = logging.getLogger(__name__)

POSITION_TTL = 30
OWNER_TTL = 15


async def handle(
    event: ATCEvent,
    redis: aioredis.Redis,
    exchange: AbstractExchange,
    sector_id: str,
) -> None:
    lat = event.data["lat"]
    lon = event.data["lon"]
    phase = event.data.get("phase", "")
    intent = event.data.get("intent", "")

    my_boundary = SECTORS.get(sector_id)
    if not my_boundary:
        return

    # Only process aircraft inside our sector (or unclaimed)
    owner_key = f"owner:{event.aircraft_id}"
    current_owner = await redis.get(owner_key)

    if current_owner is None:
        if is_inside(my_boundary, lat, lon):
            await redis.set(owner_key, sector_id, ex=OWNER_TTL)
            current_owner = sector_id

    if current_owner != sector_id:
        return

    # Update position in Redis
    await json_set(redis, f"pos:{event.aircraft_id}", event.data, ttl=POSITION_TTL)
    await redis.set(owner_key, sector_id, ex=OWNER_TTL)

    # Check if aircraft is leaving our boundary -> handoff
    if not is_inside(my_boundary, lat, lon):
        target = find_target_sector(sector_id, lat, lon)
        if target:
            logger.info(
                "Aircraft %s leaving %s → handoff to %s",
                event.aircraft_id, sector_id, target,
            )
            await publish(exchange, ATCEvent(
                type=RoutingKeys.HANDOFF_REQUEST,
                aircraft_id=event.aircraft_id,
                source_service=f"sector_{sector_id}",
                data={"from_sector": sector_id, "to_sector": target, "lat": lat, "lon": lon},
            ))

    # ── Runway request logic (deduped via Redis) ────────────
    dedup_key = f"rwy_requested:{event.aircraft_id}"
    already_requested = await redis.get(dedup_key)

    if already_requested:
        return

    # Departing aircraft in TAXI phase → request runway for takeoff
    if phase == "taxi" and intent == "takeoff":
        logger.info("Requesting runway for %s (takeoff)", event.aircraft_id)
        await redis.set(dedup_key, "1", ex=300)
        await publish(exchange, ATCEvent(
            type=RoutingKeys.RUNWAY_REQUEST,
            aircraft_id=event.aircraft_id,
            source_service=f"sector_{sector_id}",
            data={"airport_id": "YYZ", "operation": "takeoff"},
        ))

    # Arriving aircraft in HOLDING phase → request runway for landing
    elif phase == "holding" and intent == "landing":
        logger.info("Requesting runway for %s (landing)", event.aircraft_id)
        await redis.set(dedup_key, "1", ex=300)
        await publish(exchange, ATCEvent(
            type=RoutingKeys.RUNWAY_REQUEST,
            aircraft_id=event.aircraft_id,
            source_service=f"sector_{sector_id}",
            data={"airport_id": "YYZ", "operation": "landing"},
        ))
