"""State machine: advance aircraft through phases using waypoint interpolation."""

from __future__ import annotations

import math

from app.domain.aircraft import (
    APPROACH_PATHS,
    DEFAULT_APPROACH_PATH,
    DEFAULT_TAKEOFF_PATH,
    TAKEOFF_PATHS,
    Phase,
    SimAircraft,
    holding_position,
)


def _interpolate_path(
    path: list[tuple[float, float, float, float, int]],
    elapsed: int,
) -> tuple[float, float, float, float, float, bool]:
    """Walk through waypoint segments, interpolate position.

    Returns (lat, lon, alt, heading, speed, path_complete).
    """
    cumulative = 0
    for i in range(len(path) - 1):
        seg_ticks = path[i][4]
        if elapsed < cumulative + seg_ticks:
            # We're in this segment
            t = (elapsed - cumulative) / seg_ticks
            lat0, lon0, alt0, spd0, _ = path[i]
            lat1, lon1, alt1, spd1, _ = path[i + 1]

            lat = lat0 + (lat1 - lat0) * t
            lon = lon0 + (lon1 - lon0) * t
            alt = alt0 + (alt1 - alt0) * t
            spd = spd0 + (spd1 - spd0) * t

            # Heading toward next waypoint
            dlat = lat1 - lat0
            dlon = lon1 - lon0
            heading = math.degrees(math.atan2(dlon, dlat)) % 360

            return lat, lon, alt, heading, spd, False
        cumulative += seg_ticks

    # Path complete — hold at final waypoint
    final = path[-1]
    prev = path[-2]
    heading = math.degrees(math.atan2(final[1] - prev[1], final[0] - prev[0])) % 360
    return final[0], final[1], final[2], heading, final[3], True


def _get_takeoff_path(runway_id: str | None) -> list[tuple[float, float, float, float, int]]:
    """Return the takeoff path for the given runway, or the default."""
    if runway_id and runway_id in TAKEOFF_PATHS:
        return TAKEOFF_PATHS[runway_id]
    return DEFAULT_TAKEOFF_PATH


def _get_approach_path(runway_id: str | None) -> list[tuple[float, float, float, float, int]]:
    """Return the approach path for the given runway, or the default."""
    if runway_id and runway_id in APPROACH_PATHS:
        return APPROACH_PATHS[runway_id]
    return DEFAULT_APPROACH_PATH


def tick(ac: SimAircraft, has_clearance: bool, runway_id: str | None = None) -> SimAircraft:
    """Advance one simulation tick. Returns updated aircraft.

    runway_id: the assigned runway (from Redis). Selects the correct path.
    """
    ac = ac.model_copy(update={"phase_tick": ac.phase_tick + 1})

    # ── Departing aircraft ─────────────────────────────────
    if ac.phase == Phase.TAXI:
        if has_clearance:
            ac = ac.model_copy(update={"phase": Phase.TAKEOFF_ROLL, "phase_tick": 0})
        else:
            return ac

    if ac.phase == Phase.TAKEOFF_ROLL:
        path = _get_takeoff_path(runway_id)
        lat, lon, alt, hdg, spd, done = _interpolate_path(path, ac.phase_tick)
        ac = ac.model_copy(update={
            "lat": lat, "lon": lon, "altitude": alt, "heading": hdg, "speed": spd,
        })
        if ac.phase_tick > 10 and alt > 100:
            ac = ac.model_copy(update={"phase": Phase.CLIMBING})
        return ac

    if ac.phase == Phase.CLIMBING:
        path = _get_takeoff_path(runway_id)
        lat, lon, alt, hdg, spd, done = _interpolate_path(path, ac.phase_tick)
        ac = ac.model_copy(update={
            "lat": lat, "lon": lon, "altitude": alt, "heading": hdg, "speed": spd,
        })
        if done:
            ac = ac.model_copy(update={"phase": Phase.DEPARTED})
        return ac

    if ac.phase == Phase.DEPARTED:
        return ac

    # ── Arriving aircraft ──────────────────────────────────
    if ac.phase == Phase.HOLDING:
        lat, lon, alt, hdg, spd = holding_position(ac.phase_tick)
        ac = ac.model_copy(update={
            "lat": lat, "lon": lon, "altitude": alt, "heading": hdg, "speed": spd,
        })
        if has_clearance:
            ac = ac.model_copy(update={"phase": Phase.APPROACH, "phase_tick": 0})
        return ac

    if ac.phase == Phase.APPROACH:
        path = _get_approach_path(runway_id)
        lat, lon, alt, hdg, spd, done = _interpolate_path(path, ac.phase_tick)
        ac = ac.model_copy(update={
            "lat": lat, "lon": lon, "altitude": alt, "heading": hdg, "speed": spd,
        })
        if alt < 600:
            ac = ac.model_copy(update={"phase": Phase.FINAL})
        return ac

    if ac.phase == Phase.FINAL:
        path = _get_approach_path(runway_id)
        lat, lon, alt, hdg, spd, done = _interpolate_path(path, ac.phase_tick)
        ac = ac.model_copy(update={
            "lat": lat, "lon": lon, "altitude": alt, "heading": hdg, "speed": spd,
        })
        if done:
            ac = ac.model_copy(update={"phase": Phase.LANDED})
        return ac

    if ac.phase == Phase.LANDED:
        return ac

    return ac
