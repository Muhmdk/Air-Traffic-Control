"""Logging / Persistence Service – stores all events to PostgreSQL."""

from __future__ import annotations

import os
from contextlib import asynccontextmanager

from fastapi import FastAPI

from shared.logging_config import setup_logging
from shared.postgres import get_pool
from shared.rabbitmq import get_connection, get_exchange

from app.api.health import router as health_router
from app.workers.log_consumer import start_consumers

SERVICE_NAME = "logging"
setup_logging(SERVICE_NAME)

AMQP_URL = os.getenv("AMQP_URL", "amqp://guest:guest@rabbitmq:5672/")
POSTGRES_DSN = os.getenv(
    "POSTGRES_DSN", "postgresql://atc:atc_secret@postgres:5432/atc_db"
)


@asynccontextmanager
async def lifespan(app: FastAPI):
    conn = await get_connection(AMQP_URL)
    channel = await conn.channel()
    exchange = await get_exchange(channel)
    pool = await get_pool(POSTGRES_DSN)

    app.state.pool = pool

    await start_consumers(channel, exchange, pool)
    yield
    await pool.close()
    await conn.close()


app = FastAPI(title="Logging Service", lifespan=lifespan)
app.include_router(health_router)
