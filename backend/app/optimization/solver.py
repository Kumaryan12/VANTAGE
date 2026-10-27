"""CVXPY solve plus independent NumPy checks; no broker/database/network dependency."""

import time
from importlib.metadata import version

import cvxpy as cp
import numpy as np

from app.core.errors import AppError
from app.risk.conventions import validate_value, validate_weights
from app.risk.covariance import validated_covariance

from .contracts import FEASIBILITY_TOLERANCE, OptimizationRequest, Residual, SolverResult


def validate_universe(instruments, sectors, current, covariance, request):
    if len(instruments) != len(set(instruments)) or len(instruments) != len(sectors):
        raise AppError("OPTIMIZATION_UNIVERSE", "Unique instruments and sector order must align.")
    if request.asset_order is not None and instruments != request.asset_order:
        raise AppError(
            "ASSET_ORDER", "Explicit asset order differs from the authorized price/holding order."
        )
    weights = validate_weights(current, len(instruments))
    matrix, diagnostics = validated_covariance(covariance)
    if matrix.shape != (len(instruments), len(instruments)):
        raise AppError(
            "COVARIANCE_SHAPE", "Covariance dimension differs from the ordered investable universe."
        )
    c = request.constraints
    asset_keys = (
        set(c.asset_min)
        | set(c.asset_max)
        | set(c.frozen)
        | set(request.costs.asset_rates)
        | set(request.costs.buy_rates)
        | set(request.costs.sell_rates)
    )
    if asset_keys - set(instruments):
        raise AppError(
            "UNKNOWN_OPTIMIZATION_ASSET",
            "Constraints/costs cannot introduce instruments outside the held eligible universe.",
        )
    if (set(c.sector_min) | set(c.sector_max)) - set(sectors):
        raise AppError(
            "UNKNOWN_OPTIMIZATION_SECTOR", "Sector bounds must use existing classifications."
        )
    if "Unknown" in sectors and c.unknown_sector_policy == "reject":
        raise AppError(
            "UNKNOWN_SECTOR",
            "Unknown sector classifications are ineligible under the selected policy.",
        )
    if request.expected_returns and set(request.expected_returns.annual_returns) != set(
        instruments
    ):
        raise AppError(
            "RETURN_ASSUMPTION_COVERAGE",
            "Expected returns must cover exactly every eligible held instrument; no estimates are invented.",
        )
    return weights, matrix, diagnostics


def cost_rates(instruments, costs):
    symmetric = np.array([costs.asset_rates.get(i, costs.proportional_rate) for i in instruments])
    return np.array(
        [costs.buy_rates.get(i, symmetric[j]) for j, i in enumerate(instruments)]
    ), np.array([costs.sell_rates.get(i, symmetric[j]) for j, i in enumerate(instruments)])


def allocation_changes(current, proposed, value, buy, sell):
    delta = np.asarray(proposed) - np.asarray(current)
    gross = float(np.abs(delta).sum())
    fraction = float(buy @ np.maximum(delta, 0) + sell @ np.maximum(-delta, 0))
    return {
        "turnover": 0.5 * gross,
        "gross_weight_change": gross,
        "one_way_notional": value * 0.5 * gross,
        "gross_notional_traded": value * gross,
        "cost_fraction": fraction,
        "cost_inr": value * fraction,
    }


def bounds(instruments, sectors, current, c):
    lower = np.array([max(c.min_weight, c.asset_min.get(i, 0)) for i in instruments])
    upper = np.array([min(c.max_weight, c.asset_max.get(i, 1)) for i in instruments])
    sector_bounds = {
        s: (c.sector_min.get(s, 0), min(c.max_sector_weight or 1, c.sector_max.get(s, 1)))
        for s in sorted(set(sectors))
    }
    issues = []
    if np.any(lower > upper):
        issues.append("Asset lower bounds exceed asset upper bounds.")
    if lower.sum() > 1 + 1e-12:
        issues.append("Sum of asset lower bounds exceeds full investment.")
    if upper.sum() < 1 - 1e-12:
        issues.append("Sum of asset upper bounds is below full investment.")
    for i, instrument in enumerate(instruments):
        if instrument in c.frozen:
            if not lower[i] - 1e-12 <= current[i] <= upper[i] + 1e-12:
                issues.append(f"Frozen weight for {instrument} conflicts with its position bounds.")
            lower[i] = max(lower[i], current[i])
            upper[i] = min(upper[i], current[i])
    for s, (lo, hi) in sector_bounds.items():
        mask = np.array([sector == s for sector in sectors])
        if lo > hi or lower[mask].sum() > hi + 1e-12 or upper[mask].sum() < lo - 1e-12:
            issues.append(f"Sector {s} bounds conflict with position/frozen bounds.")
    if (
        sum(v[0] for v in sector_bounds.values()) > 1 + 1e-12
        or sum(v[1] for v in sector_bounds.values()) < 1 - 1e-12
    ):
        issues.append("Sector bounds cannot reconcile to a fully invested sleeve.")
    required = max(
        float(np.maximum(current - upper, 0).sum()), float(np.maximum(lower - current, 0).sum())
    )
    if c.max_turnover is not None and required > c.max_turnover + FEASIBILITY_TOLERANCE:
        issues.append(
            f"Position/frozen bounds require at least {required:.9g} one-way turnover, above the requested {c.max_turnover:.9g}."
        )
    return lower, upper, sector_bounds, issues


