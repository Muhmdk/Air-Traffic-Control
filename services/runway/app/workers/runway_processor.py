"""Background processor: periodically try to assign queued aircraft to runways."""

from __future__ import annotations

import asyncio
import logging

import redis.asyncio as aioredis
from aio_pika.abc import AbstractExchange

from app.domain.runway import RUNWAYS
from app.services.assign_runway import try_assign

logger = logging.getLogger(__name__)

PROCESS_INTERVAL = 5  # seconds


async def start_processor(
    redis: aioredis.Redis,
    exchange: AbstractExchange,
) -> None:
    """Continuously process runway queues for all airports."""
    while True:
        for airport_id in RUNWAYS:
            await try_assign(redis, exchange, airport_id)
        await asyncio.sleep(PROCESS_INTERVAL)
