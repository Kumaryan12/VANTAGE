from datetime import UTC, datetime, timedelta

import pytest
from document_fixtures import LIQUIDITY, pdf_bytes
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session
from test_identity import account

from app.core.config import settings
from app.core.errors import AppError
from app.database.models import BackgroundJob, OptimizationRun, OwnershipScope
from app.jobs import service
from app.jobs.dispatcher import dispatch, reconcile
from app.jobs.lease import Execution, current
from app.jobs.tasks import execute_job


@pytest.fixture
def durable_client(agent_client, monkeypatch, tmp_path):
    client, engine = agent_client
    monkeypatch.setattr(settings(), "job_backend", "celery")
    monkeypatch.setattr(settings(), "private_storage_dir", str(tmp_path / "private"))
    from app.database import session

    monkeypatch.setattr(session, "engine", engine)
    return client, engine


def job_for(engine, target):
    with Session(engine) as db:
        return db.scalar(select(BackgroundJob.id).where(BackgroundJob.target_id == target))


def execute(engine, target):
    ident = job_for(engine, target)
    execute_job.run(ident)
    with Session(engine) as db:
        row = db.get(BackgroundJob, ident)
        assert row.status == "completed", service.view(row)
    return ident


def test_all_durable_financial_workflows_atomic_publication_and_private_report(durable_client):
    client, engine = durable_client
    account(client)
    optimization = client.post("/api/v1/optimization/run", json={})
    assert optimization.status_code == 202, optimization.text
    target = optimization.json()["id"]
    ident = execute(engine, target)
    saved = client.get(f"/api/v1/optimization/runs/{target}").json()
    assert saved["status"] == "completed" and saved["result"]["points"][0]["solution"]["feasible"]
    previous_hash = service.digest(saved["result"])
    execute_job.run(ident)
    assert (
        service.digest(client.get(f"/api/v1/optimization/runs/{target}").json()["result"])
        == previous_hash
    )
    assert client.post(f"/api/v1/jobs/{ident}/retry").status_code == 409
    research = client.post("/api/v1/ml/backtest", json={"max_trees": 40, "search_candidates": 2})
    assert research.status_code == 202, research.text
    execute(engine, research.json()["id"])
    assert (
        client.get(f"/api/v1/ml/experiments/{research.json()['id']}").json()["status"]
        == "completed"
    )
    document = client.post(
        "/api/v1/research/documents",
        files={"file": ("SYNTHETIC.pdf", pdf_bytes([LIQUIDITY]), "application/pdf")},
        data={"source": "Synthetic permitted fixture", "permitted": "true"},
    )
    assert document.status_code == 202, document.text
    execute(engine, document.json()["id"])
    investigation = client.post(
        "/api/v1/agent/investigate",
        json={
            "question": "Summarize liquidity risks in the uploaded document",
            "document_ids": [document.json()["id"]],
        },
    )
    assert investigation.status_code == 202, investigation.text
    execute(engine, investigation.json()["id"])
    answer = client.get(f"/api/v1/agent/investigations/{investigation.json()['id']}").json()
    assert answer["answer"]["citations"]
    risk = client.post(
        "/api/v1/jobs/risk",
        json={"parameters": {"simulations": 2000}, "idempotency_key": "same-sealed-input"},
    )
    assert risk.status_code == 202, risk.text
    execute_job.run(risk.json()["id"])
    completed = client.get(f"/api/v1/jobs/{risk.json()['id']}").json()
    assert completed["status"] == "completed", completed
    source_id = completed["result_reference"]["target_id"]
    assert client.get(f"/api/v1/risk/runs/{source_id}").status_code == 200
    report = client.post(
        "/api/v1/jobs/report", json={"source_type": "optimization", "source_id": target}
    )
    assert report.status_code == 202, report.text
    execute_job.run(report.json()["id"])
    result = client.get(f"/api/v1/jobs/{report.json()['id']}").json()
    assert result["status"] == "completed", result
    artifact_id = result["result_reference"]["artifact_id"]
    assert client.get(f"/api/v1/storage/artifacts/{artifact_id}").status_code == 200
    disclosure_export = client.post(
        "/api/v1/jobs/report",
        json={"source_type": "investigation", "source_id": investigation.json()["id"]},
    ).json()
    assert client.delete(f"/api/v1/research/documents/{document.json()['id']}").status_code == 409
    execute_job.run(disclosure_export["id"])
    exported = client.get(f"/api/v1/jobs/{disclosure_export['id']}").json()["result_reference"][
        "artifact_id"
    ]
    assert client.get(f"/api/v1/storage/artifacts/{exported}").status_code == 200
    assert client.delete(f"/api/v1/research/documents/{document.json()['id']}").status_code == 200
    assert client.get(f"/api/v1/storage/artifacts/{exported}").status_code == 404
    with TestClient(client.app) as other:
        account(other, "other@example.com")
        for suffix in ("", "/cancel", "/retry"):
            response = (
                other.get(f"/api/v1/jobs/{ident}")
                if not suffix
                else other.post(f"/api/v1/jobs/{ident}{suffix}")
            )
            assert response.status_code == 404
        assert other.get(f"/api/v1/storage/artifacts/{artifact_id}").status_code == 404


