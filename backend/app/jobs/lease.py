"""Every worker commit is fenced against the SQL lease, including intermediate trace writes."""

from contextvars import ContextVar
from dataclasses import dataclass
from datetime import UTC, datetime

from sqlalchemy import event, select, update
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.database.models import BackgroundJob, OwnershipScope

current = ContextVar("vantage_job_execution", default=None)


@dataclass(frozen=True)
class Execution:
    job_id: str
    token: str
    engine: object
    kind: str = ""


def is_worker():
    return current.get() is not None


def verify(db, execution):
    from .service import utc

    with db.no_autoflush:
        row = (
            db.execute(
                select(BackgroundJob.__table__)
                .where(BackgroundJob.id == execution.job_id)
                .with_for_update()
            )
            .mappings()
            .one_or_none()
        )
        if (
            row is None
            or row["lease_token"] != execution.token
            or row["status"] not in {"running", "cancel_requested"}
        ):
            raise AppError(
                "JOB_FENCED",
                "Worker lease is no longer authorized; no late result is published.",
                409,
            )
        if row["status"] == "cancel_requested":
            raise AppError(
                "JOB_CANCELLED", "Cancellation accepted; no late success is published.", 409
            )
        if utc(row["lease_expires"]) <= datetime.now(UTC):
            raise AppError("JOB_FENCED", "Worker lease expired; no late result is published.", 409)
        scope = db.get(OwnershipScope, row["owner"])
        if scope is None or scope.lifecycle != "active":
            raise AppError("WORKSPACE_CLOSED", "Workspace is closed to publication.", 409)
        return row


@event.listens_for(Session, "before_commit")
def fence_commit(db):
    execution = current.get()
    if execution is None or db.get_bind() is not execution.engine:
        return
    row = verify(db, execution)
    from app.risk.artifacts import digest

    from .service import SUCCESS, root_model

    model = root_model(row["kind"])
    root = next(
        (
            obj
            for obj in db.identity_map.values()
            if model and isinstance(obj, model) and obj.id == row["target_id"]
        ),
        None,
    )
    explicit = db.info.pop("job_publication", None)
    if explicit is not None:
        publish(db, execution, row, explicit)
    elif root is not None and root.status in SUCCESS:
        sealed = (
            root.result
            if row["kind"] == "optimization"
            else root.summary
            if row["kind"] == "research"
            else root.answer
            if row["kind"] == "agent"
            else root.payload
            if row["kind"] == "evaluation"
            else {
                "content_hash": root.content_hash,
                "version": root.version,
                "processing": root.processing,
            }
        )
        publish(
            db,
            execution,
            row,
            {
                "kind": row["kind"],
                "target_id": root.id,
                "status": root.status,
                "result_hash": digest(sealed),
            },
        )


def publish(db, execution, row, result):
    history = list(row["attempt_history"])
    history[-1] = {
        **history[-1],
        "status": "completed",
        "finished_at": datetime.now(UTC).isoformat(),
    }
    db.execute(
        update(BackgroundJob)
        .where(BackgroundJob.id == execution.job_id, BackgroundJob.lease_token == execution.token)
        .values(
            status="completed",
            finished_at=datetime.now(UTC),
            result_reference=result,
            attempt_history=history,
        )
    )


class Cancellation:
    def __init__(self, execution):
        self.execution = execution

    def is_set(self):
        try:
            with Session(self.execution.engine) as db:
                verify(db, self.execution)
            return False
        except AppError:
            return True
