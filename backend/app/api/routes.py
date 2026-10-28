import hashlib
import re
import secrets
import time
from datetime import UTC, date, datetime
from typing import Annotated, Literal
from urllib.parse import urlencode

from fastapi import APIRouter, Depends, File, Form, Query, Request, UploadFile
from fastapi.responses import RedirectResponse
from kiteconnect.exceptions import KiteException
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, text, update
from sqlalchemy.orm import Session

from app.auth.sessions import (
    BrowserSession,
    broker_connected,
    browser_session,
    set_broker_token,
    store,
)
from app.brokers.demo import DemoBroker
from app.brokers.kite import KiteBroker, configured, new_client
from app.core.config import settings
from app.core.errors import AppError
from app.database.models import (
    AgentInvestigation,
    Dataset,
    ResearchDocument,
    ResearchExperiment,
    RiskRun,
)
from app.database.session import get_db
from app.ingestion.history import MAX_BYTES, parse_upload, persist_history
from app.integrations.providers import providers
from app.portfolios.schemas import Portfolio, RiskResult
from app.risk.service import risk_for_portfolio

router = APIRouter(prefix="/api")
DB = Annotated[Session, Depends(get_db)]
Browser = Annotated[BrowserSession, Depends(browser_session)]
Mode = Literal["demo", "kite"]
Adjustment = Literal["split_dividend_adjusted", "unadjusted", "unknown"]


def owner(session: BrowserSession):
    return session.owner_id or hashlib.sha256(session.id.encode()).hexdigest()


@router.get("/health")
def health(request: Request, db: DB):
    from app.database.models import AgentToolCall, AuthSession, GovernanceModel, OptimizationRun

    try:
        db.execute(text("SELECT 1"))
        db.execute(select(Dataset.id).limit(1))
        db.execute(select(RiskRun.schema_version).limit(1))
        db.execute(select(ResearchExperiment.id).limit(1))
        db.execute(select(AgentInvestigation.id).limit(1))
        db.execute(select(ResearchDocument.id).limit(1))
        db.execute(select(AgentToolCall.sequence).limit(1))
        db.execute(select(OptimizationRun.id).limit(1))
        db.execute(select(GovernanceModel.id).limit(1))
        db.execute(select(AuthSession.id).limit(1))
        from app.database.models import PrivateArtifact, ProviderCredential

        db.execute(select(PrivateArtifact.id).limit(1))
        db.execute(select(ProviderCredential.id).limit(1))
    except Exception:
        raise AppError(
            "DATABASE_UNAVAILABLE", "Database unavailable or migrations have not been applied.", 503
        ) from None
    return {"status": "ok", "version": request.app.version, "trading_enabled": False}


@router.get("/session")
def session_status(session: Browser):
    return {
        "kite_configured": configured(),
        "kite_connected": broker_connected(session),
        "trading_enabled": False,
    }


def snapshot(mode: Mode, session: BrowserSession):
    return DemoBroker().portfolio() if mode == "demo" else KiteBroker(session).portfolio()


@router.get("/portfolio", response_model=Portfolio)
def portfolio(session: Browser, mode: Mode = "demo"):
    return snapshot(mode, session)


@router.get("/risk", response_model=RiskResult)
def risk(
    session: Browser,
    db: DB,
    mode: Mode = "demo",
    confidence: float = Query(0.95, ge=0.90, le=0.995),
    window: int = Query(252, ge=60, le=1260),
    dataset_id: str | None = None,
):
    return risk_for_portfolio(
        db, snapshot(mode, session), owner(session), dataset_id, confidence, window
    )


@router.get("/history")
def history(session: Browser, db: DB):
    datasets = db.scalars(
        select(Dataset).where(Dataset.owner == owner(session)).order_by(Dataset.created_at.desc())
    ).all()
    return [{"id": d.id, "provenance": d.provenance} for d in datasets]


@router.post("/history/import", status_code=201)
async def import_history(
    session: Browser,
    db: DB,
    file: UploadFile = File(),
    source: str = Form(min_length=3, max_length=250),
    adjustment: Adjustment = Form(),
):
    content = await file.read(MAX_BYTES + 1)
    return persist_history(
        db, parse_upload(content, file.filename or ""), source, adjustment, owner(session)
    )


class AlphaImport(BaseModel):
    mapping: dict[str, str] = Field(min_length=1, max_length=10)
    currency: Literal["INR"]
    currency_and_venue_verified: Literal[True]

    @model_validator(mode="after")
    def valid_mapping(self):
        for instrument, symbol in self.mapping.items():
            if not re.fullmatch(r"(?:NSE|BSE):[A-Z0-9&_.-]{1,40}", instrument) or not re.fullmatch(
                r"[A-Z0-9&_.-]{1,60}", symbol
            ):
                raise ValueError(
                    "Use explicit canonical instrument identifiers and provider ticker symbols."
                )
        return self


@router.post("/history/alpha-vantage", status_code=201)
def import_alpha(body: AlphaImport, session: Browser, db: DB):
    frame = providers.adjusted_history(body.mapping, body.currency)
    mapping_note = ", ".join(f"{k}={v}" for k, v in body.mapping.items())
    return persist_history(
        db,
        frame,
        f"Alpha Vantage adjusted daily; verified mapping: {mapping_note}",
        "split_dividend_adjusted",
        owner(session),
    )


