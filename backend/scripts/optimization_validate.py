"""Execute synthetic optimization/reproduction/studies/stress and fixed agent cases on the configured DB."""

import argparse
import json
from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.agent.optimization_evaluation import evaluate_optimization
from app.brokers.demo import DemoBroker
from app.core.config import ROOT
from app.database.session import engine
from app.main import app
from app.optimization.service import queue


def execute(client, path, body):
    submitted = client.post(f"/api/v1/optimization/{path}", json=body)
    assert submitted.status_code == 202, submitted.text
    ident = submitted.json()["id"]
    queue.futures[ident].result(timeout=100)
    response = client.get(f"/api/v1/optimization/runs/{ident}")
    assert response.status_code == 200, response.text
    detail = response.json()
    assert detail["status"] == "completed", detail
    return detail


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--smoke",
        action="store_true",
        help="Verify PostgreSQL/CI without rewriting the tracked measured report",
    )
    args = parser.parse_args()
    with TestClient(app) as client:
        base = execute(client, "run", {})
        p = base["result"]["points"][0]
        assert p["solution"]["feasible"] and p["solution"]["validation"]["passed"]
        replay = execute(client, f"runs/{base['id']}/reproduce", None)
        assert replay["result"]["reproduction_match"] is True
        curve = execute(
            client, "frontier", {"base": {}, "turnover_budgets": [0, 0.05, 0.1, 0.15, 0.25]}
        )
        sensitivity = execute(
            client,
            "sensitivity",
            {
                "base": {},
                "variations": [
                    {"kind": "window", "value": 126},
                    {"kind": "shrinkage", "value": 0.1},
                    {"kind": "max_weight", "value": 0.25},
                    {"kind": "sector_max", "sector": "Technology", "value": 0.15},
                    {"kind": "turnover", "value": 0.1},
                    {"kind": "cost_penalty", "value": 5},
                ],
            },
        )
        assumed = {
            h.instrument: 0.05 + 0.01 * i for i, h in enumerate(DemoBroker().portfolio().holdings)
        }
        efficient = execute(
            client,
            "frontier",
            {
                "base": {
                    "expected_returns": {
                        "annual_returns": assumed,
                        "source": "Explicit invented annual return assumptions for synthetic methodology validation only; these are not forecasts.",
                    }
                },
                "mode": "efficient",
                "return_targets": [0.06, 0.08, 0.15],
            },
        )
        infeasible = execute(client, "run", {"constraints": {"max_weight": 0.2, "max_turnover": 0}})
        target = execute(
            client, "run", {"objective": "target_risk", "target_annual_volatility": 0.001}
        )
        assert infeasible["result"]["points"][0]["solution"]["status"] == "infeasible"
        assert target["result"]["points"][0]["solution"]["status"] == "infeasible"
        stresses = []
        for scenario in (
            {"kind": "hypothetical", "sector_shocks": {"Financials": -0.15}},
            {"kind": "historical", "scenario_id": "synthetic_2026"},
        ):
            response = client.post(
                "/api/v1/optimization/counterfactual",
                json={"run_id": base["id"], "scenario": scenario},
            )
            assert response.status_code == 200, response.text
            s = response.json()
            restored = client.post(f"/api/v1/optimization/counterfactuals/{s['id']}/reproduce")
            assert restored.status_code == 200, restored.text
            assert restored.json()["input_hash"] == s["input_hash"]
            for side in ("current", "proposed"):
                assert restored.json()[side]["pnl"] == s[side]["pnl"]
            stresses.append(s)
        assert (
            client.post(
                "/api/v1/optimization/compare", json={"run_ids": [base["id"], replay["id"]]}
            ).status_code
            == 200
        )
        gov = client.get(
            f"/api/v1/governance/models/{base['result']['governance_model_id']}"
        ).json()
        assert gov["status"] == "candidate" and gov["current_validation"]["validation_ready"]
        denial = client.post(
            f"/api/v1/governance/models/{gov['id']}/review",
            json={
                "status": "approved_research",
                "human_review": True,
                "research_only": True,
                "rationale": "Automated gate probe; no human or investment approval is asserted.",
            },
        )
        assert denial.status_code == 409
        with TestClient(app) as stranger:
            foreign = execute(stranger, "run", {})
            assert stranger.get(f"/api/v1/optimization/runs/{base['id']}").status_code == 404
        agent = evaluate_optimization(
            client,
            {
                "base": base["id"],
                "infeasible": infeasible["id"],
                "sensitivity": sensitivity["id"],
                "foreign": foreign["id"],
            },
        )
        print(
            "Optimization agent acceptance",
            agent["passed"],
            sum(c["passed"] for c in agent["cases"]),
            "/",
            len(agent["cases"]),
        )
        for case in agent["cases"]:
            print(case["id"], case["passed"], case["failure"])
        if not args.smoke:
            write_report(base, replay, curve, sensitivity, efficient, target, stresses, gov, agent)
        assert agent["passed"], (
            "Fixed optimization-agent acceptance cases failed; inspect retained outcomes."
        )
        print(
            f"Verified allocations, constraints, studies, identical stress/replay, owner scope and research governance gates: PASS ({engine.dialect.name})"
        )


