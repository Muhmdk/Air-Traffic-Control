"""Runway domain models."""

from __future__ import annotations

from pydantic import BaseModel


class RunwayRequest(BaseModel):
    aircraft_id: str
    airport_id: str
    operation: str  # "landing" or "takeoff"


# Pre-defined active runways per airport
RUNWAYS: dict[str, list[str]] = {
    "YYZ": ["RWY_06L", "RWY_06R"],
}

# Conflict groups: runways in the same group are parallel (safe simultaneously).
# Runways from different groups cross each other and CANNOT be used together.
# Group A (heading ~047): 05/23, 06L/24R, 06R/24L — all parallel east-west
# Group B (heading ~137): 15L/33R, 15R/33L — cross Group A runways
RUNWAY_CONFLICT_GROUPS: dict[str, str] = {
    "RWY_05": "A", "RWY_23": "A",
    "RWY_06L": "A", "RWY_24R": "A",
    "RWY_06R": "A", "RWY_24L": "A",
    "RWY_15L": "B", "RWY_33R": "B",
    "RWY_15R": "B", "RWY_33L": "B",
}


def conflicts_with_active(runway_id: str, active_runways: set[str]) -> bool:
    """Return True if runway_id conflicts with any currently active runway."""
    my_group = RUNWAY_CONFLICT_GROUPS.get(runway_id)
    if my_group is None:
        return False
    for active_rwy in active_runways:
        other_group = RUNWAY_CONFLICT_GROUPS.get(active_rwy)
        if other_group is not None and other_group != my_group:
            return True
    return False
