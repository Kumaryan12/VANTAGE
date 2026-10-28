"""SQL authoritative job state and outbox; Celery delivers opaque IDs at least once."""

import time
from concurrent.futures import TimeoutError
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.orm import Session

from app.auth.identity import insert_ignore, security_event, write_scope
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import BackgroundJob, OperationGate, OwnershipScope
from app.risk.artifacts import digest

ACTIVE = ("queued", "retrying", "running", "cancel_requested")
SUCCESS = ("completed", "partial", "limited", "ready")
BUDGETS = {
    "research": 240,
    "optimization": 110,
    "document": 90,
    "agent": 120,
    "evaluation": 900,
    "risk": 90,
    "report": 60,
}
CONCURRENCY = {
    "research": 1,
    "optimization": 2,
    "document": 2,
    "agent": 2,
    "evaluation": 1,
    "risk": 2,
    "report": 1,
}


def durable():
    value = settings().job_backend
    if value not in {"local", "celery"}:
        raise AppError("JOBS_CONFIGURATION", "Unknown execution backend.", 503)
    return value == "celery"


def tracked(db, target):
    return (
        db.scalar(select(BackgroundJob.id).where(BackgroundJob.target_id == target).limit(1))
        is not None
    )


def root_model(kind):
    from app.database import models as m

    return {
        "research": m.ResearchExperiment,
        "optimization": m.OptimizationRun,
        "document": m.ResearchDocument,
        "agent": m.AgentInvestigation,
        "evaluation": m.AgentEvaluation,
    }.get(kind)


def reference(kind, row):
    if kind in {"research", "optimization"}:
        return {
            "target": row.id,
            "input_hash": row.input_hash,
            "parameters": row.parameters,
            "runtime": row.runtime,
        }
    if kind == "agent":
        return {
            "target": row.id,
            "request": row.request,
            "context": row.context,
            "workflow": row.provider["workflow_version"],
        }
    if kind == "document":
        return {
            "target": row.id,
            "content_hash": row.content_hash,
            "version": row.version,
            "chunk_chars": row.processing["chunk_chars"],
            "chunk_overlap": row.processing["chunk_overlap"],
            "semantic_requested": row.processing["semantic_requested"],
            "external_data_consent": row.processing["external_data_consent"],
        }
    if kind == "evaluation":
        import hashlib

        from app.agent.evaluation import GOLDEN_PATH

        return {
            "target": row.id,
            "suite": row.payload["suite"],
            "golden_hash": hashlib.sha256(GOLDEN_PATH.read_bytes()).hexdigest(),
        }
    raise AppError("JOBS_KIND", "Unsupported job type.", 400)


def gate(db):
    insert_ignore(db, OperationGate, {"id": "jobs", "paused": 0}, ["id"])
    if db.get_bind().dialect.name == "sqlite":
        db.execute(
            update(OperationGate)
            .where(OperationGate.id == "jobs")
            .values(paused=OperationGate.paused)
        )
    return db.scalar(
        select(OperationGate)
        .where(OperationGate.id == "jobs")
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def admit(db, owner, kind, target_id, inputs, *, idempotency_key=None):
    if kind not in BUDGETS:
        raise AppError("JOBS_KIND", "Unsupported job type.")
    scope = write_scope(db, owner)
    principal = scope.user_id or owner
    control = gate(db)
    if control.paused:
        raise AppError("MAINTENANCE", "New background work is paused for maintenance.", 503)
    key = idempotency_key or target_id
    previous = db.scalar(
        select(BackgroundJob).where(
            BackgroundJob.owner == owner,
            BackgroundJob.kind == kind,
            BackgroundJob.idempotency_key == key,
        )
    )
    if previous:
        if previous.input_hash != digest(inputs):
            raise AppError(
                "IDEMPOTENCY_CONFLICT",
                "This request key is bound to different validated input.",
                409,
            )
        return previous
    active = select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status.in_(ACTIVE))
    if db.scalar(active) >= settings().job_queue_limit:
        raise AppError("QUEUE_CAPACITY", "Global bounded queue capacity reached.", 429)
    if (
        db.scalar(active.where(BackgroundJob.principal == principal))
        >= settings().job_per_user_limit
    ):
        raise AppError(
            "USER_JOB_QUOTA", "Account queued/running job limit reached across workspaces.", 429
        )
    if (
        db.scalar(active.where(BackgroundJob.principal == principal, BackgroundJob.kind == kind))
        >= 1
    ):
        raise AppError(
            "USER_KIND_QUOTA", "One job of this type is already active for this account.", 429
        )
    now = datetime.now(UTC)
    job = BackgroundJob(
        id=str(uuid4()),
        owner=owner,
        principal=principal,
        kind=kind,
        target_id=target_id,
        input_reference=inputs,
        input_hash=digest(inputs),
        idempotency_key=key,
        status="queued",
        created_at=now,
        available_at=now,
        attempts=0,
        max_attempts=1
        if kind in {"agent", "evaluation"}
        or (kind == "document" and inputs.get("semantic_requested"))
        else 3,
        timeout_seconds=BUDGETS[kind],
        attempt_history=[],
    )
    db.add(job)
    db.flush()
    security_event(db, "job_admitted", scope.user_id, target=job.id, kind=kind)
    return job