def independent_validation(instruments, sectors, current, weights, matrix, request):
    c = request.constraints
    rows = []

    def check(name, group, value, lower=None, upper=None, units="decimal weight"):
        violation = max(
            0, 0 if lower is None else lower - value, 0 if upper is None else value - upper
        )
        binding = (lower is not None and abs(value - lower) <= FEASIBILITY_TOLERANCE) or (
            upper is not None and abs(value - upper) <= FEASIBILITY_TOLERANCE
        )
        rows.append(
            Residual(
                name=name,
                group=group,
                value=float(value),
                lower=lower,
                upper=upper,
                violation=float(violation),
                binding=binding,
                utilization=float(value / upper) if upper and upper > 0 else None,
                units=units,
            )
        )

    check("Fully invested", "budget", float(weights.sum()), 1, 1)
    for i, name in enumerate(instruments):
        check(
            name,
            "position",
            weights[i],
            max(c.min_weight, c.asset_min.get(name, 0)),
            min(c.max_weight, c.asset_max.get(name, 1)),
        )
        if name in c.frozen:
            check(name, "frozen", weights[i], float(current[i]), float(current[i]))
    for sector in sorted(set(sectors)):
        value = float(weights[np.array([s == sector for s in sectors])].sum())
        check(
            sector,
            "sector",
            value,
            c.sector_min.get(sector, 0),
            min(c.max_sector_weight or 1, c.sector_max.get(sector, 1)),
        )
    turnover = 0.5 * float(np.abs(weights - current).sum())
    if c.max_turnover is not None:
        check("One-way turnover", "turnover", turnover, 0, c.max_turnover)
    if request.objective == "target_risk":
        check(
            "Annual volatility target",
            "risk_target",
            float(np.sqrt(max(0, 252 * weights @ matrix @ weights))),
            0,
            request.target_annual_volatility,
            "decimal annual standard deviation",
        )
    if request.objective == "target_return":
        mu = np.array([request.expected_returns.annual_returns[i] for i in instruments])
        check(
            "Assumed annual return target",
            "return_target",
            float(mu @ weights),
            request.target_annual_return,
            None,
            "assumed decimal annual return",
        )
    return rows


