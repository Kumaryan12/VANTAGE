from typing import Literal
from urllib.parse import quote

from fastapi import APIRouter, Request
from fastapi.responses import Response
from pydantic import Field
from sqlalchemy import select

from app.api.routes import DB, Browser, owner
from app.auth.identity import AUTH_COOKIE, authenticate, require_user
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import (
    DeletionRequest,
    OwnershipScope,
    ResearchDocument,
    ResearchExperiment,
)
from app.portfolios.schemas import StrictModel
from app.storage import service
from app.storage.lifecycle import begin_delete, execute_delete

router = APIRouter(prefix="/api/v1/storage", tags=["Private artifacts and lifecycle"])


class DeleteWorkspace(StrictModel):
    confirmation: Literal["DELETE THIS WORKSPACE"]
    acknowledge_backup_retention: Literal[True]


class RetryDeletion(StrictModel):
    request_id: str = Field(min_length=36, max_length=36)


@router.get("/usage")
def usage(session: Browser, db: DB):
    return {
        "private_object_bytes": service.usage(db, owner(session)),
        "private_object_quota_bytes": settings().storage_quota_mb * 1024 * 1024,
        "scope": "All private objects across this account's owned workspaces; legacy/SQL evidence is tracked separately.",
        "offline_backup_deletion": "Follows backup retention, not immediate erasure.",
    }


@router.get("/artifacts/{ident}")
def download(ident: str, session: Browser, db: DB):
    row = service.owned(db, ident, owner(session))
    if row.parent_id and row.category == "document":
        parent = db.get(ResearchDocument, row.parent_id)
        if parent is None or parent.owner != row.owner or parent.status != "ready":
            raise AppError("ARTIFACT_NOT_FOUND", "Validated source artifact is unavailable.", 404)
    if row.parent_id and row.category == "model":
        parent = db.get(ResearchExperiment, row.parent_id)
        if (
            parent is None
            or parent.owner != row.owner
            or parent.status not in ("completed", "partial")
        ):
            raise AppError("ARTIFACT_NOT_FOUND", "Published model artifact is unavailable.", 404)
    content = service.read_manifest(service.manifest(row), row.owner)
    return Response(
        content,
        media_type="application/octet-stream",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(row.id)}",
            "Content-Security-Policy": "sandbox; default-src 'none'",
        },
    )


@router.post("/workspace-deletion")
def delete_workspace(
    body: DeleteWorkspace, request: Request, response: Response, session: Browser, db: DB
):
    actor = require_user(session)
    deletion = begin_delete(db, owner(session), actor)
    result = execute_delete(db, deletion)
    from app.auth.identity import issue_session, set_cookie
    from app.database.models import User

    token, _ = issue_session(db, db.get(User, actor), request.cookies.get(AUTH_COOKIE))
    db.commit()
    set_cookie(response, token)
    return {"id": result.id, "status": result.status, "outcome": result.outcome}


@router.get("/deletions")
def deletions(request: Request, db: DB):
    user, _ = authenticate(db, request.cookies.get(AUTH_COOKIE))
    rows = db.scalars(
        select(DeletionRequest)
        .where(DeletionRequest.actor_id == user.id)
        .order_by(DeletionRequest.created_at.desc())
        .limit(30)
    ).all()
    return [
        {"id": r.id, "status": r.status, "outcome": r.outcome, "created_at": r.created_at}
        for r in rows
    ]


@router.post("/deletions/retry")
def retry_deletion(body: RetryDeletion, request: Request, db: DB):
    user, _ = authenticate(db, request.cookies.get(AUTH_COOKIE))
    row = db.get(DeletionRequest, body.request_id)
    scope = db.get(OwnershipScope, row.owner) if row else None
    if row is None or row.actor_id != user.id or scope is None or scope.user_id != user.id:
        raise AppError("DELETION_NOT_FOUND", "Deletion request not found in this account.", 404)
    result = execute_delete(db, row)
    return {"id": result.id, "status": result.status, "outcome": result.outcome}
