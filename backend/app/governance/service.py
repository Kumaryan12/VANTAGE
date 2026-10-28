from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import select

from app.agent.security import redact
from app.core.errors import AppError
from app.database.models import (
    GovernanceModel,
    GovernanceReviewEvent,
    OptimizationRun,
    PortfolioSnapshot,
    ResearchExperiment,
    RiskInputArtifact,
)
from app.ml.artifacts import read_artifact
from app.ml.service import owned_experiment, owned_model
from app.optimization.service import owned as owned_optimization
from app.optimization.service import verify_inputs
from app.risk.artifacts import digest

from .contracts import REVIEW_AREAS, RegisterModel, ReviewModel

TRANSITIONS = {
    "candidate": ["under_review", "rejected", "retired"],
    "under_review": ["validated", "rejected", "retired"],
    "validated": ["approved_research", "under_review", "rejected", "retired"],
    "approved_research": ["under_review", "retired"],
    "rejected": ["under_review", "retired"],
    "retired": [],
}


def source_evidence(db, owner, source_type, source_id):
    if source_type == "optimization":
        run = owned_optimization(db, source_id, owner)
        if (
            run.kind != "single"
            or run.result is None
            or not run.result["points"][0]["solution"]["feasible"]
        ):
            raise AppError(
                "GOVERNANCE_SOURCE",
                "Register a completed feasible single-allocation model; an infeasible study is not a validated allocation.",
            )
        verify_inputs(db, run, owner)
        point = run.result["points"][0]
        children = db.scalars(
            select(OptimizationRun).where(
                OptimizationRun.owner == owner,
                OptimizationRun.reproduction_of == run.id,
                OptimizationRun.status == "completed",
            )
        ).all()
        reproduced = bool(run.result.get("reproduction_match")) and bool(run.reproduction_of)
        if reproduced:
            original = owned_optimization(db, run.reproduction_of, owner)
            reproduced = original.input_hash == run.input_hash
        reproduced = reproduced or any(
            owned_optimization(db, c.id, owner).result.get("reproduction_match") is True
            and c.input_hash == run.input_hash
            for c in children
        )
        passed = (
            point["solution"]["status"] == "optimal"
            and point["solution"]["validation"].get("passed") is True
        )
        return {
            "model_type": f"cvxpy_{point['parameters']['objective']}",
            "model_version": run.runtime["optimization_version"],
            "synthetic": run.dataset["synthetic"],
            "evaluation_period": {
                "start": point["dataset"]["estimation_start"],
                "end": point["dataset"]["estimation_end"],
                "interpretation": "In-sample covariance/constraint methodology; no out-of-sample investment validation.",
            },
            "data_dependencies": {
                "snapshot_id": run.snapshot_id,
                "artifact_id": run.artifact_id,
                "input_hash": run.input_hash,
                "covariance_hash": point["dataset"]["covariance_hash"],
            },
            "automated_checks": {
                "solver_and_constraints": passed,
                "saved_input_reproduction": reproduced,
            },
            "validation_ready": passed and reproduced,
            "limitations": [
                *point["solution"]["diagnostics"],
                *point["comparison"]["warnings"],
                "A mathematically validated allocation is not proof of real-market model performance.",
                "Research-only session review is not enterprise maker-checker, regulatory certification or execution approval.",
            ],
        }
    model = owned_model(db, source_id, owner)
    exp = owned_experiment(db, model.experiment_id, owner)
    children = db.scalars(
        select(ResearchExperiment).where(
            ResearchExperiment.owner == owner,
            ResearchExperiment.reproduction_of == exp.id,
            ResearchExperiment.status == "completed",
        )
    ).all()
    reproduced = bool((exp.summary or {}).get("reproduction_match")) and bool(exp.reproduction_of)
    if reproduced:
        original = owned_experiment(db, exp.reproduction_of, owner)
        reproduced = original.input_hash == exp.input_hash
    reproduced = reproduced or any(
        c.summary and c.summary.get("reproduction_match") is True and c.input_hash == exp.input_hash
        for c in children
    )
    snapshot = db.get(PortfolioSnapshot, exp.snapshot_id)
    artifact = db.get(RiskInputArtifact, exp.input_artifact_id)
    inputs = bool(
        snapshot
        and artifact
        and snapshot.owner == owner
        and artifact.owner == owner
        and digest(snapshot.payload) == snapshot.content_hash
        and digest(artifact.payload) == artifact.content_hash
        and digest(
            {
                "snapshot": snapshot.content_hash,
                "artifact": artifact.content_hash,
                "parameters": exp.parameters,
                "version": exp.runtime["model_version"],
            }
        )
        == exp.input_hash
    )
    artifacts = True
    try:
        for file in model.payload["artifact_files"]:
            read_artifact(file, model.owner)
    except AppError:
        artifacts = False
    complete = (
        model.payload["status"] == "completed"
        and (model.payload.get("metrics") or {}).get("observations", 0) >= 100
    )
    return {
        "model_type": model.kind,
        "model_version": exp.runtime["model_version"],
        "synthetic": exp.data_info["synthetic"],
        "phase3_role": model.role,
        "evaluation_period": exp.protocol,
        "data_dependencies": {
            "experiment_id": exp.id,
            "dataset_hash": exp.dataset_hash,
            "snapshot_id": exp.snapshot_id,
            "artifact_id": exp.input_artifact_id,
        },
        "automated_checks": {
            "complete_matched_evaluation": complete,
            "artifact_integrity": artifacts,
            "input_integrity": inputs,
            "saved_input_reproduction": reproduced,
        },
        "validation_ready": complete and artifacts and inputs and reproduced,
        "limitations": [
            *model.payload["limitations"],
            *(exp.summary or {}).get("warnings", []),
            "Low QLIKE alone is not approval evidence; assess coverage, uncertainty, leakage, regimes, complexity and operations.",
            "Synthetic results cannot justify real-market model approval.",
        ],
    }


