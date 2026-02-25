"""Conflict detection rules."""

from __future__ import annotations

import math

# Minimum separation: ~5 nautical miles ≈ 0.083 degrees lat/lon (simplified)
MIN_HORIZONTAL_SEP = 0.05  # degrees (approx 5.5 km)
MIN_VERTICAL_SEP = 1000  # feet


def haversine_approx(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Approximate distance in degrees (cheap, good enough for simulation)."""
    return math.sqrt((lat1 - lat2) ** 2 + (lon1 - lon2) ** 2)


def is_conflict(
    lat1: float,
    lon1: float,
    alt1: float,
    lat2: float,
    lon2: float,
    alt2: float,
) -> bool:
    """Return True if two aircraft violate separation minimums."""
    horizontal = haversine_approx(lat1, lon1, lat2, lon2)
    vertical = abs(alt1 - alt2)
    return horizontal < MIN_HORIZONTAL_SEP and vertical < MIN_VERTICAL_SEP