def test_lease_recovery_fences_old_worker_and_cancellation_blocks_late_allocation(durable_client):
    client, engine = durable_client
    account(client)
    target = client.post("/api/v1/optimization/run", json={}).json()["id"]
    ident = job_for(engine, target)
    with Session(engine, expire_on_commit=False) as db:
        first = service.claim(db, ident, "crashed-worker")
        old_token = first.lease_token
        assert service.claim(db, ident, "duplicate-worker") is None
        row = db.get(BackgroundJob, ident)
        row.lease_expires = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        assert reconcile(db) == 1
        assert db.get(BackgroundJob, ident).status == "retrying"
        db.get(BackgroundJob, ident).available_at = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        second = service.claim(db, ident, "replacement-worker")
        new_token = second.lease_token
        assert new_token != old_token and second.attempts == 2
    token = current.set(Execution(ident, old_token, engine, "optimization"))
    try:
        with Session(engine) as db:
            row = db.get(OptimizationRun, target)
            row.result = {"forbidden": "late stale allocation"}
            row.status = "completed"
            with pytest.raises(AppError, match="lease"):
                db.commit()
            db.rollback()
    finally:
        current.reset(token)
    assert client.post(f"/api/v1/jobs/{ident}/cancel").json()["status"] == "cancel_requested"
    token = current.set(Execution(ident, new_token, engine, "optimization"))
    try:
        with Session(engine) as db:
            row = db.get(OptimizationRun, target)
            row.status = "completed"
            row.result = {"forbidden": "late cancelled allocation"}
            with pytest.raises(AppError, match="Cancellation"):
                db.commit()
            db.rollback()
    finally:
        current.reset(token)
    with Session(engine) as db:
        assert db.get(OptimizationRun, target).result is None
        db.get(BackgroundJob, ident).lease_expires = datetime.now(UTC) - timedelta(seconds=1)
        db.commit()
        assert reconcile(db) == 1
        assert db.get(BackgroundJob, ident).status == "cancelled"
        assert db.get(OptimizationRun, target).status == "cancelled"


def test_account_quota_cross_workspace_outbox_retry_and_input_integrity(durable_client):
    client, engine = durable_client
    me = account(client)
    queued = client.post("/api/v1/optimization/run", json={}).json()["id"]
    ident = job_for(engine, queued)
    with Session(engine) as db:
        scope = OwnershipScope(
            id="f" * 64,
            user_id=me["user"]["id"],
            name="Second owned scope",
            kind="personal",
            created_at=datetime.now(UTC),
            lifecycle="active",
        )
        db.add(scope)
        db.commit()
        with pytest.raises(AppError, match="type"):
            service.admit(db, scope.id, "optimization", "synthetic-target", {"synthetic": True})
        db.rollback()

        def outage(job):
            raise ConnectionError("SYNTHETIC broker unavailable")

        assert dispatch(db, outage)["broker_errors"] == 1
        assert db.get(BackgroundJob, ident).status == "queued"
        sent = []
        assert dispatch(db, lambda job: sent.append(job.id))["sent"] == 1
        assert sent == [ident]
        db.get(OptimizationRun, queued).parameters = {"tampered": True}
        db.commit()
    execute_job.run(ident)
    with Session(engine) as db:
        assert db.get(BackgroundJob, ident).status == "failed"
        assert db.get(OptimizationRun, queued).result is None
    assert client.post(f"/api/v1/jobs/{ident}/retry").status_code == 200
    assert client.post(f"/api/v1/jobs/{ident}/cancel").json()["status"] == "cancelled"
    assert client.post(f"/api/v1/jobs/{ident}/retry").status_code == 409


