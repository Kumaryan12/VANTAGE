"""Explicit account operations. Secrets never appear in account projections or audit payloads."""

import time

from fastapi import APIRouter, Query, Request, Response
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError

from app.api.routes import DB, Browser
from app.auth import identity as service
from app.auth.contracts import (
    Credentials,
    PasswordChange,
    RecoverAccount,
    RoleChange,
    UserStatus,
    WorkspaceSelection,
)
from app.auth.sessions import COOKIE, store
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import AuthSession, OwnershipScope, SecurityEvent, User, UserRoleAssignment

router = APIRouter(prefix="/api/auth", tags=["Durable research identity"])


def principal(request, db):
    return service.authenticate(db, request.cookies.get(service.AUTH_COOKIE))


def public_user(db, user, row):
    return {
        "authenticated": True,
        "user": {"id": user.id, "email": user.email, "roles": service.roles_for(db, user.id)},
        "workspace_id": row.scope_id,
        "session_id": row.id,
        "expires": row.expires,
        "registration_enabled": settings().registration_enabled,
    }


@router.get("/me")
def me(request: Request, db: DB):
    token = request.cookies.get(service.AUTH_COOKIE)
    if not token:
        return {
            "authenticated": False,
            "registration_enabled": settings().registration_enabled,
            "authentication_required": settings().auth_required,
        }
    user, row = principal(request, db)
    return public_user(db, user, row)


@router.post("/register", status_code=202)
def register(body: Credentials, request: Request, db: DB):
    if not settings().registration_enabled:
        raise AppError(
            "REGISTRATION_DISABLED",
            "Accounts are administrator-provisioned in this environment.",
            403,
        )
    service.throttle(
        db, "registration", request.client.host if request.client else "unknown", 5, 3600
    )
    try:
        service.create_user(db, body.email, body.password)
    except IntegrityError:
        db.rollback()
    return {
        "message": "Registration processed. If the account is available, sign in with the supplied credentials."
    }


@router.post("/login")
def login(body: Credentials, request: Request, response: Response, db: DB):
    token, user, row = service.login(
        db,
        body.email,
        body.password,
        request.cookies.get(service.AUTH_COOKIE),
        request.client.host if request.client else "unknown",
    )
    service.set_cookie(response, token)
    return public_user(db, user, row)


@router.post("/logout")
def logout(request: Request, response: Response, db: DB):
    token = request.cookies.get(service.AUTH_COOKIE)
    if token:
        row = db.scalar(
            select(AuthSession).where(AuthSession.token_hash == service.token_hash(token))
        )
        if row and not row.revoked:
            row.revoked = 1
            service.security_event(db, "logout", row.user_id, target=row.id)
            db.commit()
    response.delete_cookie(
        service.AUTH_COOKIE,
        path="/",
        secure=settings().cookie_secure,
        httponly=True,
        samesite="lax",
    )
    return {"authenticated": False}


@router.post("/rotate")
def rotate(request: Request, response: Response, db: DB):
    user, old = principal(request, db)
    token, row = service.issue_session(
        db, user, request.cookies.get(service.AUTH_COOKIE), old.scope_id
    )
    service.security_event(db, "session_rotated", user.id, target=old.id)
    db.commit()
    service.set_cookie(response, token)
    return public_user(db, user, row)


@router.get("/sessions")
def sessions(request: Request, db: DB):
    user, current = principal(request, db)
    rows = db.scalars(
        select(AuthSession)
        .where(AuthSession.user_id == user.id)
        .order_by(AuthSession.created_at.desc())
        .limit(50)
    ).all()
    return [
        {
            "id": r.id,
            "current": r.id == current.id,
            "expires": r.expires,
            "revoked": bool(r.revoked),
            "last_seen": r.last_seen,
        }
        for r in rows
    ]


@router.post("/sessions/{ident}/revoke")
def revoke_session(ident: str, request: Request, db: DB):
    user, _ = principal(request, db)
    row = db.get(AuthSession, ident)
    if row is None or row.user_id != user.id:
        raise AppError("SESSION_NOT_FOUND", "Session not found in this account.", 404)
    row.revoked = 1
    service.security_event(db, "session_revoked", user.id, target=row.id)
    db.commit()
    return {"revoked": True}


@router.post("/password")
def change_password(body: PasswordChange, request: Request, response: Response, db: DB):
    user, old = principal(request, db)
    service.throttle(db, "password-change", user.id, 5, 900)
    if not service.passwords.verify(body.current_password, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Current credentials are invalid.", 401)
    service.validate_password(body.new_password, user.email)
    user.password_hash = service.passwords.hash(body.new_password)
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=1))
    token, row = service.issue_session(db, user, scope_id=old.scope_id)
    service.security_event(db, "password_changed", user.id, target=user.id)
    db.commit()
    service.set_cookie(response, token)
    return public_user(db, user, row)


