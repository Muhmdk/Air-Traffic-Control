"""RabbitMQ connection helpers: publish and subscribe via topic exchange."""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any, Callable, Coroutine

import aio_pika
from aio_pika import ExchangeType, Message
from aio_pika.abc import AbstractIncomingMessage

from shared.events import EXCHANGE_NAME, ATCEvent

logger = logging.getLogger(__name__)

_MAX_RETRIES = 10
_RETRY_DELAY = 3  # seconds


async def get_connection(amqp_url: str) -> aio_pika.abc.AbstractRobustConnection:
    """Connect to RabbitMQ with retry logic."""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            return await aio_pika.connect_robust(amqp_url)
        except Exception:
            logger.warning(
                "RabbitMQ not ready (attempt %d/%d), retrying in %ds …",
                attempt,
                _MAX_RETRIES,
                _RETRY_DELAY,
            )
            await asyncio.sleep(_RETRY_DELAY)
    raise RuntimeError("Could not connect to RabbitMQ")


async def get_exchange(
    channel: aio_pika.abc.AbstractChannel,
) -> aio_pika.abc.AbstractExchange:
    """Declare (or reuse) the shared topic exchange."""
    return await channel.declare_exchange(
        EXCHANGE_NAME, ExchangeType.TOPIC, durable=True
    )


async def publish(
    exchange: aio_pika.abc.AbstractExchange,
    event: ATCEvent,
) -> None:
    """Publish an event onto the topic exchange."""
    body = json.dumps(event.model_dump()).encode()
    await exchange.publish(
        Message(body=body, content_type="application/json"),
        routing_key=event.type,
    )
    logger.debug("Published %s for %s", event.type, event.aircraft_id)


async def subscribe(
    channel: aio_pika.abc.AbstractChannel,
    exchange: aio_pika.abc.AbstractExchange,
    queue_name: str,
    routing_key: str,
    callback: Callable[[ATCEvent], Coroutine[Any, Any, None]],
) -> None:
    """Bind a queue to routing_key and start consuming."""
    queue = await channel.declare_queue(queue_name, durable=True)
    await queue.bind(exchange, routing_key=routing_key)

    async def _on_message(msg: AbstractIncomingMessage) -> None:
        async with msg.process():
            payload = json.loads(msg.body.decode())
            event = ATCEvent(**payload)
            await callback(event)

    await queue.consume(_on_message)
    logger.info("Subscribed %s → %s", queue_name, routing_key)
