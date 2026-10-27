"""Pinned hypothetical optimization tools. Models cannot alter constraints or review state."""

import re
from concurrent.futures import TimeoutError

from pydantic import Field
from sqlalchemy import select

from app.core.errors import AppError
from app.database.models import GovernanceModel, OptimizationRun
from app.optimization.contracts import AllocationConstraints, OptimizationRequest
from app.optimization.data import capture, prepare
from app.optimization.service import owned as owned_run
from app.optimization.service import queue
from app.optimization.solver import bounds
from app.risk.artifacts import digest

from .tools import Empty, fact, register, sealed


def requested_goals(question):
    q = question.lower()

    def number(pattern):
        match = re.search(pattern, q)
        return float(match.group(1)) / 100 if match else None

    return {
        "reduction": number(r"reduc\w*.{0,45}volatility\s*(?:by|at least)?\s*(\d+(?:\.\d+)?)\s*%"),
        "turnover": number(
            r"(?:turnover|selling more than|sell more than|selling no more than)[^\d%]{0,30}(\d+(?:\.\d+)?)\s*%"
        ),
        "max_weight": number(
            r"(?:single.stock|position|asset)\s*(?:exposure|weight|cap|limit)?[^\d%]{0,25}(\d+(?:\.\d+)?)\s*%"
        ),
    }


def verify_user_policy(ctx, parameters):
    if re.search(
        r"\b(?:relax|ignore|override)\b.{0,35}\b(?:constraint|bound|turnover|limit|frozen)\b",
        ctx.request.question,
        re.I,
    ):
        raise AppError(
            "OPTIMIZATION_CONSTRAINT_APPROVAL",
            "Constraint relaxation requires the user to select modified settings in the decision laboratory; tools cannot override pinned constraints.",
        )
    goals = requested_goals(ctx.request.question)
    for key, actual in (
        ("turnover", parameters.constraints.max_turnover),
        ("max_weight", parameters.constraints.max_weight),
    ):
        if goals[key] is not None and (actual is None or abs(actual - goals[key]) > 1e-12):
            raise AppError(
                "OPTIMIZATION_PINNED_CONSTRAINT",
                "Question and selected constraints disagree. Edit/select the intended constraints explicitly; no silent relaxation is permitted.",
            )


def selected_run(ctx, ident=None):
    selected = ctx.request.optimization_run_id
    if selected and ident and selected != ident:
        raise AppError("TOOL_SCOPE", "Use only the selected optimization run.", 403)
    ident = selected or ident
    if ident is None:
        row = ctx.db.scalar(
            select(OptimizationRun)
            .where(
                OptimizationRun.owner == ctx.owner,
                OptimizationRun.status.in_(["completed", "partial"]),
                OptimizationRun.dataset["synthetic"].as_boolean().is_(ctx.request.mode == "demo"),
            )
            .order_by(OptimizationRun.created_at.desc())
            .limit(1)
        )
        if row is None:
            raise AppError(
                "OPTIMIZATION_MISSING",
                "No completed optimization is accessible in this session. Run/select one in Portfolio Optimization.",
                404,
            )
        ident = row.id
    row = owned_run(ctx.db, ident, ctx.owner)
    if row.dataset["synthetic"] != (ctx.request.mode == "demo"):
        raise AppError(
            "TOOL_SCOPE", "Optimization source mode differs from the selected investigation.", 403
        )
    if row.result is None:
        raise AppError(
            "OPTIMIZATION_NOT_READY",
            "The selected optimization has no completed solver evidence.",
            409,
        )
    verify_user_policy(
        ctx,
        OptimizationRequest.model_validate(
            row.parameters if row.kind == "single" else row.parameters["base"]
        ),
    )
    return row


