import hashlib
import json
from datetime import UTC, datetime
from uuid import uuid4

import numpy as np
from sqlalchemy.orm import Session

from app.brokers.demo import demo_history
from app.core.errors import AppError
from app.database.models import RiskRun
from app.ingestion.history import load_history
from app.portfolios.schemas import Portfolio, RiskResult
from app.risk.engine import METHOD, aligned_prices, calculate


def resolve_prices(db, portfolio, owner, dataset_id, *, require_fresh=True):
    if portfolio.mode == "demo":
        if dataset_id:
            raise AppError(
                "SOURCE_MODE_MISMATCH", "Demo Mode uses only the versioned synthetic fixture."
            )
        frame, provenance = demo_history()
    else:
        if not dataset_id:
            raise AppError(
                "HISTORY_REQUIRED",
                "Holdings loaded. Import adjusted INR history covering every held instrument to enable risk calculations.",
            )
        frame, provenance = load_history(db, dataset_id, owner)
    if provenance.synthetic != portfolio.synthetic:
        raise AppError(
            "SOURCE_MODE_MISMATCH", "Synthetic and real portfolio/history sources cannot be mixed."
        )
    if provenance.adjustment != "split_dividend_adjusted":
        raise AppError(
            "ADJUSTMENT_REQUIRED",
            "Risk requires history explicitly marked split/dividend adjusted.",
        )
    prices = aligned_prices(frame, [h.instrument for h in portfolio.holdings])
    if prices.index[-1].date() > portfolio.as_of:
        raise AppError(
            "FUTURE_HISTORY", "History cannot extend beyond the portfolio valuation date."
        )
    if require_fresh and (portfolio.as_of - prices.index[-1].date()).days > 7:
        raise AppError(
            "STALE_HISTORY", "History ends more than seven calendar days before the valuation date."
        )
    return prices, provenance


def risk_for_portfolio(
    db: Session,
    portfolio: Portfolio,
    owner: str,
    dataset_id: str | None,
    confidence: float,
    window: int,
):
    prices, provenance = resolve_prices(db, portfolio, owner, dataset_id)
    output = calculate(prices, np.array([h.weight for h in portfolio.holdings]), confidence, window)
    run_id = str(uuid4())
    result = RiskResult(
        **output,
        run_id=run_id,
        methodology=METHOD,
        mode=portfolio.mode,
        confidence=confidence,
        horizon="1 observed trading day",
        loss_convention="Positive = loss; negative = gain",
        weighting="Current snapshot weights applied to historical daily returns; not account performance",
        requested_window=window,
        historical_var_amount=portfolio.total_value * output["historical_var"],
        provenance=provenance,
        warnings=[
            "Past scenarios do not guarantee future risk coverage. VaR is not maximum possible loss.",
            "Holdings-only risk excludes cash, open positions, liquidity, taxes, and costs.",
        ]
        + (
            ["Available history is shorter than the requested window."]
            if output["sample_size"] < window
            else []
        ),
    )
    input_hash = hashlib.sha256(
        json.dumps(
            {
                "snapshot": portfolio.model_dump(mode="json"),
                "data": provenance.content_hash,
                "confidence": confidence,
                "window": window,
            },
            sort_keys=True,
        ).encode()
    ).hexdigest()
    db.add(
        RiskRun(
            id=run_id,
            owner=owner,
            input_hash=input_hash,
            methodology=METHOD,
            result=result.model_dump(mode="json"),
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    return result
