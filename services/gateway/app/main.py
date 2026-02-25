"""Gateway Service – WebSocket bridge from RabbitMQ to browser clients."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from shared.logging_config import setup_logging
from shared.rabbitmq import get_connection, get_exchange
from shared.redis_utils import get_redis

from app.api.health import router as health_router
from app.api.reset import router as reset_router
from app.api.ws import router as ws_router
from app.workers.gateway_consumer import start_consumers

SERVICE_NAME = "gateway"
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

    await start_consumers(channel, exchange)
    yield
    await conn.close()


app = FastAPI(title="Gateway Service", lifespan=lifespan)
app.include_router(health_router)
app.include_router(reset_router)
app.include_router(ws_router)

# Serve the static HTML dashboard (must be last — catch-all mount)
static_dir = Path(__file__).parent / "static"
app.mount("/", StaticFiles(directory=str(static_dir), html=True), name="static")
