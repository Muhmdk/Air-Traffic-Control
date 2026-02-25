"""Sector boundary definitions."""

from __future__ import annotations

from pydantic import BaseModel


class SectorBoundary(BaseModel):
    sector_id: str
    min_lat: float
    max_lat: float
    min_lon: float
    max_lon: float


# Two pre-defined sectors split along longitude -79.45
SECTORS: dict[str, SectorBoundary] = {
    "SECTOR_A": SectorBoundary(
        sector_id="SECTOR_A",
        min_lat=43.5,
        max_lat=43.8,
        min_lon=-79.7,
        max_lon=-79.45,
    ),
    "SECTOR_B": SectorBoundary(
        sector_id="SECTOR_B",
        min_lat=43.5,
        max_lat=43.8,
        min_lon=-79.45,
        max_lon=-79.2,
    ),
}


def is_inside(sector: SectorBoundary, lat: float, lon: float) -> bool:
    return (
        sector.min_lat <= lat <= sector.max_lat
        and sector.min_lon <= lon <= sector.max_lon
    )


def find_target_sector(current_sector_id: str, lat: float, lon: float) -> str | None:
    """Return the sector_id that contains (lat, lon), excluding current."""
    for sid, boundary in SECTORS.items():
        if sid != current_sector_id and is_inside(boundary, lat, lon):
            return sid
    return None
