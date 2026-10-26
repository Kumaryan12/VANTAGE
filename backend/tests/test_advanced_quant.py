import math

import numpy as np
import pandas as pd
import pytest

from app.core.errors import AppError
from app.portfolios.normalize import normalize
from app.risk.conventions import minimum_observations
from app.risk.covariance import (
    correlation_matrix,
    estimate_covariance,
    spectral_root,
    validated_covariance,
)
from app.risk.parametric import gaussian_risk, volatility_attribution
from app.risk.simulation import monte_carlo
from app.risk.stress import historical_replay, hypothetical
from app.risk.tails import empirical_tail


@pytest.mark.parametrize(
    "losses,alpha,var,es",
    [
        (list(range(25)), 0.90, 22, 23.2),
        (list(range(20)), 0.925, 18, 56 / 3),
        ([0, 1, 2, 3], 0.95, 3, 3),
        ([1] * 18 + [2, 4], 0.90, 1, 3),
        ([-5] * 25, 0.95, -5, -5),
        ([0] * 25, 0.95, 0, 0),
    ],
)
def test_empirical_quantile_integral(losses, alpha, var, es):
    result = empirical_tail(losses, alpha)
    assert result["var"] == var
    assert result["expected_shortfall"] == pytest.approx(es, abs=1e-12)
    assert result["expected_shortfall"] >= result["var"] - 1e-12


@pytest.mark.parametrize("alpha", [0.89, 0.999, -1, 1, float("nan"), float("inf")])
def test_confidence_rejected(alpha):
    with pytest.raises(AppError):
        empirical_tail([1, 2], alpha)


@pytest.mark.parametrize("losses", [[], [float("nan")], [float("inf")], [[1, 2]]])
def test_invalid_losses(losses):
    with pytest.raises(AppError):
        empirical_tail(losses, 0.95)


def test_tail_sample_policy():
    assert minimum_observations(0.9) == 60
    assert minimum_observations(0.95) == 60
    assert minimum_observations(0.99) == 100
    assert minimum_observations(0.995) == 200


def test_gaussian_known_single_asset():
    result = gaussian_risk([0.001], [[0.0004]], [1], 1_000_000, 0.95)
    # Independently tabulated z95 = 1.6448536269514722; phi(z95)/.05 = 2.0627128075074257.
    assert result["var"] == pytest.approx(31897.07253902944, abs=1e-7)
    assert result["expected_shortfall"] == pytest.approx(40254.25615014851, abs=1e-7)
    assert result["daily_volatility"] == 0.02
    assert result["loss_mean"] == -1000
    assert result["loss_standard_deviation"] == 20000


@pytest.mark.parametrize(
    "covariance,weights,vol",
    [
        ([[0.0004, 0.0004], [0.0004, 0.0004]], [0.5, 0.5], 0.02),
        ([[0.0004, 0], [0, 0.0004]], [0.5, 0.5], 0.02 / math.sqrt(2)),
        ([[0.0004, -0.0004], [-0.0004, 0.0004]], [0.5, 0.5], 0),
        ([[0, 0], [0, 0]], [0.5, 0.5], 0),
        ([[0.0004, 0.0001], [0.0001, 0.0009]], [1, 0], 0.02),
    ],
)
def test_portfolio_covariance_analytical_cases(covariance, weights, vol):
    result = gaussian_risk([0, 0], covariance, weights, 100, 0.95)
    assert result["daily_volatility"] == pytest.approx(vol, abs=1e-14)
    attribution = volatility_attribution(covariance, weights)
    assert sum(attribution["component"]) == pytest.approx(vol, abs=1e-14)
    if vol:
        assert sum(attribution["percentage"]) == pytest.approx(1, abs=1e-13)
    else:
        assert attribution["percentage"] == [None, None]
        assert attribution["marginal"] == [None, None]


def test_zero_volatility_preserves_deterministic_gain():
    result = gaussian_risk([0.01], [[0]], [1], 1000, 0.99)
    assert result["var"] == result["expected_shortfall"] == -10


def test_negative_component_risk_is_valid():
    result = volatility_attribution([[0.04, -0.006], [-0.006, 0.0025]], [0.1, 0.9])
    assert result["component"][0] < 0
    assert sum(result["component"]) == pytest.approx(result["daily_volatility"], abs=1e-14)
    assert result["reconciliation_residual"] == pytest.approx(0, abs=1e-14)


@pytest.mark.parametrize(
    "covariance", [[[1, 2], [0, 1]], [[1, 2], [2, 1]], [[float("nan")]], [[1, 2]], []]
)
def test_invalid_covariance_rejected(covariance):
    with pytest.raises(AppError):
        validated_covariance(covariance)


def test_roundoff_correction_and_singular_sampling_are_recorded():
    matrix, metadata = validated_covariance([[1, 1 + 1e-12], [1 + 1e-12, 1]])
    assert metadata["negative_eigenvalues_clipped"] == 1
    assert metadata["correction_frobenius_norm"] > 0
    assert metadata["singular"]
    root = spectral_root(matrix)
    np.testing.assert_allclose(root @ root.T, matrix, atol=2e-15, rtol=2e-15)


def test_sample_covariance_and_explicit_shrinkage():
    values = np.array([[-0.01, 0.01], [0, 0], [0.01, -0.01]])
    sample, metadata = estimate_covariance(values)
    np.testing.assert_allclose(sample, [[0.0001, -0.0001], [-0.0001, 0.0001]], atol=1e-18)
    assert metadata["method"] == "sample" and metadata["singular"]
    shrunk, metadata = estimate_covariance(values, 0.2)
    np.testing.assert_allclose(shrunk, [[0.0001, -0.00008], [-0.00008, 0.0001]], atol=1e-18)
    assert metadata["shrinkage"] == 0.2
    assert not metadata["singular"]
    assert metadata["shrinkage_change_frobenius_norm"] > 0
    assert correlation_matrix([[0]]) == [[None]]