def pinned_parameters(ctx):
    goals = requested_goals(ctx.request.question)
    if re.search(
        r"\b(?:relax|ignore|override)\b.{0,35}\b(?:constraint|bound|turnover|limit|frozen)\b",
        ctx.request.question,
        re.I,
    ):
        raise AppError(
            "OPTIMIZATION_CONSTRAINT_APPROVAL",
            "Constraint relaxation requires the user to select modified settings in the decision laboratory; tools cannot override pinned constraints.",
        )
    if ctx.request.optimization_parameters:
        parameters = ctx.request.optimization_parameters
    elif ctx.request.optimization_run_id:
        row = selected_run(ctx)
        parameters = OptimizationRequest.model_validate(
            row.parameters if row.kind == "single" else row.parameters["base"]
        )
    else:
        if re.search(
            r"\b(?:sector|frozen|freeze|asset-specific|asymmetric)\b", ctx.request.question, re.I
        ):
            raise AppError(
                "OPTIMIZATION_SETTINGS_REQUIRED",
                "Select explicit sector, frozen-position or asset-specific policies in Portfolio Optimization and pin the saved run; these settings are not inferred.",
            )
        if any(
            word in ctx.request.question.lower()
            for word in ("expected return", "efficient frontier", "maximize return")
        ):
            raise AppError(
                "EXPECTED_RETURN_ASSUMPTIONS_REQUIRED",
                "Supply a complete sourced return-assumption vector in the decision laboratory. Volatility forecasts are not expected returns.",
            )
        constraints = AllocationConstraints(
            max_weight=goals["max_weight"] if goals["max_weight"] is not None else 1,
            max_turnover=goals["turnover"],
        )
        parameters = OptimizationRequest(
            mode=ctx.request.mode,
            dataset_id=ctx.request.dataset_id,
            confidence=ctx.request.confidence,
            window=ctx.request.window,
            shrinkage=ctx.request.shrinkage,
            constraints=constraints,
        )
    verify_user_policy(ctx, parameters)
    return parameters


class RunInput(Empty):
    run_id: str | None = Field(None, max_length=36)


@register(
    "get_optimization_constraints",
    "Read the user-pinned constraints/costs/objective. No solver choices or constraint relaxation can be supplied by the model.",
    Empty,
)
def constraints(ctx, _):
    parameters = pinned_parameters(ctx)
    facts = [
        fact(
            "opt.constraint.max_weight",
            "Maximum position weight",
            parameters.constraints.max_weight,
            "decimal weight",
            str(ctx.portfolio.as_of),
        ),
        fact(
            "opt.constraint.max_turnover",
            "Maximum one-way turnover",
            parameters.constraints.max_turnover,
            "decimal one-way turnover; null means unconstrained",
            str(ctx.portfolio.as_of),
        ),
    ]
    return sealed(
        "get_optimization_constraints",
        "optimization_configuration",
        ctx.request.optimization_run_id or ctx.snapshot_id,
        ctx.portfolio.synthetic,
        str(ctx.portfolio.as_of),
        {
            "parameters": parameters.model_dump(mode="json"),
            "requested_goals": requested_goals(ctx.request.question),
        },
        facts,
        [
            "Constraints are bound by the server to the user's selected settings or explicit percentages; no model-supplied changes are accepted.",
            "Only the held equity sleeve is optimized; unavailable cash is excluded, not assumed zero.",
        ],
        {"parameters_hash": digest(parameters.model_dump(mode="json"))},
    )


@register(
    "preview_portfolio_optimization",
    "Validate the held universe/source and necessary bound checks; this is not a certificate of joint feasibility.",
    Empty,
)
def preview(ctx, _):
    parameters = pinned_parameters(ctx)
    payload = capture(ctx.db, ctx.portfolio, ctx.owner, parameters)
    _, _, matrix, dataset = prepare(ctx.portfolio, payload, parameters)
    _, _, _, issues = bounds(
        dataset["instruments"],
        dataset["sectors"],
        dataset["current_weights"],
        parameters.constraints,
    )
    return sealed(
        "preview_portfolio_optimization",
        "optimization_preview",
        ctx.snapshot_id,
        ctx.portfolio.synthetic,
        str(ctx.portfolio.as_of),
        {
            "dataset": dataset,
            "precheck_issues": issues,
            "parameters": parameters.model_dump(mode="json"),
        },
        [],
        [
            "Necessary pre-solve checks do not establish full feasibility or optimality; a checked solver result is required.",
            *issues,
        ],
        {"covariance_hash": dataset["covariance_hash"]},
    )


