"""Chaos engineering: kill a live worker on demand and watch the system heal.

A kill is a *hard* crash — no graceful drain, no status update. What
happens next is the point of the demo:

1. the worker's in-flight jobs are stranded in claimed/running;
2. its supervisor brings up a replacement (Kubernetes restarts the pod,
   docker-compose's restart policy or supervisord restarts the container);
3. after VISIBILITY_TIMEOUT_SEC without a heartbeat the reaper marks the
   old worker dead and recovers its jobs (at-least-once), charging an
   attempt to any job whose handler was mid-run.

Two kill mechanisms, picked by CHAOS_MODE:
- kubernetes: DELETE the worker's pod through the in-cluster API with
  gracePeriodSeconds=0 (SIGKILL). Needs the pod-delete Role in k8s/.
- signal: flag the worker row and NOTIFY it; the worker os._exit(137)s.
  Works anywhere, no cluster permissions needed.
"auto" uses kubernetes when running in-cluster, falling back to signal if
the API call fails.
"""

import logging
import os
import random
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.core import observability as obs
from app.core.errors import ForbiddenError, NotFoundError, UnprocessableError
from app.core.notify import notify_chaos_kill
from app.core.rbac import ensure_role
from app.core.scoping import get_project_or_404
from app.core.security import get_current_user
from app.db import get_db
from app.models.enums import MemberRole, WorkerStatus
from app.models.user import User
from app.models.worker import Worker

logger = logging.getLogger("pulse.chaos")
router = APIRouter(prefix="/chaos", tags=["chaos"])

SA_DIR = Path("/var/run/secrets/kubernetes.io/serviceaccount")


class ChaosStatus(BaseModel):
    enabled: bool
    mode: str
    live_workers: int


class ChaosKillRequest(BaseModel):
    project_id: uuid.UUID
    worker_id: uuid.UUID | None = None  # omitted = pick a random live worker


class ChaosKillResult(BaseModel):
    worker_id: uuid.UUID
    worker_name: str
    target: str
    mode: str
    detail: str


def _in_cluster() -> bool:
    return bool(os.environ.get("KUBERNETES_SERVICE_HOST")) and (SA_DIR / "token").exists()


def resolved_mode() -> str:
    mode = get_settings().chaos_mode.lower()
    if mode == "auto":
        return "kubernetes" if _in_cluster() else "signal"
    return mode


async def _delete_pod(pod_name: str) -> str:
    host = os.environ["KUBERNETES_SERVICE_HOST"]
    port = os.environ.get("KUBERNETES_SERVICE_PORT", "443")
    namespace = os.environ.get("POD_NAMESPACE") or (SA_DIR / "namespace").read_text().strip()
    token = (SA_DIR / "token").read_text().strip()
    url = f"https://{host}:{port}/api/v1/namespaces/{namespace}/pods/{pod_name}"

    async with httpx.AsyncClient(verify=str(SA_DIR / "ca.crt"), timeout=10) as client:
        response = await client.delete(
            url,
            headers={"Authorization": f"Bearer {token}"},
            params={"gracePeriodSeconds": 0},
        )
    response.raise_for_status()
    return f"deleted pod {namespace}/{pod_name} (grace period 0)"


def _live_filter(project_id: uuid.UUID):
    fresh_after = datetime.now(timezone.utc) - timedelta(
        seconds=get_settings().visibility_timeout_sec
    )
    return (
        Worker.project_id == project_id,
        Worker.status.in_([WorkerStatus.active, WorkerStatus.idle]),
        Worker.last_heartbeat_at >= fresh_after,
        Worker.chaos_kill_requested_at.is_(None),
    )


@router.get("/status", response_model=ChaosStatus)
async def chaos_status(
    project_id: uuid.UUID,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChaosStatus:
    project = await get_project_or_404(db, project_id)
    await ensure_role(db, user, project.org_id, MemberRole.viewer)
    live = (await db.scalars(select(Worker.id).where(*_live_filter(project_id)))).all()
    return ChaosStatus(
        enabled=get_settings().chaos_enabled, mode=resolved_mode(), live_workers=len(live)
    )


@router.post("/kill", response_model=ChaosKillResult)
async def chaos_kill(
    body: ChaosKillRequest,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ChaosKillResult:
    settings = get_settings()
    if not settings.chaos_enabled:
        raise ForbiddenError("Chaos engineering is disabled (CHAOS_ENABLED=false)")

    project = await get_project_or_404(db, body.project_id)
    # killing infrastructure is an admin action
    await ensure_role(db, user, project.org_id, MemberRole.admin)

    if body.worker_id is not None:
        worker = await db.scalar(
            select(Worker).where(Worker.id == body.worker_id, *_live_filter(body.project_id))
        )
        if worker is None:
            raise NotFoundError("No live worker with that id in this project")
    else:
        candidates = (await db.scalars(select(Worker).where(*_live_filter(body.project_id)))).all()
        if not candidates:
            raise UnprocessableError("There are no live workers to kill")
        worker = random.choice(candidates)

    mode = resolved_mode()
    detail = ""
    if mode == "kubernetes":
        try:
            detail = await _delete_pod(worker.hostname)
        except Exception as exc:
            logger.warning("pod delete failed, falling back to signal mode: %s", exc)
            mode = "signal"
            detail = f"pod delete failed ({type(exc).__name__}); "

    worker.chaos_kill_requested_at = datetime.now(timezone.utc)
    if mode == "signal":
        await notify_chaos_kill(db, str(worker.id))
        detail += "worker told to crash (exit 137); its supervisor will restart it"
    await db.commit()

    obs.CHAOS_KILLS.labels(mode).inc()
    logger.warning(
        "chaos kill issued",
        extra={"extra_fields": {
            "worker_id": str(worker.id), "worker": worker.name, "mode": mode,
            "user_id": str(user.id),
        }},
    )
    return ChaosKillResult(
        worker_id=worker.id,
        worker_name=worker.name,
        target=worker.hostname,
        mode=mode,
        detail=detail,
    )
