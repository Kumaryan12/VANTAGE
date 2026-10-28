import secrets
import threading
import time
from dataclasses import dataclass

from fastapi import Depends, Request, Response
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.database.session import get_db

COOKIE = "vantage_session"
TTL = 12 * 60 * 60


@dataclass
class BrowserSession:
    id: str
    expires: float
    kite_token: str | None = None
    state: str | None = None
    state_expires: float = 0
    user_id: str | None = None
    owner_id: str | None = None
    auth_session_id: str | None = None
    database: Session | None = None


class SessionStore:
    def __init__(self):
        self.items: dict[str, BrowserSession] = {}
        self.lock = threading.RLock()

    def get(self, request: Request, response: Response) -> BrowserSession:
        with self.lock:
            now = time.time()
            for key in [key for key, item in self.items.items() if item.expires <= now]:
                del self.items[key]
            item = self.items.get(request.cookies.get(COOKIE, ""))
            if item is None:
                if len(self.items) >= 2000:
                    raise AppError("SESSION_CAPACITY", "Local session capacity reached.", 503)
                item = BrowserSession(secrets.token_urlsafe(32), now + TTL)
                self.items[item.id] = item
                response.set_cookie(
                    COOKIE,
                    item.id,
                    httponly=True,
                    secure=settings().cookie_secure,
                    samesite="lax",
                    max_age=TTL,
                    path="/",
                )
            return item

    def consume_state(self, item: BrowserSession, supplied: str):
        with self.lock:
            valid = (
                item.state
                and time.time() < item.state_expires
                and secrets.compare_digest(item.state, supplied)
            )
            item.state = None
            item.state_expires = 0
            if not valid:
                raise AppError(
                    "INVALID_AUTH_STATE",
                    "Login state is missing, expired, or invalid. Start a fresh Kite login.",
                    400,
                )


store = SessionStore()


def browser_session(
    request: Request, response: Response, db: Session = Depends(get_db)
) -> BrowserSession:
    from .identity import AUTH_COOKIE, authenticate, ensure_scope, token_hash

    token = request.cookies.get(AUTH_COOKIE)
    if token:
        user, row = authenticate(db, token)
        from app.database.models import OwnershipScope

        if db.get(OwnershipScope, row.scope_id).lifecycle != "active":
            raise AppError(
                "WORKSPACE_CLOSED",
                "This workspace is unavailable; select another owned workspace in account settings.",
                409,
            )
        return BrowserSession(
            id=row.id,
            expires=row.expires,
            user_id=user.id,
            owner_id=row.scope_id,
            auth_session_id=row.id,
            database=db,
        )
    if settings().auth_required:
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in to a durable research account.", 401)
    session = store.get(request, response)
    scope = ensure_scope(db, token_hash(session.id))
    if scope.user_id is not None:
        raise AppError(
            "LEGACY_SESSION_REVOKED", "This legacy workspace has been claimed. Sign in again.", 401
        )
    db.commit()
    return session


def enforce_required_auth(request: Request, db: Session = Depends(get_db)):
    if not settings().auth_required:
        return
    public = {
        "/api/health",
        "/api/health/live",
        "/api/health/ready",
        "/api/auth/me",
        "/api/auth/register",
        "/api/auth/login",
        "/api/auth/logout",
        "/api/auth/recover",
    }
    if request.url.path not in public:
        from .identity import AUTH_COOKIE, authenticate

        authenticate(db, request.cookies.get(AUTH_COOKIE))


def broker_token(session):
    if session.user_id:
        from app.security.vault import get

        return get(session.database, session.owner_id, actor=session.user_id)
    return session.kite_token


def set_broker_token(session, value):
    if session.user_id:
        from app.security.vault import put, revoke

        if value:
            put(session.database, session.owner_id, value, actor=session.user_id)
        else:
            revoke(session.database, session.owner_id, actor=session.user_id)
    else:
        session.kite_token = value


def broker_connected(session):
    if session.user_id:
        from app.security.vault import available

        return available(session.database, session.owner_id)
    return bool(session.kite_token)
