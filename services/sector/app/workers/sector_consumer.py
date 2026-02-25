"""Message consumers for the sector service."""

from __future__ import annotations

import redis.asyncio as aioredis
from aio_pika.abc import AbstractChannel, AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import subscribe

from app.services.handle_clearance import handle as handle_clearance
from app.services.handle_handoff import handle_accepted, handle_request
from app.services.handle_position import handle as handle_position


async def start_consumers(
    channel: AbstractChannel,
    exchange: AbstractExchange,
    redis: aioredis.Redis,
    sector_id: str,
) -> None:
    """Subscribe to all routing keys this sector cares about."""

    async def on_position(event: ATCEvent) -> None:
        await handle_position(event, redis, exchange, sector_id)

    async def on_handoff_request(event: ATCEvent) -> None:
        await handle_request(event, redis, exchange, sector_id)

    async def on_handoff_accepted(event: ATCEvent) -> None:
        await handle_accepted(event, redis, sector_id)

    async def on_runway_assigned(event: ATCEvent) -> None:
        await handle_clearance(event, redis, sector_id)

    await subscribe(
        channel, exchange,
        f"sector.{sector_id}.position",
        RoutingKeys.AIRCRAFT_POSITION,
        on_position,
    )
    await subscribe(
        channel, exchange,
        f"sector.{sector_id}.handoff.req",
        RoutingKeys.HANDOFF_REQUEST,
        on_handoff_request,
    )
    await subscribe(
        channel, exchange,
        f"sector.{sector_id}.handoff.acc",
        RoutingKeys.HANDOFF_ACCEPTED,
        on_handoff_accepted,
    )
    await subscribe(
        channel, exchange,
        f"sector.{sector_id}.runway.assigned",
        RoutingKeys.RUNWAY_ASSIGNED,
        on_runway_assigned,
    )
