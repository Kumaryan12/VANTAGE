"""Model-scoped independent review; platform administration is not financial-data access."""

from sqlalchemy import select

from app.auth.identity import require_role, roles_for, security_event
from app.core.errors import AppError
from app.database.models import GovernanceModel, OwnershipScope, ReviewAssignment, User

from .service import TRANSITIONS, detail


def creator(db, row):
    scope = db.get(OwnershipScope, row.owner)
    return scope.user_id if scope else None


def independent_reviewer(db, session, row):
    if (
        not session.user_id
        or session.user_id == creator(db, row)
        or "RESEARCH_REVIEWER" not in roles_for(db, session.user_id)
    ):
        return False
    assigned = db.get(ReviewAssignment, (row.id, session.user_id))
    return bool(assigned and assigned.active)


def authorized(db, ident, session, scope):
    row = db.get(GovernanceModel, ident)
    if row is None or (row.owner != scope and not independent_reviewer(db, session, row)):
        raise AppError(
            "GOVERNANCE_NOT_FOUND", "Review model not found in the authorized scope.", 404
        )
    return row


def permitted(db, session, row, status, scope):
    if not session.user_id:
        return (
            row.owner == scope
        )  # Explicit local legacy compatibility; production requires identity.
    if status in ("validated", "approved_research", "rejected"):
        return independent_reviewer(db, session, row)
    return row.owner == scope or independent_reviewer(db, session, row)


def review_permission(db, session, row, status, scope):
    if not permitted(db, session, row, status, scope):
        raise AppError(
            "INDEPENDENT_REVIEW_REQUIRED",
            "This decision requires a different explicitly assigned research reviewer; creators cannot validate or approve their own model.",
            403,
        )


def public_detail(db, row, session, scope):
    result = detail(db, row)
    return result.model_copy(
        update={
            "allowed_transitions": [
                s for s in TRANSITIONS[row.status] if permitted(db, session, row, s, scope)
            ]
        }
    )


def assign(db, row, session, scope, reviewer_id, active):
    actor = require_role(db, session, "RESEARCH_ADMIN")
    if row.owner != scope:
        raise AppError(
            "GOVERNANCE_NOT_FOUND", "Model not found in the administered workspace.", 404
        )
    reviewer = db.get(User, reviewer_id)
    if not reviewer or not reviewer.active or "RESEARCH_REVIEWER" not in roles_for(db, reviewer_id):
        raise AppError(
            "REVIEWER_UNAVAILABLE",
            "An active explicitly provisioned research reviewer is required.",
        )
    if reviewer_id == creator(db, row):
        raise AppError(
            "REVIEWER_SEPARATION", "The model creator cannot be its independent reviewer.", 409
        )
    assignment = db.get(ReviewAssignment, (row.id, reviewer_id))
    if assignment is None:
        from datetime import UTC, datetime

        assignment = ReviewAssignment(
            model_id=row.id,
            reviewer_id=reviewer_id,
            assigned_by=actor,
            created_at=datetime.now(UTC),
            active=int(active),
        )
        db.add(assignment)
    else:
        assignment.active = int(active)
    security_event(
        db,
        "review_assignment_changed",
        actor,
        target=row.id,
        reviewer_id=reviewer_id,
        active=active,
    )
    db.commit()
    return {"model_id": row.id, "reviewer_id": reviewer_id, "active": active}


def require_champion_review(db, session, model):
    if not session.user_id:
        return  # Original explicitly local guest research workflow.
    require_role(db, session, "RESEARCH_ADMIN")
    row = db.scalar(
        select(GovernanceModel).where(
            GovernanceModel.owner == model.owner,
            GovernanceModel.source_type == "forecast",
            GovernanceModel.source_id == model.id,
        )
    )
    if row is None or row.status != "approved_research":
        raise AppError(
            "INDEPENDENT_REVIEW_REQUIRED",
            "Champion designation requires an independently approved research-governance source.",
            403,
        )
    from .service import source_evidence

    if not source_evidence(db, row.owner, row.source_type, row.source_id)["validation_ready"]:
        raise AppError(
            "GOVERNANCE_EVIDENCE",
            "Current source integrity/reproduction evidence is incomplete.",
            409,
        )
