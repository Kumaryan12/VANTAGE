import numpy as np
import pytest
from pydantic import ValidationError

from app.core.errors import AppError
from app.optimization.contracts import (
    AllocationConstraints,
    CostAssumptions,
    OptimizationRequest,
    ReturnAssumptions,
)
from app.optimization.solver import allocation_changes, independent_validation, solve_allocation


def request(**kwargs):
    return OptimizationRequest(
        constraints=AllocationConstraints(max_weight=1, max_turnover=None), **kwargs
    )


def run(matrix, current=None, parameters=None, sectors=None):
    n = len(matrix)
    return solve_allocation(
        [f"A{i}" for i in range(n)],
        sectors or ["Sector"] * n,
        current or [1 / n] * n,
        matrix,
        1_000_000,
        parameters or request(),
    )


@pytest.mark.parametrize(
    "matrix,expected",
    [
        ([[0.0004]], [1]),
        ([[0.0004, 0], [0, 0.0009]], [9 / 13, 4 / 13]),
        ([[0.0004, 0.0001], [0.0001, 0.0009]], [8 / 11, 3 / 11]),
        (np.eye(3) * 0.0004, [1 / 3] * 3),
        ([[1e-14, 0], [0, 0.0004]], [1, 0]),
    ],
)
def test_analytical_minimum_variance_solutions(matrix, expected):
    result = run(matrix)
    assert result.status == "optimal" and result.validation["passed"], result
    np.testing.assert_allclose(result.weights, expected, atol=3e-5, rtol=0)
    assert result.annual_variance == pytest.approx(
        252 * np.array(result.weights) @ np.array(matrix) @ np.array(result.weights), abs=1e-14
    )
    assert abs(sum(result.weights) - 1) < 1e-12
    assert max(row.violation for row in result.residuals) <= 1e-7
    assert result.solver["name"] == "CLARABEL" and result.solver["version"]


@pytest.mark.parametrize(
    "matrix", [np.ones((3, 3)) * 0.0001, np.zeros((3, 3)), [[0.0001, 0.0002], [0.0002, 0.0004]]]
)
def test_singular_and_perfectly_correlated_covariance(matrix):
    result = run(matrix)
    assert result.feasible, result
    assert result.validation["covariance"]["singular"]
    assert result.annual_variance >= 0
    if np.all(np.asarray(matrix) == 0.0001):
        assert result.annual_variance == pytest.approx(0.0252)


def test_position_sector_frozen_and_turnover_constraints():
    constraints = AllocationConstraints(
        max_weight=0.7,
        asset_min={"A0": 0.1},
        asset_max={"A2": 0.6},
        frozen=["A0"],
        sector_max={"Tech": 0.45},
        sector_min={"Other": 0.55},
        max_turnover=0.15,
    )
    result = run(
        np.diag([0.0009, 0.0004, 0.0001]),
        [0.2, 0.3, 0.5],
        OptimizationRequest(constraints=constraints),
        ["Tech", "Tech", "Other"],
    )
    assert result.feasible, result
    assert result.weights[0] == pytest.approx(0.2, abs=1e-7)
    assert sum(result.weights[:2]) <= 0.45 + 1e-7
    assert result.turnover <= 0.15 + 1e-7
    fixed = run(
        np.diag([0.0009, 0.0001]),
        [0.8, 0.2],
        OptimizationRequest(constraints=AllocationConstraints(max_weight=1, max_turnover=0)),
    )
    np.testing.assert_allclose(fixed.weights, [0.8, 0.2], atol=1e-7, rtol=0)


@pytest.mark.parametrize(
    "constraints",
    [
        AllocationConstraints(max_weight=0.2, max_turnover=None),
        AllocationConstraints(min_weight=0.6, max_weight=1, max_turnover=None),
        AllocationConstraints(max_weight=0.4, frozen=["A0"], max_turnover=None),
        AllocationConstraints(max_weight=1, sector_max={"Sector": 0.9}, max_turnover=None),
        AllocationConstraints(max_weight=0.55, max_turnover=0.01),
    ],
)
def test_infeasibility_is_not_a_fake_allocation(constraints):
    result = run(
        np.diag([0.0004, 0.0001]), [0.8, 0.2], OptimizationRequest(constraints=constraints)
    )
    assert result.status == "infeasible" and not result.feasible
    assert result.weights is None and result.annual_variance is None
    assert result.diagnostics


