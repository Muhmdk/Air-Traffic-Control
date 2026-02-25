"""Standard event envelope used across all ATC services."""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any

from pydantic import BaseModel, Field


class ATCEvent(BaseModel):
    """Canonical event envelope for all inter-service messages."""

    event_id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    type: str  # routing key, e.g. "aircraft.position"
    aircraft_id: str
    source_service: str
    data: dict[str, Any] = Field(default_factory=dict)


# ── Routing keys ────────────────────────────────────────────────
class RoutingKeys:
    AIRCRAFT_POSITION = "aircraft.position"
    HANDOFF_REQUEST = "aircraft.handoff.request"
    HANDOFF_ACCEPTED = "aircraft.handoff.accepted"
    RUNWAY_REQUEST = "runway.request"
    RUNWAY_ASSIGNED = "runway.assigned"
    CONFLICT_ALERT = "conflict.alert"


EXCHANGE_NAME = "atc.events"
