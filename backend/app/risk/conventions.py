"""Shared one-observation-day, simple-return, positive-loss conventions."""

import math

import numpy as np

from app.core.errors import AppError

TRADING_DAYS = 252
MIN_CONFIDENCE = 0.90
MAX_CONFIDENCE = 0.995


def validate_confidence(confidence: float) -> float:
    if not np.isfinite(confidence) or not MIN_CONFIDENCE <= confidence <= MAX_CONFIDENCE:
        raise AppError(
            "INVALID_CONFIDENCE", "Confidence must be finite and between 0.90 and 0.995."
        )
    return float(confidence)


def minimum_observations(confidence: float) -> int:
    validate_confidence(confidence)
    return max(60, math.ceil(1 / (1 - confidence) - 1e-9))


def finite_vector(values, *, name: str, minimum: int = 1) -> np.ndarray:
    result = np.asarray(values, dtype=float)
    if result.ndim != 1 or len(result) < minimum or not np.isfinite(result).all():
        raise AppError(
            "INVALID_NUMERICAL_INPUT",
            f"{name} must be a finite vector with at least {minimum} values.",
        )
    return result


def validate_weights(weights, assets: int) -> np.ndarray:
    result = finite_vector(weights, name="Weights")
    if (
        result.shape != (assets,)
        or (result < 0).any()
        or not np.isclose(result.sum(), 1, atol=1e-10, rtol=0)
    ):
        raise AppError(
            "INVALID_WEIGHTS", "Long-only weights must align with assets and sum to one."
        )
    return result


def validate_value(value: float) -> float:
    if not np.isfinite(value) or value <= 0:
        raise AppError(
            "INVALID_PORTFOLIO_VALUE", "Portfolio value must be finite and positive INR."
        )
    return float(value)
