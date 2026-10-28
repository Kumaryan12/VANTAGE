"""Opaque-ID entrypoint. No arbitrary callable, URL, SQL or shell is accepted."""

import os
import socket
from datetime import UTC, datetime, timedelta
from threading import Event, Thread

from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import BackgroundJob

from .celery_app import app
from .lease import Cancellation, Execution, current
from .service import claim, cleanup_attempt, cleanup_staged, root_status


def heartbeat(engine, ident, token, stopped, timeout):
    import time

    deadline = time.monotonic() + timeout
    while not stopped.wait(max(1, settings().job_lease_seconds / 4)):
        if time.monotonic() >= deadline:
            return
        try:
            with Session(engine) as db:
                server_now = (
                    func.clock_timestamp()
                    if engine.dialect.name == "postgresql"
                    else datetime.now(UTC)
                )
                changed = db.execute(
                    update(BackgroundJob)
                    .where(
                        BackgroundJob.id == ident,
                        BackgroundJob.lease_token == token,
                        BackgroundJob.status == "running",
                        BackgroundJob.lease_expires > server_now,
                    )
                    .values(
                        lease_expires=server_now + timedelta(seconds=settings().job_lease_seconds)
                    )
                ).rowcount
                db.commit()
                if not changed:
                    return
        except Exception:
            # Publication remains fenced if heartbeats cannot reach SQL.
            continue


def hard_deadline(stopped, timeout):
    # Defense in depth against a malformed internal envelope omitting Celery's per-kind limit.
    # The Linux prefork supervisor also enforces an independent hard process timeout.
    if not stopped.wait(timeout + 5):
        os._exit(70)


def perform(kind, engine, target, execution):
    if kind in {"research", "optimization"}:
        from app.ml.artifacts import runtime_versions

        actual = runtime_versions()
        if kind == "optimization":
            from app.optimization.service import runtime

            actual = runtime()
        with Session(engine) as db:
            row = db.get(BackgroundJob, execution.job_id)
            expected = row.input_reference["runtime"]
            for key in (
                "python",
                "numpy",
                "pandas",
                "scipy",
                "arch",
                "lightgbm",
                "cvxpy",
                "clarabel",
            ):
                if key in expected and expected[key] != actual.get(key):
                    raise AppError(
                        "WORKER_RUNTIME_MISMATCH",
                        "Worker numerical runtime differs from the captured execution contract.",
                        409,
                    )
            row.attempt_history = [
                *row.attempt_history[:-1],
                {**row.attempt_history[-1], "runtime": actual},
            ]
            db.commit()
    if kind == "research":
        from app.ml.service import queue

        queue._execute(engine, target)
    elif kind == "optimization":
        from app.optimization.service import queue

        queue.execute(engine, target)
    elif kind == "document":
        from app.documents.service import queue

        queue.process(engine, target)
    elif kind == "agent":
        from app.agent.service import queue

        queue.execute(engine, target, Cancellation(execution))
    elif kind == "evaluation":
        from app.agent.evaluation import evaluate

        evaluate(engine, target)
    elif kind in {"risk", "report"}:
        from .workflows import execute

        execute(engine, execution)
    else:
        raise AppError("JOBS_KIND", "Unsupported durable job type.")


def fail(engine, ident, token, error):
    with Session(engine) as db:
        job = db.scalar(select(BackgroundJob).where(BackgroundJob.id == ident).with_for_update())
        if (
            job is None
            or job.lease_token != token
            or job.status not in {"running", "cancel_requested"}
        ):
            return
        cancelled = job.status == "cancel_requested" or (
            isinstance(error, AppError) and error.code == "JOB_CANCELLED"
        )
        job.status = "cancelled" if cancelled else "failed"
        job.failure = {
            "code": "JOB_CANCELLED"
            if cancelled
            else error.code
            if isinstance(error, AppError)
            else "JOB_EXECUTION_FAILED",
            "message": "Cancelled without successful publication."
            if cancelled
            else "Bounded execution failed; no successful result is claimed. Inspect authorized resource diagnostics or retry eligible work.",
        }
        job.finished_at = datetime.now(UTC)
        job.lease_token = None
        job.attempt_history = [
            *job.attempt_history[:-1],
            {
                **job.attempt_history[-1],
                "status": job.status,
                "finished_at": job.finished_at.isoformat(),
                "failure_category": job.failure["code"],
            },
        ]
        root_status(db, job, job.status, job.failure)
        try:
            with db.begin_nested():
                cleanup_staged(db, job)
        except AppError:
            job.failure = {
                **job.failure,
                "cleanup": "Staged private object cleanup requires operator retry; no staged output is downloadable.",
            }
        db.commit()


@app.task(name="vantage.execute", acks_late=True, reject_on_worker_lost=True)
def execute_job(ident):
    from app.database.session import engine

    if not isinstance(ident, str) or len(ident) != 36:
        return {"status": "invalid_envelope"}
    worker = f"{socket.gethostname()}:{os.getpid()}"
    with Session(engine, expire_on_commit=False) as db:
        try:
            job = claim(db, ident, worker)
        except AppError as error:
            db.rollback()
            # Invalid references cannot execute or be silently repaired.
            row = db.get(BackgroundJob, ident)
            if row and row.status in {"queued", "retrying"}:
                row.status = "failed"
                row.failure = {
                    "code": error.code,
                    "message": "Saved input validation/admission failed before execution.",
                }
                row.finished_at = datetime.now(UTC)
                root_status(db, row, "failed", row.failure)
                db.commit()
            return {"status": "rejected"}
        if job is None:
            return {"status": "duplicate_or_not_ready"}
    execution = Execution(job.id, job.lease_token, engine, job.kind)
    stopped = Event()
    pulse = Thread(
        target=heartbeat,
        args=(engine, job.id, job.lease_token, stopped, job.timeout_seconds),
        daemon=True,
    )
    pulse.start()
    watchdog = Thread(target=hard_deadline, args=(stopped, job.timeout_seconds), daemon=True)
    watchdog.start()
    context_token = current.set(execution)
    error = None
    try:
        with Session(engine) as db:
            cleanup_attempt(db, db.get(BackgroundJob, job.id))
            db.commit()
        perform(job.kind, engine, job.target_id, execution)
    except Exception as caught:
        error = caught
    finally:
        current.reset(context_token)
        stopped.set()
        pulse.join(timeout=2)
    if error:
        fail(engine, job.id, job.lease_token, error)
    else:
        # A swallowed service error or missing finalization is never reported as success.
        with Session(engine) as db:
            completed = db.get(BackgroundJob, job.id).status == "completed"
        if not completed:
            fail(
                engine,
                job.id,
                job.lease_token,
                AppError("JOB_NO_PUBLICATION", "No atomic successful publication was observed."),
            )
    return {"job_id": ident, "status": "handled"}
