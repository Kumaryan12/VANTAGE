"""Explicit owner deletion. Quarantine the scope first, then erase data and private objects."""

from datetime import UTC, datetime
from uuid import uuid4

from sqlalchemy import delete, select

from app.auth.identity import security_event, token_hash, write_scope
from app.core.errors import AppError
from app.database.models import (
    AgentEvaluation,
    AgentEvidence,
    AgentInvestigation,
    AgentStep,
    AgentToolCall,
    Dataset,
    DeletionRequest,
    ForecastModel,
    GovernanceModel,
    GovernanceReviewEvent,
    ModelGovernanceEvent,
    OptimizationCounterfactual,
    OptimizationRun,
    OwnershipScope,
    PortfolioSnapshot,
    PrivateArtifact,
    ProviderCredential,
    ResearchDocument,
    ResearchDocumentChunk,
    ResearchExperiment,
    ResearchForecast,
    ReviewAssignment,
    RiskInputArtifact,
    RiskRun,
    User,
)

from .service import delete as delete_object


def begin_delete(db, owner, user_id):
    scope = write_scope(db, owner)
    if scope.user_id != user_id:
        raise AppError("WORKSPACE_NOT_FOUND", "Workspace not found in this account.", 404)
    for model, statuses in (
        (ResearchExperiment, ["queued", "running"]),
        (AgentInvestigation, ["queued", "running"]),
        (OptimizationRun, ["queued", "running"]),
        (ResearchDocument, ["queued", "processing"]),
    ):
        if db.scalar(
            select(model.id).where(model.owner == owner, model.status.in_(statuses)).limit(1)
        ):
            raise AppError(
                "DELETION_ACTIVE_JOBS",
                "Cancel/wait for active work before deleting this workspace.",
                409,
            )
    scope.lifecycle = "deleting"
    request = DeletionRequest(
        id=str(uuid4()),
        owner=owner,
        actor_id=user_id,
        status="pending",
        created_at=datetime.now(UTC),
        outcome={
            "backup_erasure": "Not immediate; encrypted/offline backups follow documented retention."
        },
    )
    db.add(request)
    replacement = OwnershipScope(
        id=token_hash(str(uuid4())),
        user_id=user_id,
        name="Personal research",
        kind="personal",
        created_at=datetime.now(UTC),
        lifecycle="active",
    )
    db.add(replacement)
    db.get(User, user_id).preferred_scope = replacement.id
    security_event(db, "workspace_deletion_requested", user_id, target=owner)
    db.commit()
    return request


def execute_delete(db, request):
    if request.status == "completed":
        return request
    owner = request.owner
    scope = db.get(OwnershipScope, owner)
    if (
        scope is None
        or scope.user_id != request.actor_id
        or scope.lifecycle not in ("deleting", "deleted")
    ):
        raise AppError(
            "DELETION_SCOPE", "Deletion request ownership or quarantine is invalid.", 409
        )
    request.status = "running"
    db.commit()
    try:
        model_ids = select(ForecastModel.id).where(ForecastModel.owner == owner)
        investigation_ids = select(AgentInvestigation.id).where(AgentInvestigation.owner == owner)
        governance_ids = select(GovernanceModel.id).where(GovernanceModel.owner == owner)
        for artifact in db.scalars(
            select(PrivateArtifact).where(
                PrivateArtifact.owner == owner, PrivateArtifact.status != "deleted"
            )
        ).all():
            delete_object(db, artifact, request.actor_id)
        # Legacy files are removed only from authorized parent manifests, never inferred from names.
        from pathlib import Path

        from app.core.config import settings

        root = Path(settings().model_artifact_dir).resolve()
        for model in db.scalars(select(ForecastModel).where(ForecastModel.owner == owner)):
            for manifest in model.payload.get("artifact_files", []):
                if not manifest.get("storage_key"):
                    path = (root / manifest["path"]).resolve()
                    if not path.is_relative_to(root):
                        raise AppError("ARTIFACT_PATH", "Legacy artifact path is invalid.", 409)
                    path.unlink(missing_ok=True)
        from app.documents.service import private_path

        for document in db.scalars(select(ResearchDocument).where(ResearchDocument.owner == owner)):
            if not document.processing.get("storage_object"):
                private_path(document.id).unlink(missing_ok=True)
        for credential in db.scalars(
            select(ProviderCredential).where(ProviderCredential.owner == owner)
        ):
            credential.ciphertext = ""
            credential.revoked = 1
        counts = {}
        for model, condition in (
            (ResearchForecast, ResearchForecast.model_id.in_(model_ids)),
            (ModelGovernanceEvent, ModelGovernanceEvent.owner == owner),
            (ForecastModel, ForecastModel.owner == owner),
            (ReviewAssignment, ReviewAssignment.model_id.in_(governance_ids)),
            (GovernanceReviewEvent, GovernanceReviewEvent.owner == owner),
            (GovernanceModel, GovernanceModel.owner == owner),
            (AgentEvidence, AgentEvidence.investigation_id.in_(investigation_ids)),
            (AgentStep, AgentStep.investigation_id.in_(investigation_ids)),
            (AgentToolCall, AgentToolCall.investigation_id.in_(investigation_ids)),
            (AgentInvestigation, AgentInvestigation.owner == owner),
            (AgentEvaluation, AgentEvaluation.owner == owner),
            (OptimizationCounterfactual, OptimizationCounterfactual.owner == owner),
            (OptimizationRun, OptimizationRun.owner == owner),
            (RiskRun, RiskRun.owner == owner),
            (ResearchExperiment, ResearchExperiment.owner == owner),
            (ResearchDocumentChunk, ResearchDocumentChunk.owner == owner),
            (ResearchDocument, ResearchDocument.owner == owner),
            (Dataset, Dataset.owner == owner),
            (RiskInputArtifact, RiskInputArtifact.owner == owner),
            (PortfolioSnapshot, PortfolioSnapshot.owner == owner),
        ):
            counts[model.__tablename__] = db.execute(delete(model).where(condition)).rowcount
        scope.lifecycle = "deleted"
        scope.name = "Deleted workspace"
        request.status = "completed"
        request.finished_at = datetime.now(UTC)
        request.outcome = {
            **request.outcome,
            "active_data_deleted": True,
            "records_deleted": counts,
            "retained": "Security/deletion audit identifiers and deleted-object metadata follow retention; offline backups are not immediately erased.",
        }
        security_event(db, "workspace_deletion_completed", request.actor_id, target=owner)
        db.commit()
    except Exception:
        db.rollback()
        request = db.get(DeletionRequest, request.id)
        request.status = "failed"
        request.outcome = {
            **request.outcome,
            "active_data_deleted": False,
            "error": "Deletion did not finish; the workspace remains quarantined. Retry or contact an authorized operator.",
        }
        db.commit()
        raise AppError(
            "DELETION_INCOMPLETE",
            "Deletion did not finish; the workspace remains quarantined and can be retried.",
            503,
        ) from None
    return request
