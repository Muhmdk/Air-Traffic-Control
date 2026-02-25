"""Consume key events from RabbitMQ and forward to WebSocket clients."""

from __future__ import annotations

from aio_pika.abc import AbstractChannel, AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import subscribe

from app.api.ws import broadcast


async def start_consumers(
    channel: AbstractChannel,
    exchange: AbstractExchange,
) -> None:
    async def on_event(event: ATCEvent) -> None:
        await broadcast(event.model_dump())

    # Subscribe to the three key event types
    await subscribe(
        channel, exchange, "gateway.positions",
        RoutingKeys.AIRCRAFT_POSITION, on_event,
    )
    await subscribe(
        channel, exchange, "gateway.conflicts",
        RoutingKeys.CONFLICT_ALERT, on_event,
    )
    await subscribe(
        channel, exchange, "gateway.runway",
        RoutingKeys.RUNWAY_ASSIGNED, on_event,
    )
