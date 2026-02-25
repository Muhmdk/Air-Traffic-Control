"""Background worker: run the ATC simulation and publish position events."""

from __future__ import annotations

import asyncio
import logging
import os

import redis.asyncio as aioredis
from aio_pika.abc import AbstractExchange

from shared.events import ATCEvent, RoutingKeys
from shared.rabbitmq import publish

from app.domain.aircraft import ARRIVING_AIRCRAFT, DEPARTING_AIRCRAFT, Phase, SimAircraft
from app.services.position_updater import tick

logger = logging.getLogger(__name__)

BROADCAST_INTERVAL = float(os.getenv("RADAR_INTERVAL", "2"))


def _fresh_aircraft() -> dict[str, SimAircraft]:
    """Return a fresh copy of both aircraft at initial state."""
    return {
        DEPARTING_AIRCRAFT.aircraft_id: DEPARTING_AIRCRAFT.model_copy(),
        ARRIVING_AIRCRAFT.aircraft_id: ARRIVING_AIRCRAFT.model_copy(),
    }


async def start_broadcasting(
    exchange: AbstractExchange,
    redis_client: aioredis.Redis,
) -> None:
    """Run the two-aircraft ATC scenario, resettable via Redis flag."""
    aircraft = _fresh_aircraft()

    logger.info(
        "Radar simulation started – %s (departing) + %s (arriving) – interval %.1fs",
        DEPARTING_AIRCRAFT.callsign,
        ARRIVING_AIRCRAFT.callsign,
        BROADCAST_INTERVAL,
    )

    while True:
        # Check for reset signal from the dashboard
        reset = await redis_client.get("sim:reset")
        if reset is not None:
            await redis_client.delete("sim:reset")
            aircraft = _fresh_aircraft()
            logger.info("Simulation RESET – aircraft returned to initial positions")

        for ac_id, ac in list(aircraft.items()):
            # Skip aircraft that have finished their journey
            if ac.phase in (Phase.LANDED, Phase.DEPARTED):
                continue

            # Check Redis for clearance from sector/ATC
            clearance_key = f"clearance:{ac_id}"
            has_clearance = await redis_client.get(clearance_key) is not None

            # Read assigned runway so tick uses the correct path
            runway_id = await redis_client.get(f"runway:{ac_id}")

            # Advance the state machine
            prev_phase = ac.phase
            ac = tick(ac, has_clearance, runway_id=runway_id)
            aircraft[ac_id] = ac

            # Publish position event
            event = ATCEvent(
                type=RoutingKeys.AIRCRAFT_POSITION,
                aircraft_id=ac.aircraft_id,
                source_service="radar",
                data={
                    "callsign": ac.callsign,
                    "lat": round(ac.lat, 6),
                    "lon": round(ac.lon, 6),
                    "altitude": round(ac.altitude),
                    "heading": round(ac.heading, 1),
                    "speed": round(ac.speed),
                    "phase": ac.phase.value,
                    "intent": ac.intent,
                },
            )
            await publish(exchange, event)

            # Log when aircraft reaches terminal state (one final broadcast sent above)
            if ac.phase == Phase.LANDED and prev_phase != Phase.LANDED:
                logger.info("%s has LANDED — removing from radar", ac.callsign)
            elif ac.phase == Phase.DEPARTED and prev_phase != Phase.DEPARTED:
                logger.info("%s has DEPARTED — removing from radar", ac.callsign)

        await asyncio.sleep(BROADCAST_INTERVAL)
