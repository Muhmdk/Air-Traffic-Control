"""Handle handoff request and acceptance events."""

from __future__ import annotations

import logging

import redis.asyncio as aioredis
from aio_pika.abc import AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import publish

logger = logging.getLogger(__name__)


async def handle_request(
    event: ATCEvent,
    redis: aioredis.Redis,
    exchange: AbstractExchange,
    sector_id: str,
) -> None:
    """Receiving sector handles an incoming handoff request."""
    to_sector = event.data.get("to_sector")
    if to_sector != sector_id:
        return  # Not for us

    logger.info(
        "Accepting handoff of %s from %s",
        event.aircraft_id,
        event.data.get("from_sector"),
    )

    # Claim ownership
    await redis.set(f"owner:{event.aircraft_id}", sector_id, ex=15)

    # Publish acceptance
    accept_event = ATCEvent(
        type=RoutingKeys.HANDOFF_ACCEPTED,
        aircraft_id=event.aircraft_id,
        source_service=f"sector_{sector_id}",
        data={
            "from_sector": event.data.get("from_sector"),
            "to_sector": sector_id,
        },
    )
    await publish(exchange, accept_event)


async def handle_accepted(
    event: ATCEvent,
    redis: aioredis.Redis,
    sector_id: str,
) -> None:
    """Originating sector acknowledges handoff completion."""
    from_sector = event.data.get("from_sector")
    if from_sector != sector_id:
        return

    logger.info(
        "Handoff of %s to %s confirmed, releasing ownership",
        event.aircraft_id,
        event.data.get("to_sector"),
    )
    # Ownership already transferred; nothing else to do
