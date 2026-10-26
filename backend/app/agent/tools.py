"""Finite read-only registry. Scope is injected by the server, never by model arguments."""

import json
from dataclasses import dataclass
from uuid import uuid4

from pydantic import Field
from sqlalchemy import select

from app.core.errors import AppError
from app.database.models import ResearchExperiment
from app.ml.service import experiment_comparison, owned_experiment
from app.portfolios.schemas import Portfolio, StrictModel
from app.risk.artifacts import digest

from .contracts import Fact, InvestigationRequest, ToolEvidence
from .security import redact


class Empty(StrictModel):
    pass


class ExperimentInput(StrictModel):
    experiment_id: str | None = Field(None, max_length=36)


@dataclass
class ToolContext:
    db: object
    owner: str
    request: InvestigationRequest
    portfolio: Portfolio
    snapshot_id: str


@dataclass(frozen=True)
class ToolSpec:
    name: str
    purpose: str
    schema: type[StrictModel]
    handler: object
    max_output_bytes: int = 60_000
    timeout_seconds: float = 8


REGISTRY: dict[str, ToolSpec] = {}


def register(name, purpose, schema):
    def decorate(handler):
        REGISTRY[name] = ToolSpec(name, purpose, schema, handler)
        return handler

    return decorate


def sealed(tool, source_type, source_id, synthetic, as_of, data, facts, warnings, provenance=None):
    payload = {
        "id": str(uuid4()),
        "tool": tool,
        "source_type": source_type,
        "source_id": source_id,
        "synthetic": synthetic,
        "as_of": str(as_of),
        "data": data,
        "facts": [f.model_dump(mode="json") if isinstance(f, Fact) else f for f in facts],
        "warnings": warnings,
        "provenance": provenance or {},
    }
    payload = json.loads(redact(json.dumps(payload, allow_nan=False)))
    return ToolEvidence(**payload, checksum=digest(payload))


def fact(key, label, value, unit, as_of):
    return Fact(key=key, label=label, value=value, unit=unit, as_of=str(as_of))


def resolve_experiment(ctx, requested=None):
    selected = ctx.request.experiment_id
    if selected and requested and requested != selected:
        raise AppError("TOOL_SCOPE", "Tool must use the explicitly selected experiment.", 403)
    ident = selected or requested
    if ident is None:
        exp = ctx.db.scalar(
            select(ResearchExperiment)
            .where(
                ResearchExperiment.owner == ctx.owner,
                ResearchExperiment.status.in_(["completed", "partial"]),
                ResearchExperiment.parameters["mode"].as_string() == ctx.request.mode,
            )
            .order_by(ResearchExperiment.created_at.desc())
            .limit(1)
        )
        if exp is None:
            raise AppError(
                "RESEARCH_MISSING",
                "No completed research experiment is accessible in this session. Run or select one in Quantitative Research; private results from an expired session cannot be reassigned.",
                404,
            )
    else:
        exp = owned_experiment(ctx.db, ident, ctx.owner)
    if exp.parameters["mode"] != ctx.request.mode:
        raise AppError(
            "TOOL_SCOPE", "Experiment mode differs from the selected investigation.", 403
        )
    return exp


@register(
    "list_research_experiments",
    "List recent completed experiments in this session and selected source mode.",
    Empty,
)
def list_experiments(ctx, _):
    rows = ctx.db.scalars(
        select(ResearchExperiment)
        .where(
            ResearchExperiment.owner == ctx.owner,
            ResearchExperiment.status.in_(["completed", "partial"]),
            ResearchExperiment.parameters["mode"].as_string() == ctx.request.mode,
        )
        .order_by(ResearchExperiment.created_at.desc())
        .limit(10)
    ).all()
    return sealed(
        "list_research_experiments",
        "registry",
        "owned-research",
        ctx.request.mode == "demo",
        "retrieval time",
        {
            "experiments": [
                {
                    "id": e.id,
                    "status": e.status,
                    "created_at": e.created_at.isoformat(),
                    "test_start": e.protocol["test_start"],
                    "test_end": e.protocol["test_end"],
                }
                for e in rows
            ]
        },
        [],
        ["Only the current session's completed experiments are accessible."],
    )


