"""Consume ALL events via wildcard and persist to Postgres."""

from __future__ import annotations

import json
import logging

import asyncpg
from aio_pika.abc import AbstractChannel, AbstractExchange

from shared.events import ATCEvent
from shared.postgres import insert_event_log
from shared.rabbitmq import subscribe

logger = logging.getLogger(__name__)


async def start_consumers(
    channel: AbstractChannel,
    exchange: AbstractExchange,
    pool: asyncpg.Pool,
) -> None:
    async def on_any_event(event: ATCEvent) -> None:
        logger.debug("Persisting event %s (%s)", event.event_id, event.type)
        await insert_event_log(
            pool,
            event_id=event.event_id,
            event_type=event.type,
            aircraft_id=event.aircraft_id,
            source_service=event.source_service,
            timestamp=event.timestamp,
            payload=json.dumps(event.data),
        )

    # Wildcard: capture every event on the atc.events exchange
    await subscribe(
        channel,
        exchange,
        "logging.all_events",
        "#",  # topic wildcard – matches all routing keys
        on_any_event,
    )
