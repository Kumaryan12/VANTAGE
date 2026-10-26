"""Matched-date variance loss and VaR calibration diagnostics."""

import math

import numpy as np
from scipy.special import xlogy
from scipy.stats import binomtest, chi2

from app.core.errors import AppError


def variance_losses(realized, forecast):
    y = np.asarray(realized, dtype=float)
    h = np.asarray(forecast, dtype=float)
    if (
        y.ndim != 1
        or not len(y)
        or y.shape != h.shape
        or not np.isfinite([y, h]).all()
        or (y < 0).any()
        or (h <= 0).any()
    ):
        raise AppError(
            "INVALID_VARIANCE_FORECAST",
            "QLIKE requires matched finite nonnegative realized variance and positive variance forecasts.",
        )
    return {
        "qlike": np.log(h) + y / h,
        "squared_error": (h - y) ** 2,
        "absolute_error": np.abs(h - y),
    }


def bernoulli_log_likelihood(successes, total, p):
    return float(xlogy(successes, p) + xlogy(total - successes, 1 - p))


def coverage_tests(exceptions, confidence, min_n=100):
    e = np.asarray(exceptions)
    if e.ndim != 1 or not np.isin(e, [0, 1, False, True]).all() or confidence not in (0.95, 0.99):
        raise AppError(
            "INVALID_EXCEPTIONS", "Coverage requires a binary vector and 95% or 99% confidence."
        )
    n = len(e)
    count = int(e.sum())
    q = 1 - confidence
    transitions = {
        f"n{i}{j}": int(np.sum((e[:-1] == i) & (e[1:] == j))) for i in (0, 1) for j in (0, 1)
    }
    result = {
        "confidence": confidence,
        "observations": n,
        "exceptions": count,
        "exception_rate": count / n if n else None,
        "nominal_rate": q,
        "expected_exceptions": n * q,
        "kupiec_statistic": None,
        "kupiec_p_value": None,
        "independence_statistic": None,
        "independence_p_value": None,
        "conditional_statistic": None,
        "conditional_p_value": None,
        "exact_binomial_p_value": float(binomtest(count, n, q).pvalue) if n else None,
        "transitions": transitions,
        "warnings": [],
    }
    if n < min_n:
        result["warnings"].append(
            f"At least {min_n} observations required for asymptotic coverage diagnostics; exact binomial p-value is descriptive under independent trials."
        )
        return result
    uc = max(
        0.0,
        2 * (bernoulli_log_likelihood(count, n, count / n) - bernoulli_log_likelihood(count, n, q)),
    )
    result.update(kupiec_statistic=uc, kupiec_p_value=float(chi2.sf(uc, 1)))
    n00, n01, n10, n11 = [transitions[k] for k in ("n00", "n01", "n10", "n11")]
    if n00 + n01 and n10 + n11:
        alternative = bernoulli_log_likelihood(
            n01, n00 + n01, n01 / (n00 + n01)
        ) + bernoulli_log_likelihood(n11, n10 + n11, n11 / (n10 + n11))
        null = bernoulli_log_likelihood(n01 + n11, n - 1, (n01 + n11) / (n - 1))
        independent = max(0.0, 2 * (alternative - null))
        result.update(
            independence_statistic=independent,
            independence_p_value=float(chi2.sf(independent, 1)),
            conditional_statistic=uc + independent,
            conditional_p_value=float(chi2.sf(uc + independent, 2)),
        )
    else:
        result["warnings"].append(
            "Independence/conditional coverage unavailable: both previous-exception states were not observed."
        )
    if min(n * q, n * (1 - q)) < 5 or min(transitions.values()) < 5:
        result["warnings"].append(
            "Sparse expected violations/transition counts: asymptotic p-values have low power or unreliable calibration."
        )
    result["warnings"].append(
        "A nonsignificant p-value does not establish model correctness; these tests assume a stable nominal exception process."
    )
    return result


def metric_set(points, min_n=100):
    n = len(points)
    losses = (
        variance_losses(
            [p["realized_variance_proxy"] for p in points], [p["forecast_variance"] for p in points]
        )
        if n
        else None
    )
    return {
        "observations": n,
        "qlike": float(losses["qlike"].mean()) if n else None,
        "mse": float(losses["squared_error"].mean()) if n else None,
        "mae": float(losses["absolute_error"].mean()) if n else None,
        "coverage95": coverage_tests([p["exception95"] for p in points], 0.95, min_n),
        "coverage99": coverage_tests([p["exception99"] for p in points], 0.99, min_n),
    }


def paired_uncertainty(ml, baseline, seed=42):
    if len(ml) < 20:
        return {"available": False, "reason": "At least 20 matched losses required."}
    differences = np.asarray(ml) - np.asarray(baseline)
    n = len(differences)
    block = min(10, n)
    rng = np.random.default_rng(seed)
    means = []
    for _ in range(500):
        starts = rng.integers(0, n, size=math.ceil(n / block))
        indices = np.concatenate([(start + np.arange(block)) % n for start in starts])[:n]
        means.append(float(differences[indices].mean()))
    return {
        "available": True,
        "mean_qlike_difference": float(differences.mean()),
        "interval95": np.quantile(means, [0.025, 0.975]).tolist(),
        "block_length": block,
        "resamples": 500,
        "note": "Circular moving-block bootstrap of paired LightGBM-minus-benchmark QLIKE; descriptive sensitivity, not a champion decision or universal significance claim.",
    }
