"""SQL outbox dispatch and expired-lease recovery. Multiple dispatchers are safe."""

import argparse
import json
import time
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.database.models import BackgroundJob

from .service import gate, root_status, utc


def reconcile(db):
    now = datetime.now(UTC)
    gate(db)
    rows = db.scalars(
        select(BackgroundJob)
        .where(
            BackgroundJob.status.in_(["running", "cancel_requested"]),
            BackgroundJob.lease_expires < now,
        )
        .with_for_update(skip_locked=True)
        .limit(100)
    ).all()
    for job in rows:
        cancelled = job.status == "cancel_requested"
        job.status = "cancelled" if cancelled else "interrupted"
        job.failure = {
            "code": "JOB_CANCELLED" if cancelled else "WORKER_LEASE_EXPIRED",
            "message": "Worker stopped or its lease expired; no successful result is claimed.",
        }
        job.lease_token = None
        job.finished_at = now
        job.attempt_history = [
            *job.attempt_history[:-1],
            {
                **job.attempt_history[-1],
                "status": job.status,
                "finished_at": now.isoformat(),
                "failure_category": job.failure["code"],
            },
        ]
        root_status(db, job, job.status, job.failure)
        if not cancelled and job.attempts < job.max_attempts:
            job.status = "retrying"
            job.available_at = now + timedelta(seconds=2**job.attempts)
            job.dispatched_at = None
            root_status(db, job, "queued")
    db.commit()
    return len(rows)


def dispatch(db, send=None):
    from .tasks import execute_job

    now = datetime.now(UTC)
    if gate(db).paused:
        db.rollback()
        return {"sent": 0, "broker_errors": 0, "paused": True}
    jobs = db.scalars(
        select(BackgroundJob)
        .where(
            BackgroundJob.status.in_(["queued", "retrying"]),
            BackgroundJob.available_at <= now,
            or_(
                BackgroundJob.dispatched_at.is_(None),
                BackgroundJob.dispatched_at < now - timedelta(seconds=20),
            ),
        )
        .order_by(BackgroundJob.created_at)
        .with_for_update(skip_locked=True)
        .limit(20)
    ).all()
    result = {"sent": 0, "broker_errors": 0, "paused": False}
    for job in jobs:
        if utc(job.created_at) < now - timedelta(hours=24):
            job.status = "failed"
            job.failure = {
                "code": "QUEUE_EXPIRED",
                "message": "Work was not started within the bounded 24-hour queue lifetime.",
            }
            root_status(db, job, "failed", job.failure)
            job.finished_at = now
            continue
        try:
            if send:
                send(job)
            else:
                execute_job.apply_async(
                    retry=False,
                    args=[job.id],
                    queue=job.kind,
                    task_id=f"{job.id}:{job.attempts + 1}",
                    soft_time_limit=job.timeout_seconds,
                    time_limit=job.timeout_seconds + 10,
                    argsrepr="(<opaque job id>,)",
                    kwargsrepr="{}",
                )
            job.dispatched_at = now
            result["sent"] += 1
        except Exception:
            result["broker_errors"] += 1
            break
    db.commit()
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--once", action="store_true")
    args = parser.parse_args()
    from app.database.session import engine

    while True:
        try:
            with Session(engine) as db:
                recovered = reconcile(db)
                result = dispatch(db)
            if recovered or result["sent"] or result["broker_errors"]:
                print(
                    json.dumps({"event": "dispatcher", "recovered": recovered, **result}),
                    flush=True,
                )
        except Exception:
            print(
                json.dumps(
                    {
                        "event": "dispatcher_error",
                        "message": "State/broker reconciliation failed; no success claimed.",
                    }
                ),
                flush=True,
            )
        if args.once:
            return
        time.sleep(1)


if __name__ == "__main__":
    main()
