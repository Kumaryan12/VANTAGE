"""Provider-free risk simulation and private evidence exports from sealed inputs."""

import json
from uuid import uuid4

from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.database.models import BackgroundJob, PortfolioSnapshot, RiskInputArtifact
from app.portfolios.schemas import Portfolio
from app.risk.artifacts import MODEL_VERSION, digest, frame_payload, persist_inputs

from . import service


def submit_risk(db, portfolio, owner, parameters, *, idempotency_key=None):
    from app.risk.service import resolve_prices

    prices, provenance = resolve_prices(db, portfolio, owner, parameters.dataset_id)
    # Use the existing common validator; the expensive correlated draws are deferred.
    from app.risk.engine import calculate

    calculate(
        prices, [h.weight for h in portfolio.holdings], parameters.confidence, parameters.window
    )
    snapshot, artifact = persist_inputs(
        db, portfolio, {"kind": "analysis", "estimation": frame_payload(prices, provenance)}, owner
    )
    inputs = {
        "snapshot_id": snapshot.id,
        "artifact_id": artifact.id,
        "snapshot_hash": snapshot.content_hash,
        "artifact_hash": artifact.content_hash,
        "parameters": parameters.model_dump(mode="json"),
        "model_version": MODEL_VERSION,
    }
    job = service.admit(db, owner, "risk", str(uuid4()), inputs, idempotency_key=idempotency_key)
    db.commit()
    return job


def source_payload(db, owner, kind, ident):
    if kind == "risk":
        from app.risk.artifacts import owned_run

        return owned_run(db, ident, owner).result
    if kind == "optimization":
        from app.optimization.service import owned

        row = owned(db, ident, owner)
        if (
            row.status not in {"completed", "partial"}
            or row.result is None
            or digest(row.result) != row.result_hash
        ):
            raise AppError(
                "REPORT_SOURCE", "Saved optimization is not a verified completed source.", 409
            )
        return row.result
    if kind == "investigation":
        from app.agent.service import owned

        row = owned(db, ident, owner)
        if row.status not in {"completed", "limited"} or row.answer is None:
            raise AppError("REPORT_SOURCE", "Investigation has no published verified answer.", 409)
        return row.answer
    raise AppError("REPORT_SOURCE", "Unsupported evidence source.")


def submit_report(db, owner, kind, ident):
    payload = source_payload(db, owner, kind, ident)
    job = service.admit(
        db,
        owner,
        "report",
        str(uuid4()),
        {
            "source_type": kind,
            "source_id": ident,
            "source_hash": digest(payload),
            "export_version": "research-evidence-1",
        },
    )
    db.commit()
    return job


def execute(engine, execution):
    with Session(engine) as db:
        job = db.get(BackgroundJob, execution.job_id)
        inputs = job.input_reference
        if digest(inputs) != job.input_hash:
            raise AppError("JOB_INPUT_INTEGRITY", "Saved job inputs failed verification.", 409)
        if job.kind == "risk":
            from app.risk.advanced import run_analysis
            from app.risk.contracts import AnalysisRequest

            snapshot = db.get(PortfolioSnapshot, inputs["snapshot_id"])
            artifact = db.get(RiskInputArtifact, inputs["artifact_id"])
            if (
                inputs["model_version"] != MODEL_VERSION
                or snapshot is None
                or artifact is None
                or snapshot.owner != job.owner
                or artifact.owner != job.owner
                or digest(snapshot.payload) != inputs["snapshot_hash"]
                or digest(artifact.payload) != inputs["artifact_hash"]
            ):
                raise AppError(
                    "JOB_INPUT_INTEGRITY", "Captured risk inputs or version changed.", 409
                )
            run_analysis(
                db,
                Portfolio.model_validate(snapshot.payload),
                job.owner,
                AnalysisRequest.model_validate(inputs["parameters"]),
                replay_payload=artifact.payload,
            )
        else:
            from app.storage.service import store

            payload = source_payload(db, job.owner, inputs["source_type"], inputs["source_id"])
            if digest(payload) != inputs["source_hash"]:
                raise AppError("REPORT_INTEGRITY", "Export source changed or is unavailable.", 409)
            content = json.dumps(
                {
                    "version": inputs["export_version"],
                    "source_type": inputs["source_type"],
                    "source_id": inputs["source_id"],
                    "source_hash": inputs["source_hash"],
                    "notice": "Read-only research evidence; synthetic data remains labeled. No order, investment recommendation or future-risk guarantee.",
                    "evidence": payload,
                },
                sort_keys=True,
                allow_nan=False,
            ).encode()
            manifest = store(db, job.owner, "report", content, parent_id=job.id)
            db.info["job_publication"] = {
                "kind": "report",
                "artifact_id": manifest["object_id"],
                "sha256": manifest["sha256"],
            }
            db.commit()
