"""Sector Control Service – manages aircraft within a defined airspace sector."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging_config import setup_logging
from shared.rabbitmq import get_connection, get_exchange
from shared.redis_utils import get_redis

from app.api.health import router as health_router
from app.workers.sector_consumer import start_consumers

SERVICE_NAME = "sector"
SECTOR_ID = os.getenv("SECTOR_ID", "SECTOR_A")
setup_logging(f"{SERVICE_NAME}_{SECTOR_ID}")

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
    app.state.sector_id = SECTOR_ID

    await start_consumers(channel, exchange, redis, SECTOR_ID)
    yield
    await conn.close()


app = FastAPI(title=f"Sector Service ({SECTOR_ID})", lifespan=lifespan)
app.include_router(health_router)