@router.get("/sources")
def sources():
    return [
        {
            "id": "demo",
            "name": "Synthetic fixture",
            "configured": True,
            "purpose": "Repeatable INR portfolio and history",
            "note": "Invented securities, fixed seed, versioned observations.",
        },
        {
            "id": "kite",
            "name": "Zerodha Kite Connect",
            "configured": configured(),
            "purpose": "Read-only holdings and account data",
            "note": "Interactive authorization. Historical-data entitlement is not assumed.",
        },
        {
            "id": "csv",
            "name": "CSV / Parquet",
            "configured": True,
            "purpose": "Independent adjusted daily histories",
            "note": "Source, INR currency, adjustment and complete coverage required.",
        },
        {
            "id": "alpha",
            "name": "Alpha Vantage",
            "configured": bool(settings().alpha_vantage_api_key),
            "purpose": "Adjusted daily price history",
            "note": "Requires API key and premium adjusted-daily entitlement; explicit venue mapping.",
        },
        {
            "id": "fred",
            "name": "FRED",
            "configured": bool(settings().fred_api_key),
            "purpose": "Vintage-aware macroeconomic context",
            "note": "Context only. Never silently used as a forecasting feature.",
        },
        {
            "id": "fx",
            "name": "Frankfurter",
            "configured": True,
            "purpose": "Daily FX reference context",
            "note": "No API key. Provider availability is checked when requested; no valuation conversion.",
        },
    ]


@router.get("/context/fx")
def fx(
    base: str = Query("USD", pattern=r"^[A-Z]{3}$"),
    quote: str = Query("INR", pattern=r"^[A-Z]{3}$"),
):
    return providers.fx(base, quote)


@router.get("/context/macro")
def macro(
    series_id: str = Query("VIXCLS", pattern=r"^[A-Z0-9_]{1,30}$"), vintage: date | None = None
):
    return providers.macro(series_id, vintage or datetime.now(UTC).date())


@router.get("/auth/kite/login")
def kite_login(request: Request, db: DB):
    response = RedirectResponse("/", status_code=303)
    session = browser_session(request, response, db)
    client = new_client()
    session.state = secrets.token_urlsafe(32)
    session.state_expires = time.time() + 600
    if session.user_id:
        from app.auth.identity import token_hash
        from app.database.models import AuthSession

        row = db.get(AuthSession, session.auth_session_id)
        row.oauth_state_hash = token_hash(session.state)
        row.oauth_state_expires = int(session.state_expires)
        db.commit()
    response.headers["location"] = (
        client.login_url()
        + "&"
        + urlencode({"redirect_params": urlencode({"state": session.state})})
    )
    return response


@router.get("/auth/kite/callback")
def kite_callback(
    request: Request,
    db: DB,
    request_token: str = Query(min_length=1, max_length=512),
    state: str = Query(min_length=1, max_length=128),
):
    response = RedirectResponse(settings().frontend_url + "/?connected=kite", status_code=303)
    session = browser_session(request, response, db)
    if session.user_id:
        from app.auth.identity import token_hash
        from app.database.models import AuthSession

        used = db.execute(
            update(AuthSession)
            .where(
                AuthSession.id == session.auth_session_id,
                AuthSession.oauth_state_hash == token_hash(state),
                AuthSession.oauth_state_expires > int(time.time()),
                AuthSession.revoked == 0,
            )
            .values(oauth_state_hash=None, oauth_state_expires=None)
        ).rowcount
        db.commit()
        if not used:
            raise AppError(
                "INVALID_AUTH_STATE", "Broker login state is missing, expired or invalid.", 400
            )
    else:
        store.consume_state(session, state)
    try:
        data = new_client().generate_session(request_token, api_secret=settings().kite_api_secret)
        set_broker_token(session, data["access_token"])
    except (KiteException, OSError, KeyError, ValueError):
        raise AppError(
            "KITE_AUTH_FAILED", "Kite authorization failed. Start a fresh login.", 401
        ) from None
    return response


@router.post("/auth/kite/logout")
def kite_logout(session: Browser):
    revoked = True
    if broker_connected(session):
        try:
            KiteBroker(session).logout()
        except AppError:
            revoked = False
    session.state = None
    return {"connected": False, "remote_revocation_confirmed": revoked}


@router.get("/kite/positions")
def positions(session: Browser):
    return {
        "source": "Kite Connect",
        "excluded_from_holdings_risk": True,
        "data": KiteBroker(session).positions(),
    }


@router.get("/kite/margins")
def margins(session: Browser):
    return {"source": "Kite Connect", "data": KiteBroker(session).margins()}


@router.get("/kite/instruments")
def instruments(
    session: Browser,
    exchange: Literal["NSE", "BSE"] = "NSE",
    limit: int = Query(100, ge=1, le=1000),
):
    data = KiteBroker(session).instruments(exchange)
    return {"source": "Kite Connect", "total": len(data), "data": data[:limit]}
