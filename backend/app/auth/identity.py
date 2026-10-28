"""Durable opaque sessions and owner-workspace bindings; never rewrite financial evidence."""

import hashlib
import secrets
import time
from datetime import UTC, datetime
from uuid import uuid4

from pwdlib import PasswordHash
from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.exc import IntegrityError

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import (
    AuthSession,
    AuthThrottle,
    OwnershipScope,
    RecoveryToken,
    Role,
    SecurityEvent,
    User,
    UserRoleAssignment,
)

AUTH_COOKIE = "vantage_auth"
ROLES = ("USER", "RESEARCH_REVIEWER", "RESEARCH_ADMIN", "PLATFORM_ADMIN")
passwords = PasswordHash.recommended()
DUMMY_HASH = passwords.hash(secrets.token_urlsafe(32))


def token_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def insert_ignore(db, model, values, keys):
    constructor = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    return db.execute(
        constructor(model).values(**values).on_conflict_do_nothing(index_elements=keys)
    )


def ensure_scope(db, ident):
    if db.get(OwnershipScope, ident) is None:
        insert_ignore(
            db,
            OwnershipScope,
            {
                "id": ident,
                "user_id": None,
                "name": "Legacy research",
                "kind": "legacy",
                "created_at": datetime.now(UTC),
            },
            ["id"],
        )
    return db.get(OwnershipScope, ident)


def security_event(db, action, actor=None, target=None, **safe_metadata):
    db.add(
        SecurityEvent(
            id=str(uuid4()),
            actor_id=actor,
            action=action,
            target_id=target,
            created_at=datetime.now(UTC),
            payload=safe_metadata,
        )
    )


def throttle(db, namespace, value, limit, seconds):
    now = int(time.time())
    bucket = now // seconds
    key = token_hash(namespace + ":" + value)
    constructor = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = constructor(AuthThrottle).values(key=key, bucket=bucket, count=1)
    count = db.scalar(
        statement.on_conflict_do_update(
            index_elements=["key", "bucket"], set_={"count": AuthThrottle.count + 1}
        ).returning(AuthThrottle.count)
    )
    db.commit()
    if count > limit:
        raise AppError("AUTH_RATE_LIMIT", "Authentication limit reached. Try again later.", 429)


def validate_password(value, email=""):
    common = {
        "passwordpassword",
        "123456789012345",
        "letmeinletmeinletmein",
        "correcthorsebatterystaple",
    }
    if (
        len(value) < 15
        or len(value) > 128
        or len(set(value.casefold())) < 5
        or value.casefold() in common
        or (
            email
            and len(email.split("@")[0]) >= 4
            and email.split("@")[0].casefold() in value.casefold()
        )
    ):
        raise AppError(
            "PASSWORD_QUALITY",
            "Use a unique password of 15–128 characters, avoiding common passwords, repetitive text and your email name.",
        )


def roles_for(db, user_id):
    return list(
        db.scalars(
            select(UserRoleAssignment.role).where(UserRoleAssignment.user_id == user_id)
        ).all()
    )


def create_user(db, email, password, *, actor=None):
    email = str(email).casefold()
    validate_password(password, email)
    encoded = passwords.hash(password)
    if db.scalar(select(User.id).where(User.email == email)):
        return None
    user = User(
        id=str(uuid4()), email=email, password_hash=encoded, active=1, created_at=datetime.now(UTC)
    )
    db.add(user)
    db.flush()
    scope = OwnershipScope(
        id=token_hash(secrets.token_urlsafe(32)),
        user_id=user.id,
        name="Personal research",
        kind="personal",
        created_at=datetime.now(UTC),
    )
    db.add(scope)
    for role in ROLES:
        insert_ignore(db, Role, {"name": role}, ["name"])
    db.flush()
    user.preferred_scope = scope.id
    db.add(UserRoleAssignment(user_id=user.id, role="USER"))
    security_event(db, "account_created", actor, target=user.id)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        return None
    return user


def require_user(session):
    if not session.user_id:
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in to a durable research account.", 401)
    return session.user_id


def require_role(db, session, role):
    ident = require_user(session)
    if role not in roles_for(db, ident):
        raise AppError(
            "PERMISSION_DENIED", "This operation requires an explicitly assigned role.", 403
        )
    return ident


def authenticate(db, token, *, touch=True):
    if not token or len(token) > 128:
        raise AppError("AUTHENTICATION_REQUIRED", "Sign in to a durable research account.", 401)
    row = db.scalar(select(AuthSession).where(AuthSession.token_hash == token_hash(token)))
    now = int(time.time())
    user = db.get(User, row.user_id) if row else None
    scope = db.get(OwnershipScope, row.scope_id) if row else None
    if (
        row is None
        or row.revoked
        or row.expires <= now
        or row.last_seen + settings().auth_idle_minutes * 60 <= now
        or user is None
        or not user.active
        or scope is None
        or scope.user_id != user.id
    ):
        raise AppError("AUTHENTICATION_REQUIRED", "Session expired or revoked. Sign in again.", 401)
    if touch and now - row.last_seen >= 60:
        row.last_seen = now
        db.commit()
    return user, row