def write_report(base, replay, curve, sensitivity, efficient, target, stresses, gov, agent):
    point = base["result"]["points"][0]
    comparison = point["comparison"]
    lines = [
        "# Executed synthetic portfolio optimization validation",
        "",
        f"Executed {datetime.now(UTC).isoformat()} against **{engine.dialect.name}**. Run `{base['id']}`; reproduction `{replay['id']}`.",
        "",
        "This is actual executed software/methodology evidence from deterministic **synthetic** INR prices and holdings. It is in-sample, retrospective frozen-basket analysis, not a backtest of executable orders or evidence of future investment performance. No real-market experiment or live-LLM quality is claimed.",
        "",
        "## Objective, data and methodology",
        "",
        "Minimize annual variance `252*w'Σ_daily*w`, fully invested and long-only in all six current synthetic holdings. Position max 20%, one-way turnover max 15%, no invented cash or new securities. Unknown sectors remain explicit. Covariance is Phase 2 sample ddof=1; shrinkage and alternatives are labeled below. Annual variance, turnover and cost fractions have documented units. Default costs are 10 basis points per gross value shift, not broker charges. Costs are not deducted from the fixed risk notional.",
        "",
        "```json",
        json.dumps(
            {
                "dataset": point["dataset"],
                "parameters": point["parameters"],
                "runtime": base["runtime"],
                "input_hash": base["input_hash"],
                "snapshot_id": base["snapshot_id"],
                "artifact_id": base["artifact_id"],
                "solver": point["solution"]["solver"],
                "independent_validation": point["solution"]["validation"],
            },
            indent=2,
        ),
        "```",
        "",
        "## Matched current/proposed risk",
        "",
        "One-day tail losses are INR; annual volatility/variance are decimal units; HHI is dimensionless. Signed changes retain adverse outcomes.",
        "",
        "| Metric | Current | Proposed | Change |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key, value in comparison["delta"].items():
        lines.append(
            f"| {key} | {comparison['current'][key]:.10g} | {comparison['proposed'][key]:.10g} | {value:.10g} |"
        )
    lines += [
        "",
        f"Measured fitted volatility reduction: **{comparison['volatility_reduction_fraction']:.6%}**. One-way turnover **{point['solution']['turnover']:.6%}**; gross allocation change **{point['solution']['gross_weight_change']:.6%}**; one-way notional INR **{point['solution']['one_way_notional']:.6f}**; gross notional INR **{point['solution']['gross_notional_traded']:.6f}**; estimated cost INR **{point['solution']['cost_inr']:.6f}** ({point['solution']['cost_fraction']:.6%} of sleeve).",
        "",
        "| Synthetic holding | Sector | Current weight | Proposed weight | Approximate value shift INR |",
        "| --- | --- | ---: | ---: | ---: |",
    ]
    for a in point["allocations"]:
        lines.append(
            f"| {a['instrument']} | {a['sector']} | {a['current_weight']:.8f} | {a['proposed_weight']:.8f} | {a['approximate_notional_change']:.6f} |"
        )
    for label, study in (
        ("Risk–turnover curve", curve),
        ("Six-axis sensitivity", sensitivity),
        ("Conditional risk–return frontier", efficient),
    ):
        lines += [
            "",
            f"## {label}",
            "",
            f"Actual study `{study['id']}`. The conditional frontier uses explicitly invented synthetic annual return assumptions, never historical means or volatility forecasts as expected returns. Infeasible points have no weights or risk values.",
            "",
            "| Setting | Status | Annual volatility | One-way turnover | Cost INR | Allocation distance from base |",
            "| --- | --- | ---: | ---: | ---: | ---: |",
        ]
        for p in study["result"]["points"]:
            sol = p["solution"]
            distance = p.get("allocation_stability", {}).get("one_way_distance_from_base")
            values = [sol["annual_volatility"], sol["turnover"], sol["cost_inr"], distance]
            lines.append(
                f"| {p['label']} | {sol['status']} | "
                + " | ".join("unavailable" if v is None else f"{v:.10g}" for v in values)
                + " |"
            )
        lines += [
            "",
            "Large changes across labeled variations indicate potential estimation instability; no statistical uncertainty band or future efficacy is inferred.",
        ]
    lines += [
        "",
        "## Identical counterfactual stress",
        "",
        "Historical replay uses exact endpoints and fixed virtual adjusted-series units, without rebalancing. These allocations were estimated after the replay period; this is not out-of-sample strategy validation.",
        "",
        "| Scenario | Current P&L INR | Proposed P&L INR | Loss improvement INR | Reconciled saved-input replay |",
        "| --- | ---: | ---: | ---: | --- |",
    ]
    for s in stresses:
        lines.append(
            f"| {json.dumps(s['scenario'], sort_keys=True)} | {s['current']['pnl']:.8f} | {s['proposed']['pnl']:.8f} | {s['loss_improvement']:.8f} | passed |"
        )
    lines += [
        "",
        "## Infeasibility, numerical checks and governance",
        "",
        "The 20% position cap with zero turnover was executed and remained infeasible; no allocation was published. The executed 0.1% annual-volatility target also remained infeasible. Diagnostic:",
        *target["result"]["points"][0]["solution"]["diagnostics"],
        "",
        f"Saved-input allocation reproduction matched: **{replay['result']['reproduction_match']}**. Independent maximum constraint violation: **{point['solution']['validation']['maximum_violation']:.12g}**. Weight/covariance hashes and original source/version metadata are checked before recomputation without provider access. Tolerances:",
        "```json",
        json.dumps(replay["result"]["reproduction_tolerances"], indent=2),
        "```",
        "",
        f"Governance source `{gov['id']}` remains **{gov['status']}**. Reproduction/numerical gates passed. A direct candidate→approved request was rejected (409); this validation runner did not approve a model. Human review must cover all eight review areas, with synthetic/out-of-sample/operational gaps stated explicitly. Session-bound review is not enterprise maker-checker.",
        "",
        "## Fixed optimization-agent cases",
        "",
        f"Suite `{agent['version']}` SHA-256 `{agent['suite_hash']}`. Actual acceptance: **{agent['passed']}**. These cases are independent of the unchanged Phase 4 60-case suite. They measure deterministic tool/fact/authorization behavior, not live-LLM quality. No paid call was made; provider tokens/cost are unavailable.",
        "",
        "| Case | Category | Passed | Failure | Investigation | Seconds |",
        "| --- | --- | --- | --- | --- | ---: |",
    ]
    for c in agent["cases"]:
        lines.append(
            f"| {c['id']} | {c['category']} | {c['passed']} | {c['failure'] or 'none'} | {c.get('investigation_id', 'unavailable')} | {c['elapsed_seconds']:.5f} |"
        )
    lines += [
        "",
        "## Reproduction and limitations",
        "",
        "Run `backend/.venv/bin/python backend/scripts/optimization_validate.py` after migrations to execute and regenerate this report. Use `--smoke` for PostgreSQL/CI without overwriting the measured report. Original Phase 3 and Phase 4 reports retain their earlier commits and results. Fresh sessions cannot recover the CLI's private saved runs.",
        "",
        "Covariance and optional return assumptions are estimated/unstable; minima need not lower every VaR, ES or stress loss. Gaussian simulations have unbounded tails and sampling error. Costs omit unverified liquidity, impact, taxes and lot sizes. Continuous weights do not establish executable orders. Source-approved real history must cover every held asset; actual holdings never use Demo Mode fallback. No optimized allocation is promoted automatically. Durable identity, recovery/retention, distributed workers and production hardening remain Phase 6.",
        "",
        "The executed synthetic experiment supports numerical and integration correctness for these fixtures. It does not establish superior investment performance or institutional production readiness.",
    ]
    output = ROOT / "docs/research/portfolio_optimization_validation.md"
    output.write_text("\n".join(lines) + "\n")
    print("Measured report:", output)


if __name__ == "__main__":
    main()
