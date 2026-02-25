"""Reset endpoint – clears all simulation state and signals radar to restart."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Request

router = APIRouter()
logger = logging.getLogger(__name__)

# Redis key patterns to clear on reset
_KEY_PATTERNS = [
    "pos:*",
    "owner:*",
    "clearance:*",
    "runway:*",
    "rwy_requested:*",
    "rwyop:*",
    "runwayq:*",
    "runwaylock:*",
    "dedup:*",
]


@router.post("/api/reset")
async def reset_simulation(request: Request):
    """Wipe simulation state in Redis and signal radar to restart."""
    redis = request.app.state.redis

    # Delete all sim-related keys
    deleted = 0
    for pattern in _KEY_PATTERNS:
        async for key in redis.scan_iter(match=pattern):
            await redis.delete(key)
            deleted += 1

    # Signal the radar broadcaster to reset
    await redis.set("sim:reset", "1", ex=10)

    logger.info("Simulation reset – cleared %d Redis keys", deleted)
    return {"status": "reset", "keys_cleared": deleted}