def result_evidence(ctx, row, tool):
    points = row.result["points"]
    point = points[0]
    solution = point["solution"]
    date = point["dataset"]["as_of"]
    facts = []
    comparison = point["comparison"]
    if comparison:
        for key, value, unit in [
            (
                "current_volatility",
                comparison["current"]["annual_volatility"],
                "decimal annual standard deviation",
            ),
            (
                "proposed_volatility",
                comparison["proposed"]["annual_volatility"],
                "decimal annual standard deviation",
            ),
            (
                "volatility_reduction",
                comparison["volatility_reduction_fraction"],
                "fraction of baseline annual volatility",
            ),
            ("turnover", solution["turnover"], "decimal one-way turnover"),
            ("cost", solution["cost_inr"], "INR research cost assumption"),
            (
                "constraint_violation",
                solution["validation"]["maximum_violation"],
                "maximum original-constraint residual",
            ),
        ]:
            facts.append(fact(f"opt.{key}", key.replace("_", " "), value, unit, date))
        target = requested_goals(ctx.request.question)["reduction"]
        if target is not None:
            achieved = comparison["volatility_reduction_fraction"]
            status = (
                "unassessed_zero_baseline"
                if achieved is None
                else "achieved_by_verified_allocation"
                if achieved + 1e-7 >= target
                else "not_reached_at_fitted_minimum_variance"
                if solution["status"] == "optimal"
                and point["parameters"]["objective"] == "min_variance"
                else "not_reached_feasibility_unproven_for_this_objective"
            )
            facts.extend(
                [
                    fact(
                        "opt.requested_reduction",
                        "Requested volatility reduction",
                        target,
                        "fraction of baseline annual volatility",
                        date,
                    ),
                    fact(
                        "opt.goal_status",
                        "Risk-reduction goal assessment",
                        status,
                        "conditional on saved model/constraints; not a forecast",
                        date,
                    ),
                ]
            )
    facts.append(
        fact(
            "opt.solver_status",
            "Recorded solver outcome",
            solution["status"],
            "solver/independent-validation status",
            date,
        )
    )
    for a in point["allocations"]:
        facts.append(
            fact(
                f"opt.weight.{a['instrument']}",
                f"{a['name']} proposed weight",
                a["proposed_weight"],
                "decimal equity-sleeve weight",
                date,
            )
        )
    data = {
        "parameters": point["parameters"],
        "solution": {k: v for k, v in solution.items() if k not in ("raw_weights", "residuals")},
        "binding_constraints": [r for r in solution["residuals"] if r["binding"]][:30],
        "allocations": point["allocations"],
        "study_points": [
            {
                "label": p["label"],
                "changes": p["changes"],
                "status": p["solution"]["status"],
                "annual_volatility": p["solution"]["annual_volatility"],
                "turnover": p["solution"]["turnover"],
                "cost_inr": p["solution"]["cost_inr"],
            }
            for p in points
        ],
        "comparison": {
            side: {
                k: v
                for k, v in comparison[side].items()
                if k not in ("attribution", "simulation_diagnostics")
            }
            for side in ("current", "proposed")
        }
        if comparison
        else None,
    }
    return sealed(
        tool,
        "optimization_run",
        row.id,
        row.dataset["synthetic"],
        date,
        data,
        facts,
        [
            *solution["diagnostics"],
            *row.result["warnings"],
            "In-sample minimum variance is not guaranteed future risk reduction and need not reduce every VaR, ES or stress loss.",
            "Binding constraints reflect a user policy, not proof that a security is financially undesirable.",
            "Costs are research assumptions, continuous allocations are not executable orders, and Unknown sectors remain explicit.",
        ],
        {
            "run_id": row.id,
            "snapshot_id": row.snapshot_id,
            "input_hash": row.input_hash,
            "result_hash": row.result_hash,
            "covariance_hash": point["dataset"]["covariance_hash"],
            "version": row.runtime["optimization_version"],
        },
    )