def solve_allocation(
    instruments, sectors, current, covariance, value, request: OptimizationRequest, *, diagnose=True
):
    started = time.monotonic()
    current, matrix, cov_diagnostics = validate_universe(
        instruments, sectors, current, covariance, request
    )
    value = validate_value(value)
    lower, upper, sector_bounds, issues = bounds(instruments, sectors, current, request.constraints)
    settings = {
        "name": "CLARABEL",
        "version": version("clarabel"),
        "cvxpy_version": cp.__version__,
        "max_iter": request.solver.max_iter,
        "time_limit_seconds": request.solver.time_limit_seconds,
        "tolerance": request.solver.tolerance,
        "feasibility_tolerance": FEASIBILITY_TOLERANCE,
        "max_threads": 1,
        "variance_units": "annual decimal return squared",
        "objective_units": "annual variance plus coefficients times dimensionless turnover/cost fractions",
    }

    def outcome(
        status,
        *,
        weights=None,
        raw=None,
        annual=None,
        objective=None,
        residuals=None,
        validation=None,
        messages=None,
        changes=None,
        expected=None,
    ):
        return SolverResult(
            status=status,
            feasible=weights is not None,
            weights=None if weights is None else weights.tolist(),
            raw_weights=None if raw is None else raw.tolist(),
            annual_variance=annual,
            annual_volatility=None if annual is None else float(np.sqrt(max(annual, 0))),
            objective_value=objective,
            residuals=residuals or [],
            diagnostics=messages or [],
            solver={**settings, "wall_seconds": time.monotonic() - started},
            validation={"covariance": cov_diagnostics, **(validation or {})},
            expected_annual_return=expected,
            **(
                changes
                or dict.fromkeys(
                    (
                        "turnover",
                        "gross_weight_change",
                        "one_way_notional",
                        "gross_notional_traded",
                        "cost_fraction",
                        "cost_inr",
                    )
                )
            ),
        )

    if issues:
        return outcome(
            "infeasible",
            messages=issues,
            validation={"precheck": "necessary bound checks failed; no constraints changed"},
        )
    w = cp.Variable(len(current))
    annual_matrix = 252 * matrix
    scale = max(float(np.trace(annual_matrix) / len(current)), 1e-12)
    annual = cp.quad_form(w, cp.psd_wrap(annual_matrix))
    buy, sell = cost_rates(instruments, request.costs)
    turnover = 0.5 * cp.norm1(w - current)
    cost = buy @ cp.pos(w - current) + sell @ cp.pos(current - w)
    constraints = [cp.sum(w) == 1, w >= lower, w <= upper]
    for sector, (lo, hi) in sector_bounds.items():
        exposure = cp.sum(w[np.array([s == sector for s in sectors])])
        constraints.extend([exposure >= lo, exposure <= hi])
    if request.constraints.max_turnover is not None:
        constraints.append(turnover <= request.constraints.max_turnover)
    if request.objective == "target_risk":
        constraints.append(annual <= request.target_annual_volatility**2)
    mu = None
    if request.expected_returns:
        mu = np.array([request.expected_returns.annual_returns[i] for i in instruments])
    if request.objective == "target_return":
        constraints.append(mu @ w >= request.target_annual_return)
    expression = annual
    if request.objective == "risk_turnover":
        expression += request.lambda_turnover * turnover
    if request.objective == "risk_cost":
        expression += request.lambda_cost * cost
    problem = cp.Problem(cp.Minimize(expression / scale), constraints)
    try:
        problem.solve(
            solver=cp.CLARABEL,
            max_iter=request.solver.max_iter,
            time_limit=request.solver.time_limit_seconds,
            tol_gap_abs=request.solver.tolerance,
            tol_gap_rel=request.solver.tolerance,
            tol_feas=request.solver.tolerance,
            max_threads=1,
            verbose=False,
        )
    except TimeoutError:
        return outcome(
            "timeout",
            messages=["Solver exceeded its execution deadline; no proposed allocation published."],
        )
    except cp.error.SolverError:
        return outcome(
            "solver_failure",
            messages=[
                "CLARABEL could not produce a supported result; no fallback solver or constraint relaxation used."
            ],
        )
    stats = problem.solver_stats
    settings.update(
        reported_status=problem.status,
        iterations=stats.num_iters,
        solve_seconds=stats.solve_time,
        common_positive_objective_scale=scale,
    )
    if problem.status in (cp.INFEASIBLE, cp.INFEASIBLE_INACCURATE):
        messages = [
            "No allocation satisfies the requested constraint system; no constraints were relaxed."
        ]
        if problem.status == cp.INFEASIBLE_INACCURATE:
            messages.append(
                "Solver infeasibility certificate is inaccurate; independent review is required."
            )
        if diagnose and request.objective == "target_risk":
            alternative = request.model_copy(update={"objective": "min_variance"})
            minimum = solve_allocation(
                instruments, sectors, current, matrix, value, alternative, diagnose=False
            )
            if minimum.feasible:
                messages.append(
                    f"Diagnostic without the risk cap: minimum achievable annual volatility is {minimum.annual_volatility:.9g}; requested target is {request.target_annual_volatility:.9g}. The original request remains infeasible."
                )
        elif diagnose and request.constraints.max_turnover is not None:
            # Rebuild explicitly to ensure only the turnover cap is omitted.
            base = [cp.sum(w) == 1, w >= lower, w <= upper]
            for sector, (lo, hi) in sector_bounds.items():
                v = cp.sum(w[np.array([s == sector for s in sectors])])
                base += [v >= lo, v <= hi]
            if request.objective == "target_return":
                base.append(mu @ w >= request.target_annual_return)
            diagnostic = cp.Problem(cp.Minimize(0.5 * cp.norm1(w - current)), base)
            try:
                diagnostic.solve(
                    solver=cp.CLARABEL,
                    max_iter=300,
                    time_limit=min(2, request.solver.time_limit_seconds),
                    verbose=False,
                )
                if diagnostic.status == cp.OPTIMAL:
                    messages.append(
                        f"Diagnostic with only the turnover cap omitted: minimum required one-way turnover is {float(diagnostic.value):.9g}. No diagnostic weights are published as feasible for your original request."
                    )
                else:
                    messages.append(
                        "Position, sector, frozen or return constraints conflict even without the turnover cap; no minimal conflicting set is claimed."
                    )
            except cp.error.SolverError:
                messages.append("Additional feasibility diagnosis unavailable.")
        return outcome("infeasible", messages=messages)
    if problem.status in (cp.UNBOUNDED, cp.UNBOUNDED_INACCURATE):
        return outcome(
            "unbounded",
            messages=[
                "Unexpected unbounded result for a fully invested bounded problem; no allocation published."
            ],
        )
    if problem.status == cp.USER_LIMIT:
        return outcome(
            "iteration_limit" if (stats.num_iters or 0) >= request.solver.max_iter else "timeout",
            messages=[
                "Solver stopped at a configured iteration/time limit; no optimal allocation claimed."
            ],
        )
    if (
        problem.status not in (cp.OPTIMAL, cp.OPTIMAL_INACCURATE)
        or w.value is None
        or problem.value is None
        or not np.isfinite(problem.value)
    ):
        return outcome(
            "solver_failure",
            messages=["Solver did not report a finite supported objective/solution."],
        )
    raw = np.asarray(w.value, dtype=float).reshape(-1)
    if not np.isfinite(raw).all() or (raw < -1e-8).any() or raw.sum() <= 0:
        return outcome(
            "validation_failed",
            raw=raw if np.isfinite(raw).all() else None,
            messages=["Solver weights failed independent finite/nonnegative validation."],
        )
    normalized = np.maximum(raw, 0)
    normalized /= normalized.sum()
    adjustment = float(np.max(np.abs(normalized - raw)))
    residuals = independent_validation(instruments, sectors, current, normalized, matrix, request)
    raw_residuals = independent_validation(instruments, sectors, current, raw, matrix, request)
    maximum = max(r.violation for r in residuals)
    if (
        adjustment > 1e-8
        or maximum > FEASIBILITY_TOLERANCE
        or max(r.violation for r in raw_residuals) > FEASIBILITY_TOLERANCE
    ):
        return outcome(
            "validation_failed",
            raw=raw,
            residuals=residuals,
            validation={"maximum_violation": maximum, "canonicalization_max_change": adjustment},
            messages=[
                "Independent residual/canonicalization checks failed. Constraints were not weakened."
            ],
        )
    changes = allocation_changes(current, normalized, value, buy, sell)
    annual_value = max(float(normalized @ annual_matrix @ normalized), 0)
    objective = annual_value + (
        request.lambda_turnover * changes["turnover"]
        if request.objective == "risk_turnover"
        else request.lambda_cost * changes["cost_fraction"]
        if request.objective == "risk_cost"
        else 0
    )
    objective_error = abs(objective - float(problem.value) * scale)
    if objective_error > 1e-7 * max(1, abs(objective)):
        return outcome(
            "validation_failed",
            raw=raw,
            messages=["Reconstructed normalized objective differs from solver expression."],
        )
    messages = [
        "Continuous equity-sleeve weights are research allocations, not executable orders; quantities, cash, fees and market impact are not verified."
    ]
    if adjustment:
        messages.append(
            "Recorded tiny numerical nonnegativity/sum canonicalization; all original constraints were rechecked."
        )
    if cov_diagnostics["singular"]:
        messages.append(
            "Singular covariance can produce nonunique weights; numerical precision is not financial forecast precision."
        )
    if problem.status == cp.OPTIMAL_INACCURATE:
        messages.append(
            "Solver reported optimal_inaccurate. Feasibility checks passed, but optimality precision is reduced."
        )
    return outcome(
        "optimal" if problem.status == cp.OPTIMAL else "optimal_inaccurate",
        weights=normalized,
        raw=raw,
        annual=annual_value,
        objective=objective,
        residuals=residuals,
        messages=messages,
        changes=changes,
        expected=float(mu @ normalized) if mu is not None else None,
        validation={
            "passed": True,
            "maximum_violation": maximum,
            "canonicalization_max_change": adjustment,
            "objective_reconstruction_error": objective_error,
            "raw_maximum_violation": max(r.violation for r in raw_residuals),
        },
    )