def owned(db, ident, owner):
    row = db.get(GovernanceModel, ident)
    if row is None or row.owner != owner:
        raise AppError("GOVERNANCE_NOT_FOUND", "Review model not found in this session.", 404)
    return row


def detail(db, row):
    evidence = source_evidence(db, row.owner, row.source_type, row.source_id)
    return ReviewModel(
        id=row.id,
        source_type=row.source_type,
        source_id=row.source_id,
        model_type=row.model_type,
        model_version=row.model_version,
        intended_use=row.intended_use,
        status=row.status,
        created_at=row.created_at,
        payload=row.payload,
        current_validation=evidence,
        allowed_transitions=TRANSITIONS[row.status],
    )


def register(db, owner, body: RegisterModel, *, commit=True):
    existing = db.scalar(
        select(GovernanceModel).where(
            GovernanceModel.owner == owner,
            GovernanceModel.source_type == body.source_type,
            GovernanceModel.source_id == body.source_id,
        )
    )
    if existing:
        return existing
    evidence = source_evidence(db, owner, body.source_type, body.source_id)
    row = GovernanceModel(
        id=str(uuid4()),
        owner=owner,
        source_type=body.source_type,
        source_id=body.source_id,
        model_type=evidence["model_type"],
        model_version=evidence["model_version"],
        intended_use=redact(body.intended_use),
        status="candidate",
        payload={
            "registration_evidence": evidence,
            "approval_scope": "methodology_research",
            "assessments": {},
        },
        created_at=datetime.now(UTC),
    )
    db.add(row)
    db.flush()
    db.add(
        GovernanceReviewEvent(
            id=str(uuid4()),
            owner=owner,
            model_id=row.id,
            payload={
                "previous_status": None,
                "new_status": "candidate",
                "rationale": "Registered as a candidate only; no validation or approval inferred.",
                "actor": "system candidate registration",
                "reviewer_session": owner,
                "approval_scope": "methodology_research",
            },
            created_at=datetime.now(UTC),
        )
    )
    if commit:
        db.commit()
    return row


def review(db, row, body, actor=None):
    if body.status not in TRANSITIONS[row.status]:
        raise AppError(
            "GOVERNANCE_TRANSITION",
            "Requested state transition is not permitted; no review state changed.",
            409,
        )
    evidence = source_evidence(db, row.owner, row.source_type, row.source_id)
    assessments = {key: redact(value) for key, value in body.assessments.items()}
    if body.status == "validated":
        if not evidence["validation_ready"]:
            raise AppError(
                "GOVERNANCE_EVIDENCE",
                "Validation requires complete numerical/source checks and an executed successful saved-input reproduction.",
                409,
            )
        if set(assessments) != set(REVIEW_AREAS) or any(
            len(text.strip()) < 20 for text in assessments.values()
        ):
            raise AppError(
                "GOVERNANCE_ASSESSMENT",
                "Provide substantive written assessments for all eight review areas; unavailable out-of-sample/real-market evidence must be stated explicitly.",
            )
    if body.status == "approved_research" and (
        not evidence["validation_ready"] or not row.payload.get("assessments")
    ):
        raise AppError(
            "GOVERNANCE_EVIDENCE",
            "Approval requires previously recorded validation assessments and current reproducibility/integrity evidence.",
            409,
        )
    previous = row.status
    row.status = body.status
    row.payload = {
        **row.payload,
        "latest_evidence": evidence,
        "assessments": assessments or row.payload.get("assessments", {}),
        "approval_scope": "methodology_research",
    }
    db.add(
        GovernanceReviewEvent(
            id=str(uuid4()),
            owner=row.owner,
            model_id=row.id,
            payload={
                "previous_status": previous,
                "new_status": body.status,
                "rationale": redact(body.rationale),
                "reviewer_session": actor.auth_session_id if actor and actor.user_id else row.owner,
                "reviewer_user_id": actor.user_id if actor else None,
                "actor": "authorized session human confirmation",
                "approval_scope": body.approval_scope,
                "human_review": True,
                "research_only": True,
                "assessments": assessments,
                "evidence": evidence,
            },
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    return detail(db, row)