def enqueue(db, kind, row):
    return admit(db, row.owner, kind, row.id, reference(kind, row))


def view(job):
    return {
        k: getattr(job, k)
        for k in (
            "id",
            "kind",
            "target_id",
            "status",
            "created_at",
            "started_at",
            "finished_at",
            "attempts",
            "max_attempts",
            "timeout_seconds",
            "failure",
            "result_reference",
            "attempt_history",
        )
    }


def owned(db, ident, owner):
    job = db.scalar(
        select(BackgroundJob)
        .where(BackgroundJob.id == ident, BackgroundJob.owner == owner)
        .execution_options(populate_existing=True)
    )
    if job is None:
        raise AppError("JOB_NOT_FOUND", "Job not found in this workspace.", 404)
    return job


def lock_job(db, job):
    return db.scalar(
        select(BackgroundJob)
        .where(BackgroundJob.id == job.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )


def root_status(db, job, status, failure=None):
    model = root_model(job.kind)
    row = db.get(model, job.target_id) if model else None
    if row is None or row.status == "deleted":
        return
    if row.status in SUCCESS:
        raise AppError("JOB_IMMUTABLE", "Successful financial output cannot be overwritten.", 409)
    row.status = status
    if hasattr(row, "error"):
        row.error = failure
    if hasattr(row, "stage"):
        row.stage = (
            "Stopped without successful publication"
            if status != "queued"
            else "Queued for durable worker"
        )
    if hasattr(row, "answer"):
        row.answer = None
    if hasattr(row, "finished_at"):
        row.finished_at = (
            datetime.now(UTC) if status in {"failed", "cancelled", "interrupted"} else None
        )


def cancel(db, job):
    gate(db)
    job = lock_job(db, job)
    if job.status in ACTIVE:
        running = job.status in {"running", "cancel_requested"}
        job.status = "cancel_requested" if running else "cancelled"
        job.failure = {
            "code": "JOB_CANCELLED",
            "message": "Cancellation requested; in-flight bounded computation cannot publish a successful result.",
        }
        if not running:
            root_status(db, job, "cancelled", job.failure)
            job.finished_at = datetime.now(UTC)
            job.lease_token = None
        security_event(db, "job_cancel_requested", target=job.id)
        db.commit()
    return job


def retry(db, job):
    control = gate(db)
    job = lock_job(db, job)
    if job.status not in {"failed", "interrupted"} or job.attempts >= 3:
        raise AppError(
            "JOB_RETRY_DENIED",
            "Only failed/interrupted work below three attempts can be retried; successful/cancelled results are immutable.",
            409,
        )
    if control.paused:
        raise AppError("MAINTENANCE", "Background admission paused.", 503)
    active = select(func.count()).select_from(BackgroundJob).where(BackgroundJob.status.in_(ACTIVE))
    if (
        db.scalar(active) >= settings().job_queue_limit
        or db.scalar(active.where(BackgroundJob.principal == job.principal))
        >= settings().job_per_user_limit
        or db.scalar(
            active.where(BackgroundJob.principal == job.principal, BackgroundJob.kind == job.kind)
        )
    ):
        raise AppError("USER_JOB_QUOTA", "Retry exceeds active queue/account/type quota.", 429)
    scope = db.get(OwnershipScope, job.owner)
    if scope is None or scope.lifecycle != "active":
        raise AppError("WORKSPACE_CLOSED", "Workspace is closed.", 409)
    job.max_attempts = 3
    job.status = "retrying"
    job.available_at = datetime.now(UTC) + timedelta(seconds=2**job.attempts)
    job.lease_token = None
    job.dispatched_at = None
    job.finished_at = None
    root_status(db, job, "queued")
    security_event(db, "job_retry_requested", target=job.id)
    db.commit()
    return job


def cleanup_staged(db, job):
    from app.database.models import PrivateArtifact
    from app.storage.service import delete as delete_object

    for artifact in db.scalars(
        select(PrivateArtifact).where(
            PrivateArtifact.parent_id == job.target_id, PrivateArtifact.status == "staged"
        )
    ):
        delete_object(db, artifact)


def cleanup_attempt(db, job):
    from app.database.models import AgentEvidence, AgentStep, AgentToolCall

    if job.kind == "agent":
        for model in (AgentEvidence, AgentStep, AgentToolCall):
            db.execute(delete(model).where(model.investigation_id == job.target_id))
    cleanup_staged(db, job)


def claim(db, ident, worker_id):
    if gate(db).paused:
        db.rollback()
        return None
    job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == ident).with_for_update())
    now = datetime.now(UTC)
    if job is None or job.status not in {"queued", "retrying"} or utc(job.available_at) > now:
        db.rollback()
        return None
    if (
        db.scalar(
            select(func.count())
            .select_from(BackgroundJob)
            .where(BackgroundJob.kind == job.kind, BackgroundJob.status == "running")
        )
        >= CONCURRENCY[job.kind]
    ):
        db.rollback()
        return None
    scope = db.get(OwnershipScope, job.owner)
    if (
        scope is None
        or scope.lifecycle != "active"
        or digest(job.input_reference) != job.input_hash
    ):
        raise AppError("JOB_INPUT_INTEGRITY", "Saved job references are invalid.", 409)
    model = root_model(job.kind)
    row = db.get(model, job.target_id) if model else None
    if model and (
        row is None or row.owner != job.owner or reference(job.kind, row) != job.input_reference
    ):
        raise AppError("JOB_INPUT_INTEGRITY", "Captured input changed; job cannot execute.", 409)
    if row and row.status in SUCCESS:
        raise AppError("JOB_IMMUTABLE", "Successful output cannot be recomputed in place.", 409)
    job.status = "running"
    job.attempts += 1
    job.started_at = now
    job.finished_at = None
    job.lease_expires = now + timedelta(seconds=settings().job_lease_seconds)
    job.lease_token = str(uuid4())
    job.worker_id = worker_id
    job.failure = None
    job.attempt_history = [
        *job.attempt_history,
        {
            "attempt": job.attempts,
            "started_at": now.isoformat(),
            "worker_id": worker_id,
            "status": "running",
        },
    ]
    db.commit()
    return job


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


class JobFuture:
    """Compatibility wait handle: state is polled from SQL, never a process-local task result."""

    def __init__(self, engine, job_id):
        self.engine, self.job_id = engine, job_id

    def done(self):
        with Session(self.engine) as db:
            row = db.get(BackgroundJob, self.job_id)
            return row is None or row.status not in ACTIVE

    def result(self, timeout=None):
        deadline = time.monotonic() + (timeout or 900)
        while time.monotonic() < deadline:
            if self.done():
                return None
            time.sleep(0.05)
        raise TimeoutError()