@register(
    "run_portfolio_optimization",
    "Execute a hypothetical optimization with server-pinned user constraints, or read an explicitly selected saved result. Never modify constraints/holdings or create orders.",
    Empty,
)
def run(ctx, _):
    parameters = pinned_parameters(ctx)
    if ctx.request.optimization_run_id:
        row = selected_run(ctx)
    else:
        submitted = queue.submit(ctx.db, ctx.portfolio, ctx.owner, parameters)
        try:
            queue.futures[submitted.id].result(timeout=7)
        except TimeoutError:
            raise AppError(
                "OPTIMIZATION_PENDING",
                "The saved calculation is still running. Inspect its recorded outcome before claiming any allocation or risk reduction.",
                409,
            ) from None
        ctx.db.expire_all()
        row = owned_run(ctx.db, submitted.id, ctx.owner)
        if row.result is None:
            raise AppError(
                "OPTIMIZATION_FAILED",
                "The calculation has not produced verified solver evidence; no allocation is claimed.",
                409,
            )
    return result_evidence(ctx, row, "run_portfolio_optimization")


@register(
    "get_optimization_result",
    "Read the authorized pinned/latest completed optimization; no recomputation or source substitution.",
    RunInput,
)
def get_result(ctx, body):
    return result_evidence(ctx, selected_run(ctx, body.run_id), "get_optimization_result")


@register(
    "compare_portfolio_allocations",
    "Read the matched current/proposed risk comparison from the selected saved result.",
    RunInput,
)
def allocation_comparison(ctx, body):
    return result_evidence(ctx, selected_run(ctx, body.run_id), "compare_portfolio_allocations")


@register(
    "get_optimization_sensitivity",
    "Read existing labeled sensitivity results. Never change assumptions or generate an unrequested relaxed allocation.",
    RunInput,
)
def sensitivity(ctx, body):
    row = selected_run(ctx, body.run_id)
    if row.kind != "sensitivity":
        raise AppError(
            "OPTIMIZATION_SENSITIVITY_MISSING",
            "Select an accessible sensitivity study from the decision laboratory; no variations are invented.",
        )
    result = result_evidence(ctx, row, "get_optimization_sensitivity")
    payload = result.model_dump(mode="json", exclude={"checksum"})
    for index, point in enumerate(row.result["points"]):
        payload["facts"].append(
            fact(
                f"opt.sensitivity.{index}.volatility",
                point["label"],
                point["solution"]["annual_volatility"],
                "decimal annual standard deviation; assumptions vary by labeled row",
                point["dataset"]["as_of"],
            ).model_dump(mode="json")
        )
    return type(result)(**payload, checksum=digest(payload))


@register(
    "explain_optimization_tradeoffs",
    "Explain measured covariance/turnover/cost/constraint trade-offs from verified saved evidence, not financial causes or guaranteed benefits.",
    RunInput,
)
def explain_tradeoffs(ctx, body):
    return result_evidence(ctx, selected_run(ctx, body.run_id), "explain_optimization_tradeoffs")


@register(
    "get_model_governance_status",
    "Read local methodological research review status for the selected optimization. This tool cannot create or change review decisions.",
    Empty,
)
def governance_status(ctx, _):
    row = selected_run(ctx)
    model = ctx.db.scalar(
        select(GovernanceModel).where(
            GovernanceModel.owner == ctx.owner,
            GovernanceModel.source_type == "optimization",
            GovernanceModel.source_id == row.id,
        )
    )
    if model is None:
        raise AppError(
            "GOVERNANCE_MISSING",
            "No registered feasible single-allocation candidate is linked to this run.",
            404,
        )
    return sealed(
        "get_model_governance_status",
        "governance_model",
        model.id,
        row.dataset["synthetic"],
        str(model.created_at.date()),
        {"status": model.status, "intended_use": model.intended_use, "payload": model.payload},
        [
            fact(
                "opt.governance_status",
                "Research model review status",
                model.status,
                "session-bound methodological review only",
                str(model.created_at.date()),
            )
        ],
        [
            "The assistant cannot approve models or mutate governance. Session-bound review is not enterprise maker-checker or real-market investment approval."
        ],
        {"model_id": model.id, "source_run_id": row.id, "version": model.model_version},
    )