@router.post("/recover")
def recovery(body: RecoverAccount, request: Request, db: DB):
    service.throttle(db, "recovery", request.client.host if request.client else "unknown", 10, 900)
    service.recover(db, body.token, body.new_password)
    return {"message": "Recovery completed. Sign in again; previous sessions were revoked."}


@router.get("/workspaces")
def workspaces(request: Request, db: DB):
    user, _ = principal(request, db)
    return [
        {"id": r.id, "name": r.name, "kind": r.kind}
        for r in db.scalars(select(OwnershipScope).where(OwnershipScope.user_id == user.id)).all()
    ]


@router.post("/workspace")
def choose_workspace(body: WorkspaceSelection, request: Request, response: Response, db: DB):
    user, old = principal(request, db)
    scope = db.get(OwnershipScope, body.scope_id)
    if scope is None or scope.user_id != user.id:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found in this account.", 404)
    user.preferred_scope = scope.id
    token, row = service.issue_session(db, user, request.cookies.get(service.AUTH_COOKIE), scope.id)
    service.security_event(db, "workspace_selected", user.id, target=scope.id)
    db.commit()
    service.set_cookie(response, token)
    return public_user(db, user, row)


@router.post("/claim-legacy")
def claim_legacy(request: Request, response: Response, db: DB):
    user, row = principal(request, db)
    legacy_token = request.cookies.get(COOKIE)
    with store.lock:
        legacy = store.items.get(legacy_token)
        if legacy is None or legacy.expires <= time.time():
            raise AppError(
                "LEGACY_PROOF_REQUIRED",
                "A still-live original legacy session is required; lost or expired sessions cannot be recovered automatically.",
                409,
            )
        token, new = service.claim_legacy(db, user, row, legacy)
        store.items.pop(legacy_token, None)
    response.delete_cookie(COOKIE, path="/")
    service.set_cookie(response, token)
    return public_user(db, user, new)


@router.get("/security-events")
def security_events(request: Request, db: DB, limit: int = Query(30, ge=1, le=100)):
    user, _ = principal(request, db)
    rows = db.scalars(
        select(SecurityEvent)
        .where(SecurityEvent.actor_id == user.id)
        .order_by(SecurityEvent.created_at.desc())
        .limit(limit)
    ).all()
    return [
        {
            "id": r.id,
            "action": r.action,
            "target_id": r.target_id,
            "created_at": r.created_at,
            "metadata": r.payload,
        }
        for r in rows
    ]


@router.get("/admin/users")
def list_users(session: Browser, db: DB):
    service.require_role(db, session, "PLATFORM_ADMIN")
    return [
        {
            "id": u.id,
            "email": u.email,
            "active": bool(u.active),
            "roles": service.roles_for(db, u.id),
        }
        for u in db.scalars(select(User).limit(100)).all()
    ]


@router.post("/admin/users/{ident}/status")
def user_status(ident: str, body: UserStatus, session: Browser, db: DB):
    actor = service.require_role(db, session, "PLATFORM_ADMIN")
    user = db.get(User, ident)
    if user is None:
        raise AppError("USER_NOT_FOUND", "User not found.", 404)
    if actor == ident and not body.active:
        raise AppError(
            "ADMIN_SELF_SUSPEND",
            "Use another authorized administrator to suspend this account.",
            409,
        )
    user.active = int(body.active)
    if not body.active:
        db.execute(update(AuthSession).where(AuthSession.user_id == ident).values(revoked=1))
    service.security_event(db, "account_status_changed", actor, target=ident, active=body.active)
    db.commit()
    return {"active": body.active}


@router.post("/admin/users/{ident}/roles")
def user_role(ident: str, body: RoleChange, session: Browser, db: DB):
    actor = service.require_role(db, session, "PLATFORM_ADMIN")
    if db.get(User, ident) is None:
        raise AppError("USER_NOT_FOUND", "User not found.", 404)
    if actor == ident and body.role == "PLATFORM_ADMIN" and not body.enabled:
        raise AppError(
            "ADMIN_SELF_DEMOTION", "Use another authorized administrator to remove this role.", 409
        )
    if body.role == "USER" and not body.enabled:
        raise AppError(
            "BASE_ROLE_REQUIRED",
            "Suspend the account to revoke base access; the USER role is required.",
            409,
        )
    if body.enabled:
        service.insert_ignore(
            db, UserRoleAssignment, {"user_id": ident, "role": body.role}, ["user_id", "role"]
        )
    else:
        row = db.get(UserRoleAssignment, (ident, body.role))
        if row:
            db.delete(row)
    service.security_event(
        db, "role_changed", actor, target=ident, role=body.role, enabled=body.enabled
    )
    db.commit()
    return {"roles": service.roles_for(db, ident)}


@router.get("/legacy-status")
def legacy_status(request: Request, db: DB):
    principal(request, db)
    with store.lock:
        row = store.items.get(request.cookies.get(COOKIE))
        available = bool(row and row.expires > time.time())
    return {
        "proof_available": available,
        "limitation": "Only the still-live original session can prove ownership. Lost or expired sessions have no automatic recovery.",
    }