@pytest.mark.parametrize("weights", [[0.5], [-0.1, 1.1], [0.2, 0.2], [float("nan"), 1]])
def test_invalid_weights(weights):
    with pytest.raises(AppError):
        gaussian_risk([0, 0], [[1, 0], [0, 1]], weights, 100, 0.95)


def test_monte_carlo_reproducible_and_converges_to_correlated_gaussian():
    matrix = [[0.0004, 0.00036], [0.00036, 0.0004]]
    expected = gaussian_risk([0.001, 0.0005], matrix, [0.3, 0.7], 1_000_000, 0.99)
    a = monte_carlo([0.001, 0.0005], matrix, [0.3, 0.7], 1_000_000, 0.99, 100_000, 2026)
    b = monte_carlo([0.001, 0.0005], matrix, [0.3, 0.7], 1_000_000, 0.99, 100_000, 2026)
    assert a == b
    # Six asymptotic Monte Carlo SEs: statistical, scale-aware tolerance, not arbitrary percent.
    assert abs(a["var"] - expected["var"]) <= 6 * a["var_standard_error"]
    assert (
        abs(a["expected_shortfall"] - expected["expected_shortfall"]) <= 6 * a["es_standard_error"]
    )
    assert sum(bin["count"] for bin in a["histogram"]) == 100_000
    assert sum(bin["tail_count"] for bin in a["histogram"]) >= 1000
    assert a["value_quantiles"]["p50"] == pytest.approx(1_000_000 + a["pnl_quantiles"]["p50"])


def test_mc_zero_and_singular_covariance():
    zero = monte_carlo([0.01], [[0]], [1], 1000, 0.95, 2000, 1)
    assert zero["var"] == zero["expected_shortfall"] == -10
    assert zero["var_standard_error"] == zero["es_standard_error"] == 0
    hedged = monte_carlo(
        [0, 0], [[0.0004, -0.0004], [-0.0004, 0.0004]], [0.5, 0.5], 1000, 0.95, 2000, 1
    )
    assert hedged["var"] == pytest.approx(0, abs=1e-12)


@pytest.mark.parametrize(
    "simulations,seed", [(0, 1), (100_001, 1), (2000, -1), (2000, 2**32), (2000, True)]
)
def test_mc_invalid_parameters(simulations, seed):
    with pytest.raises(AppError):
        monte_carlo([0], [[1]], [1], 100, 0.95, simulations, seed)


@pytest.fixture
def small_portfolio():
    from datetime import UTC, datetime

    return normalize(
        [
            {
                "instrument": "NSE:A",
                "name": "A",
                "sector": "Technology",
                "quantity": 2,
                "last_price": 100,
                "average_price": 100,
            },
            {
                "instrument": "NSE:B",
                "name": "B",
                "sector": "Banks",
                "quantity": 3,
                "last_price": 200,
                "average_price": 200,
            },
        ],
        mode="demo",
        source="Synthetic numerical test",
        as_of="2026-01-05",
        retrieved_at=datetime(2026, 1, 5, tzinfo=UTC),
    )


def test_hypothetical_precedence_and_pnl_reconciliation(small_portfolio):
    result = hypothetical(small_portfolio, -0.1, {"Technology": -0.2}, {"NSE:B": 0.05})
    assert [a["pnl"] for a in result["assets"]] == [-40, 30]
    assert result["pnl"] == -10
    assert result["value_before"] == 800
    assert result["value_after"] == 790
    assert result["portfolio_return"] == pytest.approx(-0.0125)
    assert result["pnl_reconciliation_residual"] == 0
    assert result["largest_loss_contributors"] == ["NSE:A"]


def test_buy_and_hold_replay_matches_endpoint_weights(small_portfolio):
    prices = pd.DataFrame(
        {"NSE:A": [100, 90, 80], "NSE:B": [200, 190, 180]},
        index=pd.to_datetime(["2026-01-01", "2026-01-02", "2026-01-05"]),
    )
    result = historical_replay(small_portfolio, prices, "2026-01-01", "2026-01-05")
    assert result["pnl"] == pytest.approx(-100)
    assert result["portfolio_return"] == pytest.approx(-0.125)
    assert result["path"][-1]["value"] == pytest.approx(700)
    assert sum(a["pnl"] for a in result["assets"]) == pytest.approx(result["pnl"])
    assert sum(s["pnl"] for s in result["sectors"]) == pytest.approx(result["pnl"])
    with pytest.raises(AppError, match="Exact scenario"):
        historical_replay(small_portfolio, prices, "2026-01-03", "2026-01-05")
    with pytest.raises(AppError):
        historical_replay(small_portfolio, prices, "2026-01-05", "2026-01-01")


@pytest.mark.parametrize(
    "market,sectors,securities",
    [
        (None, {}, {}),
        (-1.1, {}, {}),
        (0.1, {"Unknown": -0.2}, {}),
        (0.1, {}, {"NSE:MISSING": -0.2}),
        (float("nan"), {}, {}),
    ],
)
def test_invalid_shock_targets_or_values(small_portfolio, market, sectors, securities):
    with pytest.raises(AppError):
        hypothetical(small_portfolio, market, sectors, securities)
