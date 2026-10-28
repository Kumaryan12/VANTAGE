"""Authenticated encryption using cryptography Fernet; keys never live in the database."""

import json
import re
import time
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from cryptography.fernet import Fernet, InvalidToken
from sqlalchemy import select

from app.auth.identity import security_event
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import OwnershipScope, ProviderCredential


def keyring():
    config = settings()
    try:
        if config.master_key_file:
            path = Path(config.master_key_file)
            if not path.is_file() or path.stat().st_size > 8192:
                raise ValueError()
            raw = path.read_text()
        else:
            raw = config.master_keys
        values = json.loads(raw or "{}")
        if (
            not isinstance(values, dict)
            or not 1 <= len(values) <= 8
            or config.master_key_active not in values
        ):
            raise ValueError()
        if any(not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", k) for k in values):
            raise ValueError()
        return {k: Fernet(v.encode()) for k, v in values.items()}
    except (ValueError, TypeError, OSError, AttributeError):
        raise AppError(
            "SECRETS_CONFIGURATION",
            "A valid external versioned encryption keyring is required for persistent credentials.",
            503,
        ) from None


def credential(db, owner, provider="kite"):
    return db.scalar(
        select(ProviderCredential).where(
            ProviderCredential.owner == owner, ProviderCredential.provider == provider
        )
    )


def available(db, owner, provider="kite"):
    row = credential(db, owner, provider)
    return bool(row and not row.revoked and row.expires > time.time())


def put(db, owner, value, *, actor=None, provider="kite", expires=None):
    if provider != "kite" or not isinstance(value, str) or not 1 <= len(value) <= 4096:
        raise AppError("CREDENTIAL_INPUT", "Unsupported credential or invalid credential size.")
    scope = db.get(OwnershipScope, owner)
    if scope is None or scope.user_id is None or (actor and scope.user_id != actor):
        raise AppError("CREDENTIAL_SCOPE", "A durable authorized owner is required.", 403)
    keys = keyring()
    row = credential(db, owner, provider)
    if row is None:
        row = ProviderCredential(id=str(uuid4()), owner=owner, provider=provider, revision=0)
        db.add(row)
    row.revision += 1
    row.expires = (
        int(time.time()) + settings().kite_token_lifetime_hours * 3600
        if expires is None
        else int(expires)
    )
    payload = {
        "expires": row.expires,
        "version": 1,
        "id": row.id,
        "owner": owner,
        "provider": provider,
        "revision": row.revision,
        "value": value,
    }
    row.key_id = settings().master_key_active
    row.ciphertext = (
        keys[row.key_id].encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()
    )
    row.revoked = 0
    row.updated_at = datetime.now(UTC)
    security_event(
        db, "credential_stored", actor, target=row.id, provider=provider, key_id=row.key_id
    )
    db.commit()
    return row


def decrypt(row):
    try:
        key = keyring().get(row.key_id)
        if key is None:
            raise InvalidToken()
        payload = json.loads(key.decrypt(row.ciphertext.encode()))
        if any(
            payload.get(k) != v
            for k, v in {
                "version": 1,
                "id": row.id,
                "owner": row.owner,
                "provider": row.provider,
                "revision": row.revision,
                "expires": row.expires,
            }.items()
        ) or not isinstance(payload.get("value"), str):
            raise InvalidToken()
        return payload["value"]
    except (InvalidToken, ValueError, TypeError, KeyError):
        raise AppError(
            "CREDENTIAL_INTEGRITY",
            "Stored credential could not be authenticated. Revoke it and reconnect; no fallback credential is used.",
            503,
        ) from None


def get(db, owner, provider="kite", *, actor=None):
    scope = db.get(OwnershipScope, owner)
    if scope is None or (actor and scope.user_id != actor):
        raise AppError("CREDENTIAL_SCOPE", "Credential unavailable in this scope.", 404)
    row = credential(db, owner, provider)
    if row is None or row.revoked or row.expires <= time.time():
        return None
    value = decrypt(row)
    security_event(db, "credential_used", actor, target=row.id, provider=provider)
    db.commit()
    return value


def revoke(db, owner, provider="kite", *, actor=None):
    scope = db.get(OwnershipScope, owner)
    if scope is None or (actor and scope.user_id != actor):
        raise AppError("CREDENTIAL_SCOPE", "Credential unavailable in this scope.", 404)
    row = credential(db, owner, provider)
    if row:
        row.revoked = 1
        row.ciphertext = (
            ""  # Active-store cryptographic material is removed; old backups follow retention.
        )
        row.updated_at = datetime.now(UTC)
        security_event(db, "credential_revoked", actor, target=row.id, provider=provider)
        db.commit()


def rotate(db):
    keys = keyring()
    active = settings().master_key_active
    rows = db.scalars(select(ProviderCredential).where(ProviderCredential.revoked == 0)).all()
    for row in rows:
        value = decrypt(row)
        payload = {
            "version": 1,
            "expires": row.expires,
            "id": row.id,
            "owner": row.owner,
            "provider": row.provider,
            "revision": row.revision,
            "value": value,
        }
        row.ciphertext = (
            keys[active].encrypt(json.dumps(payload, separators=(",", ":")).encode()).decode()
        )
        row.key_id = active
        row.updated_at = datetime.now(UTC)
        security_event(db, "credential_key_rotated", target=row.id, key_id=active)
    db.commit()
    return len(rows)
