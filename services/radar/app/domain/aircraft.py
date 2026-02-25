"""Aircraft simulation models with phase-based state machine."""

from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel


class Phase(str, Enum):
    # Departing aircraft
    TAXI = "taxi"
    TAKEOFF_ROLL = "takeoff_roll"
    CLIMBING = "climbing"
    DEPARTED = "departed"

    # Arriving aircraft
    HOLDING = "holding"
    APPROACH = "approach"
    FINAL = "final"
    LANDED = "landed"


class SimAircraft(BaseModel):
    aircraft_id: str
    callsign: str
    phase: Phase
    intent: str  # "landing" or "takeoff"
    lat: float
    lon: float
    altitude: float
    heading: float
    speed: float
    phase_tick: int = 0  # ticks spent in current phase


# ── Waypoint paths ──────────────────────────────────────────
# Each path: list of (lat, lon, altitude_ft, speed_kts, ticks_to_next)
# Coordinates from OurAirports CYYZ runway data.
#
# Paths are keyed by runway ID so the radar can look up the correct
# path after the runway service assigns a specific runway.

# ── Takeoff paths ───────────────────────────────────────────
# RWY 06L: threshold at (43.6610, -79.6234), far end 24R at (43.6790, -79.5974)
# Heading ~047 (SW → NE)
TAKEOFF_PATHS: dict[str, list[tuple[float, float, float, float, int]]] = {
    "RWY_06L": [
        (43.6590, -79.6260,    0,   20,  8),   # taxi toward 06L threshold
        (43.6610, -79.6234,    0,  140,  5),   # at threshold — start roll
        (43.6700, -79.6104,    0,  160,  5),   # mid-runway — rotating
        (43.6790, -79.5974,  300,  170,  4),   # end of runway — liftoff
        (43.6900, -79.5800, 1500,  220,  6),   # initial climb
        (43.7100, -79.5450, 4000,  260,  8),   # climbing through 4000
        (43.7400, -79.4900, 10000, 300, 10),   # climb to cruise
        (43.7700, -79.4300, 15000, 320, 12),   # departing sector
    ],
}

# ── Approach paths ──────────────────────────────────────────
# RWY 06R: threshold at (43.6583, -79.6219), far end 24L at (43.6753, -79.5972)
# Heading ~047, approach from SW
APPROACH_PATHS: dict[str, list[tuple[float, float, float, float, int]]] = {
    "RWY_06R": [
        (43.7100, -79.5000, 4500,  200,  8),   # break from holding, descend
        (43.6900, -79.5400, 3500,  180,  8),   # base leg
        (43.6700, -79.5800, 2500,  170,  8),   # intercept extended centerline
        (43.6630, -79.6100, 1500,  160,  8),   # on final — aligned with 06R
        (43.6600, -79.6180,  500,  150,  6),   # short final
        (43.6583, -79.6219,   50,  140,  4),   # over 06R threshold
        (43.6640, -79.6140,    0,   80,  4),   # touchdown + decelerate
        (43.6700, -79.6050,    0,   20,  6),   # roll-out toward 24L end
    ],
}

# Fallbacks used when no runway-specific path exists
DEFAULT_TAKEOFF_PATH = TAKEOFF_PATHS["RWY_06L"]
DEFAULT_APPROACH_PATH = APPROACH_PATHS["RWY_06R"]


# ── Holding pattern (elliptical racetrack) ──────────────────
HOLDING_CENTER = (43.72, -79.48)
HOLDING_A = 0.015       # lat semi-axis
HOLDING_B = 0.025       # lon semi-axis (elongated E-W)
HOLDING_ALT = 5000.0
HOLDING_SPEED = 220.0
HOLDING_ANGULAR_SPEED = 0.15  # radians per tick (~42 ticks per loop)


def holding_position(tick: int) -> tuple[float, float, float, float, float]:
    """Compute position on the elliptical holding pattern. Returns (lat, lon, alt, heading, speed)."""
    angle = tick * HOLDING_ANGULAR_SPEED
    lat = HOLDING_CENTER[0] + HOLDING_A * math.sin(angle)
    lon = HOLDING_CENTER[1] + HOLDING_B * math.cos(angle)

    # Heading = tangent direction of the ellipse
    dx = HOLDING_B * -math.sin(angle)
    dy = HOLDING_A * math.cos(angle)
    heading = math.degrees(math.atan2(dx, dy)) % 360

    return lat, lon, HOLDING_ALT, heading, HOLDING_SPEED


# ── Initial aircraft ────────────────────────────────────────

# WJA512 starts near the RWY 06L threshold on the taxiway
DEPARTING_AIRCRAFT = SimAircraft(
    aircraft_id="WJA512",
    callsign="WJA512",
    phase=Phase.TAXI,
    intent="takeoff",
    lat=43.6580,
    lon=-79.6270,
    altitude=0,
    heading=47,
    speed=0,
)

ARRIVING_AIRCRAFT = SimAircraft(
    aircraft_id="ACA845",
    callsign="ACA845",
    phase=Phase.HOLDING,
    intent="landing",
    lat=HOLDING_CENTER[0],
    lon=HOLDING_CENTER[1],
    altitude=HOLDING_ALT,
    heading=0,
    speed=HOLDING_SPEED,
)
