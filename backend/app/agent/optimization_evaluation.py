"""Independent, fixed optimization-agent expectations; no paid provider calls."""

import json
import math
import time

from fastapi.testclient import TestClient

from app.core.config import ROOT
from app.risk.artifacts import digest

from .service import queue

CASES = ROOT / "data/evaluations/optimization_golden_v1.json"


def evaluate_optimization(client, fixtures):
    suite = json.loads(CASES.read_text())
    results = []
    for case in suite["cases"]:
        started = time.monotonic()
        result = {"id": case["id"], "category": case["category"], "passed": False, "failure": None}
        caller = TestClient(client.app) if case["fixture"] == "foreign" else client
        try:
            if caller is not client:
                caller.__enter__()
            body = {"question": case["question"], "engine": "demo"}
            if case["fixture"]:
                body["optimization_run_id"] = fixtures[case["fixture"]]
            response = caller.post("/api/v1/agent/investigate", json=body)
            assert response.status_code == 202, response.text
            ident = response.json()["id"]
            queue.futures[ident].result(timeout=30)
            actual = caller.get(f"/api/v1/agent/investigations/{ident}").json()
            calls = caller.get(f"/api/v1/agent/investigations/{ident}/tool-calls").json()
            assert actual["status"] == case["status"], actual
            assert [c["name"] for c in calls] == case["tools"], calls
            assert actual["verification"]["unsupported_values_published"] == 0
            facts = {f["key"]: f["value"] for f in actual["answer"]["claims"]}
            checks = case["checks"]
            if checks.get("no_claims"):
                assert not facts
            if checks.get("no_allocation"):
                assert not any(k.startswith("opt.weight.") for k in facts)
                assert "opt.proposed_volatility" not in facts
            for field in ("goal_status", "solver_status", "governance_status"):
                if field in checks:
                    assert facts[f"opt.{field}"] == checks[field], facts
            if "max_turnover" in checks:
                assert facts["opt.turnover"] <= checks["max_turnover"] + 1e-7
            if "target" in checks:
                achieved = 1 - facts["opt.proposed_volatility"] / facts["opt.current_volatility"]
                assert math.isclose(facts["opt.volatility_reduction"], achieved, abs_tol=1e-12)
                assert facts["opt.requested_reduction"] == checks["target"]
                assert (facts["opt.goal_status"] == "achieved_by_verified_allocation") == (
                    achieved + 1e-7 >= checks["target"]
                )
            if "warning" in checks:
                assert any(checks["warning"] in w for w in actual["answer"]["warnings"])
            if case["fixture"] == "foreign":
                with TestClient(client.app) as other:
                    assert other.get(f"/api/v1/agent/investigations/{ident}").status_code == 404
            result.update(
                passed=True,
                investigation_id=ident,
                tool_names=[c["name"] for c in calls],
                claims_hash=digest(actual["answer"]["claims"]),
            )
        except (AssertionError, KeyError) as error:
            result["failure"] = str(error)[:1500]
        finally:
            if caller is not client:
                caller.__exit__(None, None, None)
        result["elapsed_seconds"] = time.monotonic() - started
        results.append(result)
    return {
        "version": suite["version"],
        "suite_hash": digest(suite),
        "acceptance": suite["acceptance"],
        "passed": all(r["passed"] for r in results),
        "cases": results,
    }
