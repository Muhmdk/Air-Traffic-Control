"""WebSocket endpoint for real-time event streaming to browser clients."""

from __future__ import annotations

import asyncio
import json
import logging

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter()
logger = logging.getLogger(__name__)

# Connected WebSocket clients
_clients: set[WebSocket] = set()


def get_clients() -> set[WebSocket]:
    return _clients


async def broadcast(data: dict) -> None:
    """Send a JSON message to all connected WebSocket clients."""
    dead: list[WebSocket] = []
    message = json.dumps(data)
    for ws in _clients:
        try:
            await ws.send_text(message)
        except Exception:
            dead.append(ws)
    for ws in dead:
        _clients.discard(ws)


@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    _clients.add(websocket)
    logger.info("WebSocket client connected (%d total)", len(_clients))
    try:
        while True:
            # Keep connection alive; ignore client messages
            await websocket.receive_text()
    except WebSocketDisconnect:
        _clients.discard(websocket)
        logger.info("WebSocket client disconnected (%d total)", len(_clients))
