import json
import logging
import uuid
from collections import defaultdict

from fastapi import WebSocket

logger = logging.getLogger("pulse.ws")


class ConnectionManager:
    """Tracks active WebSocket connections per project. Events are fanned
    out by EventPublisher (app/ws/publisher.py), which polls the DB for
    changes on the same cadence regardless of which process (api, worker,
    or scheduler) caused them — so no cross-process pub/sub is needed."""

    def __init__(self) -> None:
        self._connections: dict[uuid.UUID, set[WebSocket]] = defaultdict(set)

    def active_project_ids(self) -> list[uuid.UUID]:
        return [pid for pid, conns in self._connections.items() if conns]

    async def connect(self, project_id: uuid.UUID, websocket: WebSocket) -> None:
        await websocket.accept()
        self._connections[project_id].add(websocket)

    def disconnect(self, project_id: uuid.UUID, websocket: WebSocket) -> None:
        conns = self._connections.get(project_id)
        if conns is None:
            return
        conns.discard(websocket)
        if not conns:
            del self._connections[project_id]

    async def broadcast(self, project_id: uuid.UUID, message: dict) -> None:
        conns = self._connections.get(project_id)
        if not conns:
            return
        payload = json.dumps(message, default=str)
        dead: list[WebSocket] = []
        for ws in conns:
            try:
                await ws.send_text(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            conns.discard(ws)


manager = ConnectionManager()
