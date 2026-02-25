"""Consume runway.request events and enqueue aircraft."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from aio_pika.abc import AbstractChannel, AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import subscribe
from shared.redis_utils import enqueue

logger = logging.getLogger(__name__)


async def start_consumers(
    channel: AbstractChannel,
    exchange: AbstractExchange,
    redis: aioredis.Redis,
) -> None:
    async def on_runway_request(event: ATCEvent) -> None:
        airport_id = event.data.get("airport_id", "YYZ")
        operation = event.data.get("operation", "landing")
        queue_key = f"runwayq:{airport_id}"
        logger.info(
            "Enqueuing %s for %s at %s", event.aircraft_id, operation, airport_id
        )
        await enqueue(redis, queue_key, event.aircraft_id)
        # Store the operation so assign_runway can include it
        await redis.set(f"rwyop:{event.aircraft_id}", operation, ex=300)

    await subscribe(
        channel,
        exchange,
        "runway.requests",
        RoutingKeys.RUNWAY_REQUEST,
        on_runway_request,
    )