def test_provider_reservations_are_atomic_and_shared_across_owned_workspaces(
    durable_client, monkeypatch
):
    from app.jobs.quotas import reserve

    client, engine = durable_client
    me = account(client)
    monkeypatch.setattr(settings(), "provider_daily_reserved_tokens", 1_000_000)
    with Session(engine) as db:
        db.add(
            OwnershipScope(
                id="e" * 64,
                user_id=me["user"]["id"],
                name="Same principal",
                kind="personal",
                created_at=datetime.now(UTC),
                lifecycle="active",
            )
        )
        db.commit()
    reserve(engine, me["workspace_id"], "llm", token_reservation=1_000_000)
    with pytest.raises(AppError, match="reservation"):
        reserve(engine, "e" * 64, "llm", token_reservation=1_000_000)
    with TestClient(client.app) as other:
        second = account(other, "other@example.com")
        reserve(engine, second["workspace_id"], "llm", token_reservation=1_000_000)


def test_account_sql_sources_quota_and_old_unindexed_crash_file_reconciliation(
    durable_client, monkeypatch, tmp_path
):
    import os

    from app.storage.backends import LocalStorage
    from app.storage.reconcile import reconcile_files
    from app.storage.service import reserve_sources, store

    client, engine = durable_client
    me = account(client)
    with Session(engine) as db:
        with pytest.raises(AppError, match="source/history"):
            reserve_sources(db, me["workspace_id"], settings().source_quota_mb * 1024 * 1024 + 1)
        db.rollback()
        manifest = store(db, me["workspace_id"], "export", b"SYNTHETIC live reference")
        db.commit()
        orphan_key = me["workspace_id"] + "/" + "a" * 36
        LocalStorage().put(orphan_key, "export", b"SYNTHETIC unindexed crash file")
        orphan = LocalStorage().path(orphan_key, "export")
        for path in (orphan, LocalStorage().path(manifest["storage_key"], "export")):
            old = (datetime.now(UTC) - timedelta(days=8)).timestamp()
            os.utime(path, (old, old))
        assert reconcile_files(db)["unindexed_files_older_than_7_days"] == 1
        assert orphan.exists()
        assert reconcile_files(db, apply=True)["unindexed_files_older_than_7_days"] == 1
        assert not orphan.exists()
        assert LocalStorage().path(manifest["storage_key"], "export").exists()


def test_expired_worker_heartbeat_cannot_revive_its_lease(durable_client):
    from app.jobs.tasks import heartbeat

    client, engine = durable_client
    account(client)
    target = client.post("/api/v1/optimization/run", json={}).json()["id"]
    ident = job_for(engine, target)
    with Session(engine, expire_on_commit=False) as db:
        job = service.claim(db, ident, "expired-worker")
        old = datetime.now(UTC) - timedelta(seconds=1)
        job.lease_expires = old
        token = job.lease_token
        db.commit()

    class Pulse:
        calls = 0

        def wait(self, seconds):
            self.calls += 1
            return self.calls > 1

    heartbeat(engine, ident, token, Pulse(), 100)
    with Session(engine) as db:
        assert service.utc(db.get(BackgroundJob, ident).lease_expires) == old
        reconcile(db)
        service.cancel(db, db.get(BackgroundJob, ident))
