"""Consume position events and run conflict detection."""

from __future__ import annotations

import redis.asyncio as aioredis
from aio_pika.abc import AbstractChannel, AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import subscribe

from app.services.detect_conflicts import check


async def start_consumers(
    channel: AbstractChannel,
    exchange: AbstractExchange,
    redis: aioredis.Redis,
) -> None:
    async def on_position(event: ATCEvent) -> None:
        await check(event, redis, exchange)

    await subscribe(
        channel,
        exchange,
        "conflict.positions",
        RoutingKeys.AIRCRAFT_POSITION,
        on_position,
    )
