"""Runway & Ground Control Service – manages runway allocation."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging_config import setup_logging
from shared.rabbitmq import get_connection, get_exchange
from shared.redis_utils import get_redis

from app.api.health import router as health_router
from app.workers.runway_consumer import start_consumers
from app.workers.runway_processor import start_processor

SERVICE_NAME = "runway"
setup_logging(SERVICE_NAME)

AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672/")
REDIS_URL = os.getenv("REDIS_URL", "redis://redis:6379/0")


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = await get_connection(AMQP_URL)
    channel = await conn.channel()
    exchange = await get_exchange(channel)
    redis = await get_redis(REDIS_URL)

    app.state.exchange = exchange
    app.state.redis = redis

    await start_consumers(channel, exchange, redis)
    task = asyncio.create_task(start_processor(redis, exchange))
    yield
    task.cancel()
    await conn.close()


app = FastAPI(title="Runway Service", lifespan=lifespan)
app.include_router(health_router)
