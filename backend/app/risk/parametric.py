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
from app.risk.covariance import validated_covariance


def gaussian_risk(
    mean_returns, covariance, weights, portfolio_value: float, confidence: float
) -> dict:
    validate_confidence(confidence)
    value = validate_value(portfolio_value)
    means = finite_vector(mean_returns, name="Expected asset returns")
    matrix, _ = validated_covariance(covariance)
    if matrix.shape != (len(means), len(means)):
        raise AppError(
            "COVARIANCE_SHAPE", "Means and covariance must have the same asset dimension."
        )
    w = validate_weights(weights, len(means))
    mean_return = float(w @ means)
    sigma = float(np.sqrt(max(float(w @ matrix @ w), 0)))
    z = NormalDist().inv_cdf(confidence)
    density = math.exp(-z * z / 2) / math.sqrt(2 * math.pi)
    loss_mean, loss_sigma = -value * mean_return, value * sigma
    return {
        "expected_return": mean_return,
        "daily_volatility": sigma,
        "loss_mean": loss_mean,
        "loss_standard_deviation": loss_sigma,
        "var": loss_mean + loss_sigma * z,
        "expected_shortfall": loss_mean + loss_sigma * density / (1 - confidence),
    }


def volatility_attribution(covariance, weights) -> dict:
    matrix, _ = validated_covariance(covariance)
    w = validate_weights(weights, len(matrix))
    variance = max(float(w @ matrix @ w), 0)
    sigma = float(np.sqrt(variance))
    if sigma == 0:
        return {
            "daily_volatility": 0.0,
            "marginal": [None] * len(w),
            "component": [0.0] * len(w),
            "percentage": [None] * len(w),
            "reconciliation_residual": 0.0,
            "note": "Zero portfolio volatility: marginal and percentage contributions are undefined.",
        }
    marginal = matrix @ w / sigma
    component = w * marginal
    return {
        "daily_volatility": sigma,
        "marginal": marginal.tolist(),
        "component": component.tolist(),
        "percentage": (component / sigma).tolist(),
        "reconciliation_residual": float(component.sum() - sigma),
        "note": "Euler volatility attribution; negative components are valid. These are not VaR contributions.",
    }
