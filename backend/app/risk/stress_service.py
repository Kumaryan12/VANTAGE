from uuid import uuid4

import numpy as np
import pandas as pd
from sqlalchemy.orm import Session

from app.core.errors import AppError
from app.portfolios.schemas import Portfolio
from app.risk.artifacts import frame_payload, metadata, payload_frame, persist_inputs, persist_run
from app.risk.contracts import ScenarioAvailability, StressRequest, StressResult
from app.risk.engine import calculate
from app.risk.service import resolve_prices
from app.risk.stress import NAMED_WINDOWS, historical_replay, hypothetical
from app.risk.tails import empirical_tail


def scenario_dates(parameters: StressRequest, synthetic: bool):
    if not parameters.scenario_id:
        return parameters.start, parameters.end
    scenario = next((s for s in NAMED_WINDOWS if s["id"] == parameters.scenario_id), None)
    if scenario is None:
        raise AppError("SCENARIO_NOT_FOUND", "Unknown named stress window.", 404)
    if scenario["synthetic"] != synthetic:
        raise AppError(
            "SCENARIO_SOURCE_MISMATCH",
            "Synthetic windows and actual historical market scenarios require matching source modes.",
        )
    return pd.Timestamp(scenario["start"]).date(), pd.Timestamp(scenario["end"]).date()


def scenario_catalog(db: Session, portfolio: Portfolio, owner: str, dataset_id: str | None):
    reason = None
    try:
        prices, _ = resolve_prices(db, portfolio, owner, dataset_id, require_fresh=False)
    except AppError as error:
        if error.status in (401, 403, 404, 409):
            raise
        prices, reason = None, error.message
    result = []
    for scenario in NAMED_WINDOWS:
        unavailable = reason
        if scenario["synthetic"] != portfolio.synthetic:
            unavailable = (
                "Synthetic fixture data cannot represent actual historical market observations."
                if portfolio.synthetic
                else "Synthetic fixture windows are available only in Demo Mode."
            )
        elif prices is not None:
            if any(pd.Timestamp(scenario[key]) not in prices.index for key in ("start", "end")):
                unavailable = "Selected data does not cover the exact start and end observations for this scenario."
            elif pd.Timestamp(scenario["end"]).date() > portfolio.as_of:
                unavailable = "Scenario ends after the portfolio valuation date."
        result.append(
            ScenarioAvailability(
                **scenario,
                available=unavailable is None,
                reason=unavailable
                or "Exact endpoints and aligned holding coverage available; source-calendar continuity is an importer assertion.",
            )
        )
    return result


def reference_context(db, portfolio, owner, parameters):
    try:
        prices, provenance = resolve_prices(db, portfolio, owner, parameters.dataset_id)
        legacy = calculate(
            prices,
            np.array([h.weight for h in portfolio.holdings]),
            parameters.confidence,
            parameters.window,
        )
        prices = prices.tail(parameters.window + 1)
        return frame_payload(prices, provenance), legacy, None
    except AppError as error:
        # An unauthorized/mutated supplied dataset must not be converted into a partial success.
        if error.status in (401, 403, 404, 409):
            raise
        return None, None, f"Current one-day risk comparison unavailable: {error.message}"


def run_stress(
    db: Session,
    portfolio: Portfolio,
    owner: str,
    parameters: StressRequest,
    *,
    replay_payload: dict | None = None,
):
    payload = {"kind": "stress"}
    provenance = None
    warnings = list(portfolio.warnings)
    if parameters.kind == "historical":
        start, end = scenario_dates(parameters, portfolio.synthetic)
        if replay_payload is None:
            prices, provenance = resolve_prices(
                db,
                portfolio,
                owner,
                parameters.scenario_dataset_id or parameters.dataset_id,
                require_fresh=False,
            )
        else:
            prices, provenance = payload_frame(replay_payload["scenario"])
        output = historical_replay(portfolio, prices, start, end)
        selected = prices.loc[pd.Timestamp(start) : pd.Timestamp(end)]
        payload["scenario"] = frame_payload(selected, provenance)
        kind = "synthetic_replay" if portfolio.synthetic else "historical"
        if portfolio.synthetic:
            warnings.append("SYNTHETIC REPLAY: this is not an actual historical market event.")
    else:
        output = hypothetical(
            portfolio, parameters.market_shock, parameters.sector_shocks, parameters.security_shocks
        )
        kind = "hypothetical"
    if replay_payload is None:
        reference, legacy, reference_warning = reference_context(db, portfolio, owner, parameters)
    else:
        reference = replay_payload.get("reference")
        legacy = None
        reference_warning = replay_payload.get("reference_warning")
        if reference:
            prices, _ = payload_frame(reference)
            legacy = calculate(
                prices,
                np.array([h.weight for h in portfolio.holdings]),
                parameters.confidence,
                parameters.window,
            )
    payload["reference"] = reference
    payload["reference_warning"] = reference_warning
    comparison = None
    if legacy and reference:
        ref_prices, _ = payload_frame(reference)
        returns = ref_prices.pct_change(fill_method=None).iloc[1:].to_numpy() @ np.array(
            [h.weight for h in portfolio.holdings]
        )
        tails = empirical_tail(-portfolio.total_value * returns, parameters.confidence)
        comparison = {
            "historical_var": tails["var"],
            "historical_es": tails["expected_shortfall"],
            "stress_loss_to_var": output["loss"] / tails["var"] if tails["var"] > 0 else None,
            "note": "Descriptive comparison with current one-day historical risk. A multi-day replay has a different horizon; the ratio is not a probability, coverage test, or prediction.",
        }
    if reference_warning:
        warnings.append(reference_warning)
    warnings.append(
        "Direct stress P&L is not volatility or VaR attribution. Scenarios are conditional what-if calculations, not forecasts."
    )
    snapshot, artifact = persist_inputs(db, portfolio, payload, owner)
    meta = metadata(
        portfolio,
        parameters,
        snapshot,
        artifact,
        methodology="stress_replay" if parameters.kind == "historical" else "direct_shock",
        sample_size=legacy["sample_size"] if legacy else 0,
        provenance=provenance,
        start=legacy["start"].date() if legacy else None,
        end=legacy["end"].date() if legacy else None,
        warnings=warnings,
    )
    result = StressResult(
        **output,
        scenario_kind=kind,
        run_id=str(uuid4()),
        name=parameters.name,
        portfolio=portfolio,
        parameters=parameters,
        metadata=meta,
        provenance=provenance,
        reference_risk=comparison,
    )
    return persist_run(db, result, owner)
