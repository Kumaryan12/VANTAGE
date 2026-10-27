import numpy as np

from app.core.errors import AppError
from app.risk.artifacts import digest, frame_payload, payload_frame
from app.risk.conventions import minimum_observations
from app.risk.covariance import estimate_covariance
from app.risk.engine import asset_returns
from app.risk.service import resolve_prices

from .solver import validate_universe


def capture(db, portfolio, owner, parameters):
    prices, source = resolve_prices(db, portfolio, owner, parameters.dataset_id)
    prices = prices.tail(1261)
    return {"kind": "optimization", "history": frame_payload(prices, source)}


def prepare(portfolio, payload, parameters):
    prices, source = payload_frame(payload["history"])
    instruments = [h.instrument for h in portfolio.holdings]
    if list(prices.columns) != instruments:
        raise AppError(
            "ASSET_ORDER",
            "Saved history and portfolio must have exactly the same ordered instruments.",
        )
    if source.synthetic != portfolio.synthetic or source.adjustment != "split_dividend_adjusted":
        raise AppError(
            "OPTIMIZATION_SOURCE",
            "Mode-matched adjusted history is required; no substitution or filling.",
        )
    if len(prices) - 1 < parameters.window:
        raise AppError(
            "OPTIMIZATION_SAMPLE",
            f"Requested {parameters.window} returns but only {len(prices) - 1} are available. Select a supported window explicitly.",
        )
    if parameters.window < minimum_observations(parameters.confidence):
        raise AppError(
            "OPTIMIZATION_SAMPLE", "Window is too short for the selected risk confidence."
        )
    if prices.index[-1].date() > portfolio.as_of:
        raise AppError("FUTURE_HISTORY", "History extends after the saved valuation date.")
    selected = prices.tail(parameters.window + 1)
    returns = asset_returns(selected)
    covariance, diagnostics = estimate_covariance(returns, parameters.shrinkage)
    current = np.array([h.weight for h in portfolio.holdings], dtype=float)
    sectors = [h.sector for h in portfolio.holdings]
    validate_universe(instruments, sectors, current, covariance, parameters)
    covariance_hash = digest(
        {
            "instruments": instruments,
            "matrix": covariance.tolist(),
            "window": parameters.window,
            "shrinkage": parameters.shrinkage,
        }
    )
    price_hash = digest(
        {
            "instruments": instruments,
            "dates": [d.date().isoformat() for d in selected.index],
            "prices": selected.to_numpy().tolist(),
            "adjustment": source.adjustment,
            "synthetic": source.synthetic,
        }
    )
    dataset = {
        "source": source.model_dump(mode="json"),
        "synthetic": portfolio.synthetic,
        "sleeve": "Held INR cash-equity sleeve only; these are not whole-account allocation weights.",
        "account_cash": "Unavailable/excluded; not assumed zero.",
        "excluded": "Cash, derivatives, non-equity positions, financing, taxes, market impact and executable quantities are outside this sleeve.",
        "as_of": portfolio.as_of.isoformat(),
        "snapshot_retrieved_at": portfolio.retrieved_at.isoformat(),
        "sleeve_notional": portfolio.total_value,
        "currency": "INR",
        "instruments": instruments,
        "sectors": sectors,
        "current_weights": current.tolist(),
        "unknown_sector_policy": parameters.constraints.unknown_sector_policy,
        "unknown_sector_weight": sum(h.weight for h in portfolio.holdings if h.sector == "Unknown"),
        "estimation_start": selected.index[0].date().isoformat(),
        "estimation_end": selected.index[-1].date().isoformat(),
        "observations": len(returns),
        "available_returns": len(prices) - 1,
        "price_value_hash": price_hash,
        "covariance_hash": covariance_hash,
        "covariance_diagnostics": diagnostics,
        "return_convention": "Adjusted daily simple returns; full aligned held universe, fixed current weights; source calendar/adjustment assertions remain unverified.",
        "horizon": "One observed trading day; annual volatility uses sqrt(252).",
    }
    return selected, returns, covariance, dataset
