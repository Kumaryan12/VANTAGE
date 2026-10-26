"""Pure deterministic risk functions. No API, database, or broker dependencies."""

import numpy as np
import pandas as pd

from app.core.errors import AppError
from app.risk.conventions import minimum_observations, validate_confidence
from app.risk.tails import empirical_tail

METHOD = "historical-current-weights-v1"


def aligned_prices(frame: pd.DataFrame, instruments: list[str]) -> pd.DataFrame:
    required = {"date", "instrument", "close"}
    if not required.issubset(frame.columns):
        raise AppError("HISTORY_SCHEMA", "Missing required historical columns.")
    if not instruments or len(set(instruments)) != len(instruments):
        raise AppError(
            "INVALID_INSTRUMENTS", "Historical alignment requires unique nonempty instruments."
        )
    data = frame[frame.instrument.isin(instruments)].copy()
    try:
        data["date"] = pd.to_datetime(data.date, errors="raise")
        if (
            data.date.isna().any()
            or data.date.dt.tz is not None
            or not data.date.eq(data.date.dt.normalize()).all()
        ):
            raise ValueError
    except (ValueError, TypeError, AttributeError):
        raise AppError(
            "INVALID_DATES", "Historical observations must have valid daily, timezone-free dates."
        ) from None
    missing = sorted(set(instruments) - set(data.instrument))
    if missing:
        raise AppError(
            "MISSING_COVERAGE", "Historical data does not cover every holding.", details=missing
        )
    if data.duplicated(["date", "instrument"]).any():
        raise AppError("DUPLICATE_OBSERVATION", "Duplicate instrument/date observations.")
    prices = data.pivot(index="date", columns="instrument", values="close").sort_index()
    prices = prices[instruments]
    values = prices.to_numpy(dtype=float)
    if not np.isfinite(values).all() or (values <= 0).any():
        raise AppError(
            "UNALIGNED_HISTORY",
            "Every holding must have positive prices on exactly the same observation dates. No fill is performed.",
        )
    return prices


def historical_var(returns: np.ndarray, confidence: float) -> float:
    values = np.asarray(returns, dtype=float)
    if values.ndim != 1 or not len(values) or not np.isfinite(values).all():
        raise AppError("INVALID_RETURNS", "Returns must be a nonempty finite vector.")
    return empirical_tail(-values, confidence)["var"]


def annualized_volatility(returns: np.ndarray) -> float:
    values = np.asarray(returns, dtype=float)
    if values.ndim != 1 or len(values) < 2 or not np.isfinite(values).all():
        raise AppError("INVALID_RETURNS", "Volatility requires at least two finite returns.")
    return float(np.std(values, ddof=1) * np.sqrt(252))


def scenario_path(returns: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    values = np.asarray(returns, dtype=float)
    if values.ndim != 1 or not np.isfinite(values).all() or (values <= -1).any():
        raise AppError("INVALID_RETURNS", "Scenario returns must be finite and greater than -1.")
    index = np.concatenate(([100.0], 100.0 * np.cumprod(1 + values)))
    drawdown = index / np.maximum.accumulate(index) - 1
    return index, drawdown


def calculate(prices: pd.DataFrame, weights: np.ndarray, confidence: float, window: int) -> dict:
    validate_confidence(confidence)
    weights = np.asarray(weights, dtype=float)
    if (
        weights.shape != (prices.shape[1],)
        or not np.isfinite(weights).all()
        or (weights < 0).any()
        or not np.isclose(weights.sum(), 1, atol=1e-10, rtol=0)
    ):
        raise AppError(
            "INVALID_WEIGHTS", "Long-only weights must align with columns and sum to one."
        )
    values = prices.to_numpy(dtype=float)
    if (
        not prices.index.is_monotonic_increasing
        or prices.index.has_duplicates
        or not np.isfinite(values).all()
        or (values <= 0).any()
    ):
        raise AppError("INVALID_PRICES", "Prices must be positive and dates unique and increasing.")
    if not 60 <= window <= 1260:
        raise AppError("INVALID_WINDOW", "Window must be between 60 and 1260 daily returns.")
    prices = prices.tail(window + 1)
    returns = prices.pct_change(fill_method=None).iloc[1:]
    minimum = minimum_observations(confidence)
    if len(returns) < minimum:
        raise AppError(
            "INSUFFICIENT_HISTORY", f"At least {minimum} aligned daily returns required."
        )
    portfolio_returns = returns.to_numpy() @ weights
    index, drawdown = scenario_path(portfolio_returns)
    rolling = pd.Series(portfolio_returns).rolling(21).std(ddof=1) * np.sqrt(252)
    covariance = returns.cov().to_numpy()
    correlation = returns.corr().to_numpy()
    return {
        "annualized_volatility": annualized_volatility(portfolio_returns),
        "historical_var": historical_var(portfolio_returns, confidence),
        "maximum_drawdown": float(-drawdown.min()),
        "sample_size": len(returns),
        "tail_sample_mass": float((1 - confidence) * len(returns)),
        "start": prices.index[0],
        "end": prices.index[-1],
        "covariance": covariance.tolist(),
        "correlation": [[float(x) if np.isfinite(x) else None for x in row] for row in correlation],
        "instruments": list(prices.columns),
        "series": [
            {
                "date": dt,
                "scenario_index": float(index[i]),
                "drawdown": float(drawdown[i]),
                "daily_return": None if i == 0 else float(portfolio_returns[i - 1]),
                "rolling_volatility": None
                if i == 0 or pd.isna(rolling.iloc[i - 1])
                else float(rolling.iloc[i - 1]),
            }
            for i, dt in enumerate(prices.index)
        ],
    }
