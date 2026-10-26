"""Daily features at origin t; labels become available only at t+1."""

import numpy as np
import pandas as pd

from app.core.errors import AppError

LOOKBACK = 60


def ewma_path(returns, decay=0.94, initial=20):
    values = np.asarray(returns, dtype=np.float64)
    if (
        values.ndim != 1
        or not len(values)
        or not np.isfinite(values).all()
        or not 0 < decay < 1
        or initial < 1
    ):
        raise AppError(
            "INVALID_EWMA", "EWMA requires finite returns, valid decay and initialization."
        )
    output = np.full(len(values), np.nan)
    if len(values) < initial:
        return output
    state = float(np.mean(values[:initial] ** 2))
    output[initial - 1] = state
    for i in range(initial, len(values)):
        state = decay * state + (1 - decay) * values[i] ** 2
        output[i] = state
    return output


def build_features(
    returns: pd.Series,
    *,
    decay=0.94,
    feature_set="full",
    benchmark: pd.Series | None = None,
    sectors: pd.DataFrame | None = None,
):
    if (
        not isinstance(returns.index, pd.DatetimeIndex)
        or returns.index.has_duplicates
        or not returns.index.is_monotonic_increasing
    ):
        raise AppError("RESEARCH_DATES", "Research returns require increasing unique daily dates.")
    if not np.isfinite(returns.to_numpy()).all() or (returns <= -1).any():
        raise AppError(
            "RESEARCH_RETURNS", "Research returns must be finite and greater than -100%."
        )
    r = returns.astype(float)
    x = pd.DataFrame(index=r.index)
    for lag in (0, 1, 2, 5):
        x[f"return_lag_{lag}"] = r.shift(lag)
        x[f"squared_lag_{lag}"] = r.shift(lag) ** 2
    for window in (5, 10, 20, 60):
        x[f"second_moment_{window}"] = r.pow(2).rolling(window, min_periods=window).mean()
        x[f"mean_return_{window}"] = r.rolling(window, min_periods=window).mean()
    x["ewma_variance"] = ewma_path(r.to_numpy(), decay)
    if feature_set == "full":
        x["absolute_return"] = r.abs()
        wealth = (1 + r).cumprod()
        x["drawdown_20"] = wealth / wealth.rolling(20, min_periods=20).max() - 1
        x["momentum_20"] = (1 + r).rolling(20, min_periods=20).apply(np.prod, raw=True) - 1
        x["variance_ratio_5_60"] = x.second_moment_5 / (x.second_moment_60 + 1e-12)
        x["volatility_of_variance_20"] = r.pow(2).rolling(20, min_periods=20).std(ddof=0)
    if benchmark is not None:
        if not r.index.equals(benchmark.index) or not np.isfinite(benchmark.to_numpy()).all():
            raise AppError(
                "BENCHMARK_ALIGNMENT",
                "Benchmark must have exactly matching finite return observations.",
            )
        # Conservative one-observation lag for optional externally supplied context.
        market = benchmark.shift(1)
        x["benchmark_lag_1"] = market
        x["benchmark_second_moment_20"] = market.pow(2).rolling(20).mean()
        x["benchmark_correlation_60"] = r.shift(1).rolling(60).corr(market)
        x["benchmark_beta_60"] = r.shift(1).rolling(60).cov(market) / (
            market.rolling(60).var() + 1e-12
        )
    if sectors is not None and len(sectors.columns):
        if not sectors.index.equals(r.index) or not np.isfinite(sectors.to_numpy()).all():
            raise AppError(
                "SECTOR_ALIGNMENT",
                "Known-sector basket returns must align exactly with portfolio returns.",
            )
        lagged = sectors.shift(1)
        x["frozen_sector_dispersion_lag1"] = lagged.std(axis=1, ddof=0)
        x["frozen_sector_second_moment_20"] = lagged.pow(2).rolling(20).mean().mean(axis=1)
    return x.replace([np.inf, -np.inf], np.nan)


def fit_imputer(features: pd.DataFrame) -> dict:
    if features.empty:
        raise AppError("TRAINING_FEATURES", "No permitted training features remain after warmup.")
    medians = {}
    for name in features.columns:
        values = features[name].to_numpy(dtype=float)
        finite = values[np.isfinite(values)]
        if len(finite):
            medians[name] = float(np.median(finite))
    if not medians:
        raise AppError("TRAINING_FEATURES", "Every training feature is missing.")
    return {"medians": medians, "dropped_features": [c for c in features if c not in medians]}


def apply_imputer(features: pd.DataFrame, imputer: dict) -> np.ndarray:
    columns = list(imputer["medians"])
    values = features[columns].to_numpy(dtype=float, copy=True)
    for i, name in enumerate(columns):
        values[~np.isfinite(values[:, i]), i] = imputer["medians"][name]
    return np.ascontiguousarray(values, dtype=np.float64)


def training_pairs(
    features: pd.DataFrame, returns: pd.Series, origin_index: int, start_index: int = 0
):
    # Origin j has label r[j+1]^2; require j+1 <= forecast origin.
    stop = origin_index
    start = max(LOOKBACK - 1, start_index)
    x = features.iloc[start:stop]
    y = np.square(returns.iloc[start + 1 : stop + 1].to_numpy())
    if len(x) != len(y) or (len(x) and x.index[-1] >= returns.index[origin_index]):
        raise AppError("LABEL_LEAKAGE", "Training labels extend beyond the forecast origin.")
    return x, y
