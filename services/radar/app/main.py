"""Radar Service – generates and broadcasts aircraft position updates."""

from __future__ import annotations

import asyncio
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging_config import setup_logging
from shared.rabbitmq import get_connection, get_exchange
from shared.redis_utils import get_redis

from app.api.health import router as health_router
from app.workers.position_broadcaster import start_broadcasting

SERVICE_NAME = "radar"
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

    task = asyncio.create_task(start_broadcasting(exchange, redis))
    yield
    task.cancel()
    await conn.close()


app = FastAPI(title="Radar Service", lifespan=lifespan)
app.include_router(health_router)
