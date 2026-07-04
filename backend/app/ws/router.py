import logging
import uuid

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.core.rbac import ensure_role
from app.core.security import decode_token
from app.db import AsyncSessionLocal
from app.models.enums import MemberRole
from app.models.project import Project
from app.models.user import User
from app.ws.manager import manager

logger = logging.getLogger("pulse.ws")
router = APIRouter(tags=["ws"])


async def _authorize(token: str, project_id: uuid.UUID) -> User | None:
    async with AsyncSessionLocal() as db:
        try:
            payload = decode_token(token, expected_type="access")
            user = await db.get(User, uuid.UUID(payload["sub"]))
            if user is None:
                return None
            project = await db.get(Project, project_id)
            if project is None:
                return None
            await ensure_role(db, user, project.org_id, MemberRole.viewer)
            return user
        except Exception:
            return None


@router.websocket("/ws")
async def ws_endpoint(
    websocket: WebSocket,
    token: str = Query(...),
    project_id: uuid.UUID = Query(...),
) -> None:
    user = await _authorize(token, project_id)
    if user is None:
        await websocket.close(code=4401)
        return

    await manager.connect(project_id, websocket)
    logger.info(
        "ws connected",
        extra={"extra_fields": {"project_id": str(project_id), "user_id": str(user.id)}},
    )
    try:
        while True:
            # No client->server protocol beyond keeping the connection open;
            # just drain anything received (e.g. ping frames from a client lib).
            await websocket.receive_text()
    except WebSocketDisconnect:
        pass
    finally:
        manager.disconnect(project_id, websocket)
        logger.info("ws disconnected", extra={"extra_fields": {"project_id": str(project_id)}})
