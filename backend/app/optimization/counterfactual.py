from datetime import UTC, datetime
from uuid import uuid4

import numpy as np

from app.core.errors import AppError
from app.database.models import OptimizationCounterfactual, PortfolioSnapshot, RiskInputArtifact
from app.risk.artifacts import digest, frame_payload, payload_frame, persist_inputs
from app.risk.contracts import StressRequest
from app.risk.service import resolve_prices
from app.risk.stress import historical_replay, hypothetical
from app.risk.stress_service import scenario_dates

from .comparison import virtual_portfolio
from .contracts import VERSION, OptimizationRequest
from .service import verify_inputs


def counterfactual(db, row, owner, point_index, scenario, *, saved_payload=None):
    if row.result is None or point_index >= len(row.result["points"]):
        raise AppError("OPTIMIZATION_POINT", "Select an existing completed point.", 409)
    point = row.result["points"][point_index]
    if not point["solution"]["feasible"]:
        raise AppError(
            "OPTIMIZATION_INFEASIBLE",
            "An infeasible point has no proposed allocation for stress testing.",
            409,
        )
    portfolio, payload = verify_inputs(db, row, owner)
    settings = OptimizationRequest.model_validate(point["parameters"])
    if scenario.mode != portfolio.mode or (
        scenario.dataset_id is not None and scenario.dataset_id != settings.dataset_id
    ):
        raise AppError(
            "COUNTERFACTUAL_SCOPE",
            "Scenario mode/data must match the selected saved sleeve; use the explicit scenario history field for an older covered dataset.",
            403,
        )
    scenario_payload = {
        "kind": "optimization_counterfactual",
        "optimization_input_hash": row.input_hash,
        "point_index": point_index,
    }
    virtual = virtual_portfolio(portfolio, np.array(point["solution"]["weights"]))
    if scenario.kind == "historical":
        if saved_payload is not None:
            prices, source = payload_frame(saved_payload["scenario"])
        elif scenario.scenario_dataset_id:
            prices, source = resolve_prices(
                db, portfolio, owner, scenario.scenario_dataset_id, require_fresh=False
            )
        else:
            prices, source = payload_frame(payload["history"])
        start, end = scenario_dates(scenario, portfolio.synthetic)
        before = historical_replay(portfolio, prices, start, end)
        after = historical_replay(virtual, prices, start, end)
        scenario_payload["scenario"] = frame_payload(prices.loc[str(start) : str(end)], source)
        source_info = source.model_dump(mode="json")
    else:
        before = hypothetical(
            portfolio, scenario.market_shock, scenario.sector_shocks, scenario.security_shocks
        )
        after = hypothetical(
            virtual, scenario.market_shock, scenario.sector_shocks, scenario.security_shocks
        )
        source_info = {
            "source": "User-specified direct hypothetical shocks",
            "synthetic": portfolio.synthetic,
        }
    snapshot, artifact = persist_inputs(db, portfolio, scenario_payload, owner)
    parameters = scenario.model_dump(mode="json")
    result = {
        "id": str(uuid4()),
        "run_id": row.id,
        "point_index": point_index,
        "scenario": parameters,
        "version": VERSION,
        "source": source_info,
        "current": before,
        "proposed": after,
        "pnl_difference": after["pnl"] - before["pnl"],
        "loss_improvement": before["loss"] - after["loss"],
        "asset_changes": [
            {
                "instrument": a["instrument"],
                "sector": a["sector"],
                "mapping": a["mapping"],
                "current_pnl": a["pnl"],
                "proposed_pnl": b["pnl"],
                "pnl_difference": b["pnl"] - a["pnl"],
                "current_weight": a["weight"],
                "proposed_weight": b["weight"],
            }
            for a, b in zip(before["assets"], after["assets"], strict=True)
        ],
        "snapshot_id": snapshot.id,
        "artifact_id": artifact.id,
        "input_hash": digest(
            {
                "run": row.input_hash,
                "point": point_index,
                "artifact": artifact.content_hash,
                "scenario": parameters,
                "version": VERSION,
            }
        ),
        "warnings": [
            "Identical shock definitions, valuation date, sleeve notional and scenario data are applied to current and proposed continuous allocations.",
            "Counterfactual historical replay is retrospective and may use allocations estimated after that scenario. It is not out-of-sample strategy performance.",
            "Hypothetical shocks are what-if assumptions, not predictions or inferred factor sensitivities. Costs are reported separately.",
        ],
    }
    if portfolio.synthetic:
        result["warnings"].append(
            "SYNTHETIC data cannot represent an actual historical market loss."
        )
    result["result_hash"] = digest(result)
    db.add(
        OptimizationCounterfactual(
            id=result["id"],
            owner=owner,
            run_id=row.id,
            payload=result,
            created_at=datetime.now(UTC),
        )
    )
    db.commit()
    return result


def verified_counterfactual(db, row, run, owner):
    result = row.payload
    if row.owner != owner or row.run_id != run.id:
        raise AppError("COUNTERFACTUAL_NOT_FOUND", "Counterfactual not found in this session.", 404)
    if (
        result.get("result_hash") != digest({k: v for k, v in result.items() if k != "result_hash"})
        or result.get("version") != VERSION
    ):
        raise AppError(
            "COUNTERFACTUAL_INTEGRITY",
            "Saved counterfactual failed hash/version verification.",
            409,
        )
    snapshot = db.get(PortfolioSnapshot, result["snapshot_id"])
    artifact = db.get(RiskInputArtifact, result["artifact_id"])
    if (
        not snapshot
        or not artifact
        or snapshot.owner != owner
        or artifact.owner != owner
        or digest(snapshot.payload) != snapshot.content_hash
        or digest(artifact.payload) != artifact.content_hash
    ):
        raise AppError(
            "COUNTERFACTUAL_INTEGRITY",
            "Saved scenario snapshot or artifact failed verification.",
            409,
        )
    expected = digest(
        {
            "run": run.input_hash,
            "point": result["point_index"],
            "artifact": artifact.content_hash,
            "scenario": result["scenario"],
            "version": VERSION,
        }
    )
    if expected != result["input_hash"]:
        raise AppError(
            "COUNTERFACTUAL_INTEGRITY", "Saved scenario parameters or inputs changed.", 409
        )
    verify_inputs(db, run, owner)
    return result, artifact.payload


def reproduce_counterfactual(db, row, run, owner):
    result, payload = verified_counterfactual(db, row, run, owner)
    return counterfactual(
        db,
        run,
        owner,
        result["point_index"],
        StressRequest.model_validate(result["scenario"]),
        saved_payload=payload,
    )