@register(
    "compare_forecasting_models",
    "Read actual saved four-model matched evaluation, coverage, uncertainty and regime limitations. Never fit/promote a model.",
    ExperimentInput,
)
def compare_models(ctx, body):
    exp = resolve_experiment(ctx, body.experiment_id)
    result = experiment_comparison(ctx.db, exp)
    rows = result["models"]
    as_of = exp.protocol["test_end"]
    facts = []
    compact = []
    for row in rows:
        m = row["metrics"]
        prefix = row["kind"]
        for key, label, unit in [
            ("qlike", "QLIKE", "variance QLIKE"),
            ("mse", "MSE", "decimal variance squared"),
            ("mae", "MAE", "decimal variance"),
            ("observations", "Matched targets", "observations"),
        ]:
            facts.append(fact(f"{prefix}.{key}", f"{prefix} · {label}", m[key], unit, as_of))
        coverages = {}
        for confidence in (95, 99):
            c = m[f"coverage{confidence}"]
            for key in (
                "exceptions",
                "exception_rate",
                "kupiec_p_value",
                "independence_p_value",
                "conditional_p_value",
            ):
                facts.append(
                    fact(
                        f"{prefix}.coverage{confidence}.{key}",
                        f"{prefix} · {confidence}% {key.replace('_', ' ')}",
                        c[key],
                        "exceptions" if key == "exceptions" else "probability",
                        as_of,
                    )
                )
            coverages[str(confidence)] = {
                k: c[k]
                for k in (
                    "observations",
                    "exceptions",
                    "expected_exceptions",
                    "exception_rate",
                    "warnings",
                )
            }
        compact.append(
            {
                "kind": prefix,
                "role": row["role"],
                "status": row["status"],
                "coverage": coverages,
                "limitations": row["limitations"],
            }
        )
    valid = [r for r in rows if r["metrics"]["qlike"] is not None]
    if valid:
        best = min(valid, key=lambda r: r["metrics"]["qlike"])
        facts.append(
            fact(
                "lowest_qlike_model",
                "Lowest observed average QLIKE",
                best["kind"],
                "model name; descriptive only",
                as_of,
            )
        )
    facts.append(
        fact(
            "matched_observations",
            "Common evaluation targets",
            result["matched_observations"],
            "observations",
            as_of,
        )
    )
    regimes = exp.summary["regimes"]
    high = next(r["metrics"]["observations"] for r in regimes["metrics"] if r["regime"] == "high")
    facts.append(
        fact(
            "high_regime_observations",
            "High-volatility regime sample",
            high,
            "observations per model",
            as_of,
        )
    )
    warnings = (
        result["warnings"]
        + exp.summary["warnings"]
        + [
            exp.data_info["portfolio_construction"],
            exp.data_info["universe_limitation"],
            "Prior test labels may enter later refits only after observation; this is a retrospective prequential experiment.",
            "Sparse tail exceptions have weak calibration evidence; nonsignificant p-values do not prove correctness.",
            "SHAP describes fitted predictions and cannot establish market causality. Conversational output cannot change model governance.",
        ]
    )
    if exp.data_info["synthetic"]:
        warnings.append(
            "SYNTHETIC evaluation cannot establish real-market forecasting superiority."
        )
    if high == 0:
        warnings.append(
            "The high-volatility regime has no test observations; stress-regime superiority is unassessed."
        )
    return sealed(
        "compare_forecasting_models",
        "research_experiment",
        exp.id,
        exp.data_info["synthetic"],
        as_of,
        {
            "models": compact,
            "uncertainty": result["uncertainty"],
            "protocol": exp.protocol,
            "excluded_dates": result["excluded_dates"],
            "dataset_hash": exp.dataset_hash,
            "original_runtime": exp.runtime,
        },
        facts,
        warnings,
        {
            "experiment_id": exp.id,
            "snapshot_id": exp.snapshot_id,
            "dataset_hash": exp.dataset_hash,
            "runtime": exp.runtime,
        },
    )


@register(
    "get_model_evaluation",
    "Read a selected owned experiment's measured evaluation, not a generated forecast claim.",
    ExperimentInput,
)
def model_evaluation(ctx, body):
    return compare_models(ctx, body)


@register(
    "get_conditional_var_backtest",
    "Read stored conditional 95/99% VaR coverage on matched targets.",
    ExperimentInput,
)
def var_backtest(ctx, body):
    return compare_models(ctx, body)


def invoke(ctx, name, arguments):
    spec = REGISTRY.get(name)
    if spec is None:
        raise AppError(
            "TOOL_NOT_ALLOWED",
            "Requested operation is outside the read-only financial tool allowlist.",
            403,
        )
    body = spec.schema.model_validate(arguments)
    evidence = spec.handler(ctx, body)
    # Alias handlers retain the actual invoked audit name.
    if evidence.tool != name:
        payload = evidence.model_dump(mode="json", exclude={"checksum"})
        payload["tool"] = name
        evidence = ToolEvidence(**payload, checksum=digest(payload))
    if len(evidence.model_dump_json().encode()) > spec.max_output_bytes:
        raise AppError("TOOL_OUTPUT_LIMIT", "Tool evidence exceeds the bounded output contract.")
    return evidence
