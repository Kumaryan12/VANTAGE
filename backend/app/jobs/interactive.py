"""Session-scoped PostgreSQL admission for legacy synchronous numerical endpoints."""

from contextlib import contextmanager

from sqlalchemy import text

from app.core.errors import AppError
from app.jobs.service import durable


@contextmanager
def calculation_lease(db):
    if db is None or not durable():
        yield
        return
    if db.get_bind().dialect.name != "postgresql":
        raise AppError(
            "DISTRIBUTED_DATABASE_REQUIRED",
            "Durable deployment requires PostgreSQL for cross-process numerical admission.",
            503,
        )
    # One bounded interactive calculation deployment-wide. SQL session locks release on
    # process/connection loss; a separate connection keeps the financial transaction intact.
    with db.get_bind().connect() as connection:
        acquired = connection.scalar(
            text("SELECT pg_try_advisory_lock(:key)"), {"key": 87201562001}
        )
        if not acquired:
            raise AppError(
                "RISK_ENGINE_BUSY",
                "The distributed interactive calculation slot is occupied. Queue a risk job or retry shortly.",
                429,
            )
        try:
            yield
        finally:
            try:
                connection.execute(text("SELECT pg_advisory_unlock(:key)"), {"key": 87201562001})
                connection.commit()
            except Exception:
                # Never return a connection with a retained session lock to the pool.
                connection.invalidate()