def issue_session(db, user, old_token=None, scope_id=None):
    if old_token:
        db.execute(
            update(AuthSession)
            .where(AuthSession.token_hash == token_hash(old_token))
            .values(revoked=1)
        )
    scope_id = scope_id or user.preferred_scope
    scope = db.get(OwnershipScope, scope_id)
    if not scope or scope.user_id != user.id:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found in this account.", 404)
    token = secrets.token_urlsafe(32)
    now = int(time.time())
    row = AuthSession(
        id=str(uuid4()),
        token_hash=token_hash(token),
        user_id=user.id,
        scope_id=scope.id,
        created_at=datetime.now(UTC),
        expires=now + settings().auth_session_hours * 3600,
        last_seen=now,
        revoked=0,
    )
    db.add(row)
    return token, row


def set_cookie(response, token):
    response.set_cookie(
        AUTH_COOKIE,
        token,
        httponly=True,
        secure=settings().cookie_secure,
        samesite="lax",
        max_age=settings().auth_session_hours * 3600,
        path="/",
    )


def login(db, email, password, old_token, ip):
    email = str(email).casefold()
    throttle(db, "login-address", ip, 50, 900)
    throttle(db, "login-account", email, 10, 900)
    user = db.scalar(select(User).where(User.email == email))
    valid, replacement = passwords.verify_and_update(
        password, user.password_hash if user else DUMMY_HASH
    )
    if not valid or user is None or not user.active:
        security_event(db, "login_failed", target=token_hash(email))
        db.commit()
        raise AppError("INVALID_CREDENTIALS", "Email or password is invalid.", 401)
    if replacement:
        user.password_hash = replacement
    token, row = issue_session(db, user, old_token)
    security_event(db, "login", user.id, target=row.id)
    db.commit()
    return token, user, row


def issue_recovery(db, user_id, actor=None):
    user = db.get(User, user_id)
    if not user or not user.active:
        raise AppError("ACCOUNT_UNAVAILABLE", "Account unavailable.", 404)
    db.execute(update(RecoveryToken).where(RecoveryToken.user_id == user_id).values(used=1))
    token = secrets.token_urlsafe(32)
    db.add(
        RecoveryToken(
            token_hash=token_hash(token), user_id=user_id, expires=int(time.time()) + 900, used=0
        )
    )
    security_event(db, "recovery_issued", actor, target=user_id)
    db.commit()
    return token


def recover(db, token, password):
    row = db.get(RecoveryToken, token_hash(token))
    user = db.get(User, row.user_id) if row else None
    if (
        row is None
        or row.used
        or row.expires <= int(time.time())
        or user is None
        or not user.active
    ):
        raise AppError("RECOVERY_INVALID", "Recovery token is invalid or expired.", 400)
    validate_password(password, user.email)
    claimed = db.execute(
        update(RecoveryToken)
        .where(
            RecoveryToken.token_hash == row.token_hash,
            RecoveryToken.used == 0,
            RecoveryToken.expires > int(time.time()),
        )
        .values(used=1)
    ).rowcount
    if not claimed:
        db.rollback()
        raise AppError("RECOVERY_INVALID", "Recovery token is invalid or expired.", 400)
    user.password_hash = passwords.hash(password)
    db.execute(update(AuthSession).where(AuthSession.user_id == user.id).values(revoked=1))
    security_event(db, "password_recovered", user.id, target=user.id)
    db.commit()


def claim_legacy(db, user, auth_session, legacy):
    ident = token_hash(legacy.id)
    scope = ensure_scope(db, ident)
    if scope.user_id is not None:
        raise AppError("LEGACY_CLAIM_UNAVAILABLE", "This legacy workspace cannot be claimed.", 409)
    claimed = db.execute(
        update(OwnershipScope)
        .where(OwnershipScope.id == ident, OwnershipScope.user_id.is_(None))
        .values(user_id=user.id, name="Recovered legacy research", claimed_at=datetime.now(UTC))
    ).rowcount
    if not claimed:
        db.rollback()
        raise AppError("LEGACY_CLAIM_UNAVAILABLE", "This legacy workspace cannot be claimed.", 409)
    user.preferred_scope = ident
    auth_session.revoked = 1
    token, new = issue_session(db, user, scope_id=ident)
    security_event(
        db,
        "legacy_workspace_claimed",
        user.id,
        target=ident,
        proof="live_original_session",
        financial_records_rewritten=False,
    )
    db.commit()
    return token, new
