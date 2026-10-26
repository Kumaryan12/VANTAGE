"""Compact immutable source artifacts; never persist simulation draws."""

import hashlib
import json
import platform
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.database.models import PortfolioSnapshot, RiskInputArtifact, RiskRun
from app.portfolios.schemas import Portfolio, Provenance
from app.risk.contracts import RunMetadata

MODEL_VERSION = "2.0.0"


def digest(payload) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()


def frame_payload(prices: pd.DataFrame, provenance: Provenance) -> dict:
    return {
        "dates": [dt.date().isoformat() for dt in prices.index],
        "instruments": list(prices.columns),
        "prices": prices.to_numpy().tolist(),
        "provenance": provenance.model_dump(mode="json"),
    }


def payload_frame(payload: dict) -> tuple[pd.DataFrame, Provenance]:
    frame = pd.DataFrame(
        payload["prices"], columns=payload["instruments"], index=pd.to_datetime(payload["dates"])
    )
    return frame, Provenance.model_validate(payload["provenance"])


def persist_inputs(db: Session, portfolio: Portfolio, payload: dict, owner: str):
    snapshot_payload = portfolio.model_dump(mode="json")
    # Exact stored snapshot, including retrieval metadata, is part of replay identity.
    snapshot_hash = digest(snapshot_payload)
    snapshot = db.scalar(
        select(PortfolioSnapshot).where(
            PortfolioSnapshot.owner == owner, PortfolioSnapshot.content_hash == snapshot_hash
        )
    )
    if snapshot is None:
        snapshot = PortfolioSnapshot(
            id=str(uuid4()),
            owner=owner,
            content_hash=snapshot_hash,
            payload=snapshot_payload,
            created_at=datetime.now(UTC),
        )
        db.add(snapshot)
    artifact_hash = digest(payload)
    artifact = db.scalar(
        select(RiskInputArtifact).where(
            RiskInputArtifact.owner == owner, RiskInputArtifact.content_hash == artifact_hash
        )
    )
    if artifact is None:
        artifact = RiskInputArtifact(
            id=str(uuid4()),
            owner=owner,
            content_hash=artifact_hash,
            payload=payload,
            created_at=datetime.now(UTC),
        )
        db.add(artifact)
    db.flush()
    return snapshot, artifact


def metadata(
    portfolio,
    parameters,
    snapshot,
    artifact,
    *,
    methodology,
    sample_size,
    provenance=None,
    start=None,
    end=None,
    covariance_method=None,
    warnings=None,
):
    combined_hash = digest(
        {
            "snapshot": snapshot.content_hash,
            "artifact": artifact.content_hash,
            "parameters": parameters.model_dump(mode="json"),
            "model_version": MODEL_VERSION,
            "methodology": methodology,
        }
    )
    return RunMetadata(
        methodology=methodology,
        model_version=MODEL_VERSION,
        created_at=datetime.now(UTC),
        valuation_as_of=portfolio.as_of,
        snapshot_retrieved_at=portfolio.retrieved_at,
        valuation_timestamp_note=portfolio.price_timestamp_note,
        snapshot_id=snapshot.id,
        input_artifact_id=artifact.id,
        input_hash=combined_hash,
        artifact_hash=artifact.content_hash,
        historical_data_hash=provenance.content_hash if provenance else None,
        data_source_ids=[portfolio.source] + ([provenance.source] if provenance else []),
        horizon="1 observed trading day"
        if methodology == "risk_comparison"
        else "Scenario window / instantaneous direct shock; see parameters",
        confidence=parameters.confidence,
        requested_window=parameters.window,
        sample_size=sample_size,
        estimation_start=start,
        estimation_end=end,
        covariance_method=covariance_method,
        shrinkage=parameters.shrinkage,
        random_seed=getattr(parameters, "seed", None),
        simulation_count=getattr(parameters, "simulations", 0),
        runtime={
            "python": platform.python_version(),
            "numpy": np.__version__,
            "pandas": pd.__version__,
            "platform": platform.platform(),
            "dtype": "float64",
            "sampling": "PCG64 / numpy.linalg.eigh",
        },
        validation={
            "currency": "INR",
            "full_cross_asset_date_alignment": True,
            "exchange_calendar_completeness": "source assertion; not independently certified",
            "adjustment": provenance.adjustment
            if provenance
            else "not applicable to direct shocks",
            "tail_sample_mass": sample_size * (1 - parameters.confidence),
        },
        warnings=warnings or [],
    )


def persist_run(db: Session, result, owner: str):
    db.add(
        RiskRun(
            id=result.run_id,
            owner=owner,
            input_hash=result.metadata.input_hash,
            methodology=result.metadata.methodology,
            result=result.model_dump(mode="json"),
            created_at=result.metadata.created_at,
            schema_version=2,
            kind=result.kind,
            snapshot_id=result.metadata.snapshot_id,
            input_artifact_id=result.metadata.input_artifact_id,
            parameters=result.parameters.model_dump(mode="json"),
        )
    )
    db.commit()
    return result


def owned_run(db: Session, run_id: str, owner: str) -> RiskRun:
    run = db.get(RiskRun, run_id)
    if run is None or run.owner != owner:
        raise AppError("RUN_NOT_FOUND", "Risk run not found in the authorized session.", 404)
    return run


def replay_inputs(db: Session, run: RiskRun, owner: str):
    snapshot = db.get(PortfolioSnapshot, run.snapshot_id)
    artifact = db.get(RiskInputArtifact, run.input_artifact_id)
    if snapshot is None or artifact is None or snapshot.owner != owner or artifact.owner != owner:
        raise AppError("REPLAY_UNAVAILABLE", "This run has no authorized immutable inputs.", 422)
    if (
        digest(snapshot.payload) != snapshot.content_hash
        or digest(artifact.payload) != artifact.content_hash
    ):
        raise AppError(
            "INPUT_INTEGRITY", "Persisted replay inputs failed their content-hash check.", 409
        )
    return Portfolio.model_validate(snapshot.payload), artifact.payload
