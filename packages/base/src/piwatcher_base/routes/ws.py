"""WebSocket event broadcasting for dashboard clients."""

import json
from typing import Any

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

router = APIRouter(tags=["dashboard"])


class EventConnectionManager:
    """Track dashboard WebSocket clients and broadcast event updates."""

    def __init__(self) -> None:
        self._connections: set[WebSocket] = set()

    async def connect(self, websocket: WebSocket) -> None:
        """Accept and track a WebSocket client."""

        await websocket.accept()
        self._connections.add(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        """Remove a disconnected WebSocket client."""

        self._connections.discard(websocket)

    async def broadcast(self, payload: dict[str, Any]) -> None:
        """Send payload to all connected clients, dropping failed sockets."""

        message = json.dumps(payload)
        stale_connections: list[WebSocket] = []
        for websocket in self._connections:
            try:
                await websocket.send_text(message)
            except RuntimeError:
                stale_connections.append(websocket)

        for websocket in stale_connections:
            self.disconnect(websocket)


event_manager = EventConnectionManager()


@router.websocket("/ws/events")
async def events_websocket(websocket: WebSocket) -> None:
    """Keep dashboard clients connected for event notifications."""

    await event_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except WebSocketDisconnect:
        event_manager.disconnect(websocket)


async def broadcast_event_created(event_id: int, camera_id: str) -> None:
    """Broadcast that a new event is available."""

    await event_manager.broadcast(
        {"type": "event_created", "event_id": event_id, "camera_id": camera_id}
    )
