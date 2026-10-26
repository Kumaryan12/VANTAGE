from fastapi import APIRouter, Query
from sqlalchemy import select

from app.agent.contracts import (
    Activity,
    InvestigationDetail,
    InvestigationRequest,
    InvestigationSummary,
    ProviderStatus,
    ToolEvidence,
)
from app.agent.service import detail, owned, queue, summary
from app.api.routes import DB, Browser, owner, snapshot
from app.core.config import settings
from app.database.models import AgentEvidence, AgentInvestigation, AgentStep, AgentToolCall

router = APIRouter(prefix="/api/v1/agent", tags=["Financial investigations"])


@router.get("/status", response_model=ProviderStatus)
def provider_status(session: Browser):
    config = settings()
    return ProviderStatus(
        configured=bool(config.openai_api_key),
        provider="openai",
        model=config.llm_model,
        demo_available=True,
        embeddings_available=False,
        message="Configured provider available; external processing requires request consent."
        if config.openai_api_key
        else "AI provider not configured. Deterministic demonstration is available and explicitly labeled.",
    )


@router.post("/investigate", response_model=InvestigationSummary, status_code=202)
def investigate(body: InvestigationRequest, session: Browser, db: DB):
    return queue.submit(db, snapshot(body.mode, session), owner(session), body)


@router.get("/investigations", response_model=list[InvestigationSummary])
def investigations(
    session: Browser, db: DB, limit: int = Query(20, ge=1, le=100), offset: int = Query(0, ge=0)
):
    rows = db.scalars(
        select(AgentInvestigation)
        .where(AgentInvestigation.owner == owner(session))
        .order_by(AgentInvestigation.created_at.desc())
        .limit(limit)
        .offset(offset)
    ).all()
    return [summary(owned(db, r.id, owner(session))) for r in rows]


@router.get("/investigations/{ident}", response_model=InvestigationDetail)
def investigation(ident: str, session: Browser, db: DB):
    return detail(owned(db, ident, owner(session)))


@router.post("/investigations/{ident}/cancel", response_model=InvestigationSummary)
def cancel(ident: str, session: Browser, db: DB):
    return queue.cancel(db, owned(db, ident, owner(session)))


@router.get("/investigations/{ident}/trace", response_model=list[Activity])
def trace(ident: str, session: Browser, db: DB):
    owned(db, ident, owner(session))
    return [
        r.payload
        for r in db.scalars(
            select(AgentStep)
            .where(AgentStep.investigation_id == ident)
            .order_by(AgentStep.sequence)
        ).all()
    ]


@router.get("/investigations/{ident}/tool-calls", response_model=list[dict])
def calls(ident: str, session: Browser, db: DB):
    owned(db, ident, owner(session))
    return [
        r.payload
        for r in db.scalars(
            select(AgentToolCall).where(AgentToolCall.investigation_id == ident)
        ).all()
    ]


@router.get("/investigations/{ident}/evidence", response_model=list[ToolEvidence])
def evidence(ident: str, session: Browser, db: DB):
    owned(db, ident, owner(session))
    return [
        r.payload
        for r in db.scalars(
            select(AgentEvidence).where(AgentEvidence.investigation_id == ident)
        ).all()
    ]
