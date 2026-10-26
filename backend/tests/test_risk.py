import hashlib
from datetime import UTC, datetime

import numpy as np
import pandas as pd
import pytest

from app.brokers.demo import DemoBroker, demo_history
from app.core.config import ROOT
from app.core.errors import AppError
from app.portfolios.normalize import normalize
from app.risk.engine import (
    aligned_prices,
    annualized_volatility,
    calculate,
    historical_var,
    scenario_path,
)


def test_valuation_and_exposures_known_case():
    rows = [
        {
            "instrument": "NSE:A",
            "name": "A",
            "sector": "Technology",
            "quantity": 2,
            "last_price": 100,
            "average_price": 80,
        },
        {
            "instrument": "NSE:B",
            "name": "B",
            "sector": "Banks",
            "quantity": 3,
            "last_price": 200,
            "average_price": 180,
        },
    ]
    p = normalize(
        rows, mode="demo", source="test", as_of="2026-01-01", retrieved_at=datetime.now(UTC)
    )
    assert p.total_value == 800
    assert p.total_cost == 700
    assert p.unrealized_pnl == 100
    assert [h.weight for h in p.holdings] == [0.25, 0.75]
    assert p.hhi == 0.625
    assert p.sectors == {"Technology": 0.25, "Banks": 0.75}


def test_volatility_independent_three_point_case():
    # Mean 0; squared deviations sum .0002; sample variance .0001.
    assert annualized_volatility(np.array([-0.01, 0, 0.01])) == pytest.approx(0.01 * (252**0.5))


def test_var_empirical_order_statistics_and_ties():
    # 1..100 percent losses: inverse ECDF at 95% selects 95th loss.
    assert historical_var(-np.arange(1, 101) / 100, 0.95) == 0.95
    assert historical_var(-np.arange(1, 101) / 100, 0.99) == 0.99
    assert historical_var(np.array([-0.02] * 100), 0.95) == 0.02
    assert historical_var(np.array([0.01] * 100), 0.95) == -0.01


def test_drawdown_includes_initial_wealth():
    index, drawdown = scenario_path(np.array([-0.2, 0.25, -0.1]))
    assert index.tolist() == pytest.approx([100, 80, 100, 90])
    assert -drawdown.min() == pytest.approx(0.2)


def test_aligned_returns_covariance_and_constant_weight_case():
    # Opposite per-security returns cancel exactly with equal current weights.
    a = np.tile([0.01, -0.01], 50)
    b = -a
    prices = pd.DataFrame(
        {
            "NSE:A": np.r_[100, 100 * np.cumprod(1 + a)],
            "NSE:B": np.r_[100, 100 * np.cumprod(1 + b)],
        },
        index=pd.bdate_range("2025-01-01", periods=101),
    )
    result = calculate(prices, np.array([0.5, 0.5]), 0.99, 100)
    assert result["annualized_volatility"] == pytest.approx(0, abs=1e-13)
    assert result["historical_var"] == pytest.approx(0, abs=1e-13)
    assert result["correlation"][0][1] == pytest.approx(-1)
    assert result["covariance"][0][0] == pytest.approx(0.01**2 * 100 / 99)
    assert result["covariance"][0][1] == pytest.approx(-(0.01**2) * 100 / 99)
    assert result["series"][-1]["scenario_index"] == pytest.approx(100)
    assert result["series"][20]["rolling_volatility"] is None
    assert result["series"][21]["rolling_volatility"] is not None


def test_zero_volatility_correlation_is_null():
    prices = pd.DataFrame({"NSE:A": [100.0] * 101}, index=pd.bdate_range("2025-01-01", periods=101))
    result = calculate(prices, np.array([1.0]), 0.95, 100)
    assert result["correlation"] == [[None]]
    assert result["annualized_volatility"] == 0


@pytest.mark.parametrize(
    "change,code",
    [
        ("missing", "MISSING_COVERAGE"),
        ("date_gap", "UNALIGNED_HISTORY"),
        ("duplicate", "DUPLICATE_OBSERVATION"),
        ("zero", "UNALIGNED_HISTORY"),
    ],
)
def test_coverage_validation(change, code):
    frame = pd.DataFrame(
        {
            "date": ["2025-01-01", "2025-01-02"] * 2,
            "instrument": ["NSE:A"] * 2 + ["NSE:B"] * 2,
            "close": [100.0, 101.0, 100.0, 102.0],
        }
    )
    if change == "missing":
        frame = frame[frame.instrument == "NSE:A"]
    elif change == "date_gap":
        frame = frame.iloc[:-1]
    elif change == "duplicate":
        frame = pd.concat([frame, frame.iloc[:1]])
    else:
        frame.loc[0, "close"] = 0
    with pytest.raises(AppError) as error:
        aligned_prices(frame, ["NSE:A", "NSE:B"])
    assert error.value.code == code


@pytest.mark.parametrize("returns", [[float("nan"), 0], [float("inf"), 0], []])
def test_invalid_returns_rejected(returns):
    with pytest.raises(AppError):
        historical_var(np.array(returns), 0.95)


def test_insufficient_and_invalid_weights():
    prices = pd.DataFrame({"NSE:A": [100.0] * 61}, index=pd.bdate_range("2025-01-01", periods=61))
    with pytest.raises(AppError, match="100 aligned"):
        calculate(prices, np.array([1.0]), 0.99, 100)
    with pytest.raises(AppError, match="sum to one"):
        calculate(prices, np.array([0.5]), 0.95, 60)
    with pytest.raises(AppError):
        historical_var(np.array([0.01]), 0.90)


def test_demo_is_repeatable_and_hash_matches_fixture():
    p = DemoBroker().portfolio()
    again = DemoBroker().portfolio()
    assert p == again
    assert p.synthetic
    frame, provenance = demo_history()
    assert len(frame) == 505 * 6
    assert (
        provenance.content_hash
        == hashlib.sha256((ROOT / "data/sample/prices.csv").read_bytes()).hexdigest()
    )
    for h in p.holdings:
        assert frame.loc[frame.instrument == h.instrument].iloc[-1].close == pytest.approx(
            h.last_price
        )