def test_cost_conventions_and_penalties():
    changes = allocation_changes(
        np.array([0.6, 0.4]),
        np.array([0.4, 0.6]),
        1_000_000,
        np.array([0.002, 0.003]),
        np.array([0.004, 0.005]),
    )
    assert changes["turnover"] == pytest.approx(0.2)
    assert changes["gross_weight_change"] == pytest.approx(0.4)
    assert changes["one_way_notional"] == pytest.approx(200000)
    assert changes["gross_notional_traded"] == pytest.approx(400000)
    assert changes["cost_fraction"] == pytest.approx(0.0014)
    assert changes["cost_inr"] == pytest.approx(1400)
    base = run(np.diag([0.0004, 0.0001]), [0.5, 0.5])
    turnover = run(
        np.diag([0.0004, 0.0001]),
        [0.5, 0.5],
        request(objective="risk_turnover", lambda_turnover=10),
    )
    cost = run(
        np.diag([0.0004, 0.0001]),
        [0.5, 0.5],
        request(
            objective="risk_cost", lambda_cost=100, costs=CostAssumptions(proportional_rate=0.01)
        ),
    )
    assert base.turnover > 0.2
    assert turnover.turnover < 1e-6 and cost.turnover < 1e-6
    assert cost.cost_inr < 0.1


def test_target_risk_and_explicit_return_assumptions():
    impossible = run(
        np.diag([0.0001, 0.0004]),
        parameters=request(objective="target_risk", target_annual_volatility=0.01),
    )
    assert impossible.status == "infeasible" and any(
        "minimum achievable" in s for s in impossible.diagnostics
    )
    feasible = run(
        np.diag([0.0001, 0.0004]),
        parameters=request(objective="target_risk", target_annual_volatility=0.2),
    )
    assert feasible.feasible and feasible.annual_volatility <= 0.2
    assumed = ReturnAssumptions(
        annual_returns={"A0": 0.05, "A1": 0.2},
        source="Explicit synthetic annual assumptions for an analytical contract test.",
    )
    target = run(
        np.diag([0.0001, 0.0004]),
        parameters=request(
            objective="target_return", expected_returns=assumed, target_annual_return=0.15
        ),
    )
    assert target.feasible and target.expected_annual_return >= 0.15 - 1e-7
    with pytest.raises(ValidationError):
        request(objective="target_return")


def test_invalid_mapping_covariance_bounds_and_independent_rejection():
    with pytest.raises(AppError):
        run([[1, 2], [2, 1]])
    with pytest.raises(AppError):
        run([[1, 0.2], [0.1, 1]])
    with pytest.raises(AppError):
        run(np.eye(2), parameters=request(asset_order=["A1", "A0"]))
    with pytest.raises(AppError):
        run(
            np.eye(2),
            parameters=OptimizationRequest(
                constraints=AllocationConstraints(asset_max={"NEW": 0.5})
            ),
        )
    with pytest.raises(AppError):
        run(
            np.eye(2),
            sectors=["Unknown", "Known"],
            parameters=OptimizationRequest(
                constraints=AllocationConstraints(unknown_sector_policy="reject")
            ),
        )
    rows = independent_validation(
        ["A0", "A1"],
        ["Tech", "Other"],
        np.array([0.5, 0.5]),
        np.array([1.1, -0.1]),
        np.eye(2),
        request(),
    )
    assert max(r.violation for r in rows) > 0.09
    with pytest.raises(ValidationError):
        AllocationConstraints(min_weight=0.5, max_weight=0.4)
    with pytest.raises(ValidationError):
        CostAssumptions(asset_rates={"A0": float("nan")})
