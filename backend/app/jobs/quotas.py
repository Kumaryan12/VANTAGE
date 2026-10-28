"""SQL provider reservations across processes; no prompt, token or upstream body is stored."""

import time

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.orm import Session

from app.auth.identity import token_hash
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import AuthThrottle, OwnershipScope


def increment(db, namespace, principal, amount, limit, seconds):
    constructor = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    statement = constructor(AuthThrottle).values(
        key=token_hash(namespace + ":" + principal),
        bucket=int(time.time()) // seconds,
        count=amount,
    )
    count = db.scalar(
        statement.on_conflict_do_update(
            index_elements=["key", "bucket"], set_={"count": AuthThrottle.count + amount}
        ).returning(AuthThrottle.count)
    )
    if count > limit:
        raise AppError(
            "PROVIDER_QUOTA",
            "Distributed provider request/token reservation budget reached. No upstream request was sent.",
            429,
        )


def reserve(engine, owner, provider, *, token_reservation=0):
    if settings().job_backend != "celery":
        return
    with Session(engine) as db:
        scope = db.get(OwnershipScope, owner)
        if scope is None or scope.lifecycle != "active":
            raise AppError(
                "PROVIDER_SCOPE", "Provider use requires an active authorized workspace.", 403
            )
        principal = scope.user_id or owner
        # Lock acquisition order is global, principal, daily. Each logical call reserves two
        # possible network attempts for existing bounded adapters; unused reservations expire.
        increment(db, provider + ":global", "deployment", 2, 120, 60)
        increment(db, provider + ":requests", principal, 2, 30, 60)
        if token_reservation:
            increment(
                db,
                provider + ":reserved_tokens",
                principal,
                token_reservation,
                settings().provider_daily_reserved_tokens,
                86400,
            )
        db.commit()
