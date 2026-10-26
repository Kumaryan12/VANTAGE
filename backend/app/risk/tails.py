"""Inverse empirical CDF VaR and quantile-integral Expected Shortfall."""

import math

import numpy as np

from app.risk.conventions import finite_vector, validate_confidence


def empirical_tail(losses, confidence: float) -> dict:
    """Loss units in = risk units out. Each observation has mass 1/n.

    Integrate the worst m = n(1-alpha) observations, with fractional mass on
    the next order statistic. This also handles ties and m < 1 correctly.
    Minimum estimation history is enforced separately at the service boundary.
    """
    validate_confidence(confidence)
    ordered = np.sort(finite_vector(losses, name="Losses"))[::-1]
    mass = len(ordered) * (1 - confidence)
    whole = int(math.floor(mass))
    fraction = mass - whole
    numerator = float(ordered[:whole].sum())
    if fraction > 0:
        numerator += fraction * ordered[whole]
    return {
        "var": float(np.quantile(ordered, confidence, method="inverted_cdf")),
        "expected_shortfall": numerator / mass,
        "tail_sample_mass": mass,
    }
