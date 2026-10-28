import hashlib
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import func, select

from app.auth.identity import ensure_scope, security_event, write_scope
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import OwnershipScope, PrivateArtifact, User

from .backends import MAX_OBJECT_BYTES, backend, validate_key


def scope_owners(db, owner):
    scope = ensure_scope(db, owner)
    return (
        list(db.scalars(select(OwnershipScope.id).where(OwnershipScope.user_id == scope.user_id)))
        if scope.user_id
        else [owner]
    )


def usage(db, owner):
    owners = scope_owners(db, owner)
    return int(
        db.scalar(
            select(func.coalesce(func.sum(PrivateArtifact.size), 0)).where(
                PrivateArtifact.owner.in_(owners), PrivateArtifact.status != "deleted"
            )
        )
        or 0
    )


def reserve(db, owner, size):
    scope = write_scope(db, owner)
    # A durable principal lock serializes storage admissions across API/worker processes.
    if scope.user_id:
        db.execute(select(User.id).where(User.id == scope.user_id).with_for_update())
    else:
        db.execute(select(OwnershipScope.id).where(OwnershipScope.id == owner).with_for_update())
    if usage(db, owner) + size > settings().storage_quota_mb * 1024 * 1024:
        raise AppError(
            "STORAGE_QUOTA",
            "Private artifact storage quota exceeded. Delete eligible data or contact an authorized operator.",
            429,
        )


def store(db, owner, category, data, *, parent_id=None, published=True):
    if not isinstance(data, bytes) or not 1 <= len(data) <= MAX_OBJECT_BYTES:
        raise AppError("STORAGE_SIZE", "Private object size is outside the validated bound.", 413)
    reserve(db, owner, len(data))
    ident = str(uuid4())
    key = f"{owner}/{ident}"
    adapter = backend()
    adapter.put(key, category, data)
    row = PrivateArtifact(
        id=ident,
        owner=owner,
        category=category,
        backend=adapter.name,
        storage_key=key,
        content_hash=hashlib.sha256(data).hexdigest(),
        size=len(data),
        version="private-object-1",
        status="published" if published else "staged",
        parent_id=parent_id,
        created_at=datetime.now(UTC),
        expires_at=datetime.now(UTC) + timedelta(days=30)
        if category in {"export", "report"}
        else None,
    )
    db.add(row)
    db.flush()
    return {
        "object_id": ident,
        "path": key,
        "storage_key": key,
        "backend": adapter.name,
        "category": category,
        "sha256": row.content_hash,
        "bytes": row.size,
        "version": row.version,
    }


def read_manifest(manifest, owner=None):
    key = manifest["storage_key"]
    validate_key(key, manifest["category"])
    if owner and not key.startswith(owner + "/"):
        raise AppError(
            "STORAGE_SCOPE", "Private object is outside the authorized parent scope.", 404
        )
    if not 0 < manifest["bytes"] <= MAX_OBJECT_BYTES:
        raise AppError("STORAGE_SIZE", "Private object metadata has an invalid size.", 409)
    data = backend(manifest["backend"]).get(key, manifest["category"], manifest["bytes"])
    if len(data) != manifest["bytes"] or hashlib.sha256(data).hexdigest() != manifest["sha256"]:
        raise AppError("STORAGE_INTEGRITY", "Private object failed hash/size verification.", 409)
    return data


def owned(db, ident, owner):
    row = db.get(PrivateArtifact, ident)
    if row is None or row.owner != owner or row.status != "published":
        raise AppError("ARTIFACT_NOT_FOUND", "Published artifact not found in this workspace.", 404)
    return row


def manifest(row):
    return {
        "object_id": row.id,
        "storage_key": row.storage_key,
        "backend": row.backend,
        "category": row.category,
        "sha256": row.content_hash,
        "bytes": row.size,
        "version": row.version,
    }


def delete(db, row, actor=None):
    if row.status == "deleted":
        return
    backend(row.backend).delete(row.storage_key, row.category)
    row.status = "deleted"
    security_event(db, "artifact_deleted", actor, target=row.id, category=row.category)


def finalize(db, parent_id, referenced):
    ids = {m.get("object_id") for m in referenced if m.get("object_id")}
    for row in db.scalars(
        select(PrivateArtifact).where(
            PrivateArtifact.parent_id == parent_id, PrivateArtifact.status == "staged"
        )
    ).all():
        if row.id in ids:
            row.status = "published"
        else:
            delete(db, row)
