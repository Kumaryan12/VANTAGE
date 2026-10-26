"""Seeded correlated one-day Gaussian simulation; no matrices are persisted."""

import math
from statistics import NormalDist

import numpy as np

from app.core.errors import AppError
from app.risk.conventions import (
    finite_vector,
    validate_confidence,
    validate_value,
    validate_weights,
)
from app.risk.covariance import spectral_root, validated_covariance
from app.risk.tails import empirical_tail


def monte_carlo(
    mean_returns,
    covariance,
    weights,
    portfolio_value: float,
    confidence: float,
    simulations: int = 10_000,
    seed: int = 42,
) -> dict:
    validate_confidence(confidence)
    value = validate_value(portfolio_value)
    means = finite_vector(mean_returns, name="Expected asset returns")
    matrix, _ = validated_covariance(covariance)
    if matrix.shape != (len(means), len(means)):
        raise AppError("COVARIANCE_SHAPE", "Means and covariance must align.")
    w = validate_weights(weights, len(means))
    if (
        isinstance(simulations, bool)
        or not isinstance(simulations, int)
        or not 2000 <= simulations <= 100_000
    ):
        raise AppError(
            "SIMULATION_COUNT", "Simulation count must be an integer from 2,000 to 100,000."
        )
    if isinstance(seed, bool) or not isinstance(seed, int) or not 0 <= seed <= 2**32 - 1:
        raise AppError("SIMULATION_SEED", "Seed must be an unsigned 32-bit integer.")
    if simulations * len(means) > 5_000_000:
        raise AppError(
            "SIMULATION_CAPACITY", "Simulation request exceeds the five-million asset-draw limit."
        )
    root = spectral_root(matrix)
    rng = np.random.Generator(np.random.PCG64(seed))
    draws = rng.standard_normal((simulations, len(means))) @ root.T
    draws += means
    portfolio_returns = draws @ w
    pnl = value * portfolio_returns
    losses = -pnl
    tail = empirical_tail(losses, confidence)
    sigma_loss = value * math.sqrt(max(float(w @ matrix @ w), 0))
    z = NormalDist().inv_cdf(confidence)
    phi = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    q = 1 - confidence
    var_se = sigma_loss * math.sqrt(confidence * q / simulations) / phi
    es_variance = ((1 + z * z) * q - z * phi) / (q * q) - (phi / q - z) ** 2
    es_se = sigma_loss * math.sqrt(max(es_variance, 0) / simulations)
    counts, edges = np.histogram(pnl, bins=60)
    tail_counts, _ = np.histogram(pnl[pnl <= -tail["var"]], bins=edges)
    quantiles = [0.01, 0.05, 0.5, 0.95, 0.99]
    return {
        **tail,
        "simulations": simulations,
        "seed": seed,
        "sampling_method": "eigh_psd_square_root",
        "bit_generator": "PCG64",
        "mean_pnl": float(pnl.mean()),
        "pnl_standard_deviation": float(pnl.std(ddof=1)),
        "pnl_quantiles": dict(
            zip(
                ["p01", "p05", "p50", "p95", "p99"],
                np.quantile(pnl, quantiles).tolist(),
                strict=True,
            )
        ),
        "value_quantiles": dict(
            zip(
                ["p01", "p05", "p50", "p95", "p99"],
                (value + np.quantile(pnl, quantiles)).tolist(),
                strict=True,
            )
        ),
        "return_quantiles": dict(
            zip(
                ["p01", "p05", "p50", "p95", "p99"],
                np.quantile(portfolio_returns, quantiles).tolist(),
                strict=True,
            )
        ),
        "histogram": [
            {
                "left_pnl": float(edges[i]),
                "right_pnl": float(edges[i + 1]),
                "center_pnl": float((edges[i] + edges[i + 1]) / 2),
                "count": int(count),
                "tail_count": int(tail_counts[i]),
            }
            for i, count in enumerate(counts)
        ],
        "var_standard_error": var_se,
        "es_standard_error": es_se,
        "var_mc_interval_95": [tail["var"] - 1.96 * var_se, tail["var"] + 1.96 * var_se],
        "es_mc_interval_95": [
            tail["expected_shortfall"] - 1.96 * es_se,
            tail["expected_shortfall"] + 1.96 * es_se,
        ],
        "nonpositive_value_count": int(np.count_nonzero(value + pnl <= 0)),
        "asset_returns_below_minus_one": int(np.count_nonzero(draws < -1)),
        "uncertainty_note": "Asymptotic Monte Carlo sampling error conditional on the fitted Gaussian; excludes parameter uncertainty and model risk.",
        "assumptions": [
            "One-day multivariate Gaussian simple returns with historical means and full covariance.",
            "Unbounded Gaussian tails can imply asset returns below -100%; no clipping or replacement occurs.",
            "Histogram highlights realized P&L at or below the negative VaR cutoff; ES uses fractional empirical tail mass.",
        ],
    }
