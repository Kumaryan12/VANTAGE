"""Run the actual credential-free golden suite and retain every case outcome."""

import argparse
import hashlib
from uuid import uuid4

from sqlalchemy.orm import Session

from app.agent.evaluation import queue
from app.core.config import ROOT
from app.database.models import AgentEvaluation
from app.database.session import engine


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--no-report",
        action="store_true",
        help="Database integration smoke without overwriting tracked report",
    )
    args = parser.parse_args()
    with Session(engine) as db:
        job = queue.submit(db, hashlib.sha256(f"cli-evaluation:{uuid4()}".encode()).hexdigest())
        queue.futures[job["id"]].result(timeout=180)
        db.expire_all()
        row = db.get(AgentEvaluation, job["id"])
        payload = row.payload
        print("Evaluation", row.id, row.status)
        print(
            "Acceptance",
            payload.get("acceptance_passed"),
            "Failures",
            payload.get("failures", payload.get("error")),
        )
        for key, metric in payload.get("metrics", {}).items():
            print(key, metric)
        if not args.no_report:
            lines = [
                "# Executed financial investigator evaluation",
                "",
                f"Run `{row.id}` · status **{row.status}** · suite `{payload.get('version', 'unavailable')}`.",
                "",
                "This measures deterministic synthetic workflows and backend security/verifier probes, **not live-LLM quality, real-world financial validity, or production readiness**.",
                "",
                f"Dataset SHA-256 `{payload.get('dataset_sha256', 'unavailable')}`. Acceptance passed: **{payload.get('acceptance_passed', 'unavailable')}**.",
                "",
                "| Metric | Passed | Applicable cases | Rate |",
                "| --- | ---: | ---: | ---: |",
            ]
            for key, m in payload.get("metrics", {}).items():
                lines.append(
                    f"| {key} | {m['passed']} | {m['total']} | {m['rate']:.6g} |"
                    if m["rate"] is not None
                    else f"| {key} | {m['passed']} | {m['total']} | unavailable |"
                )
            lines += [
                "",
                "Thresholds were fixed before execution in phase4_audit.md: task >=95%, tool/numeric/citation >=98%, safety 100%, zero unsupported published values. Inapplicable cases are excluded from each denominator.",
                "",
                "## Runtime and efficiency",
                "```json",
                __import__("json").dumps(
                    {
                        "runtime": payload.get("runtime"),
                        "efficiency": payload.get("efficiency"),
                        "categories": payload.get("categories"),
                    },
                    indent=2,
                ),
                "```",
                "",
                "## Per-case results",
                "| Case | Category | Passed | Failure | Seconds |",
                "| --- | --- | --- | --- | ---: |",
            ]
            for c in payload.get("cases", []):
                lines.append(
                    f"| {c['id']} | {c['category']} | {c['passed']} | {c['failure'] or 'none'} | {c['elapsed_seconds']:.4f} |"
                )
            lines += [
                "",
                "## Limits and reproduction",
                *payload.get("limitations", []),
                "Paid-provider transports are mock-tested separately. No paid call was made by this suite; tokens and cost are unavailable, not zero.",
                "Every case retains expected tools, numerical references, actual checks, failures, source identifiers and concise execution activity in the private evaluation registry. Fresh browser sessions cannot recover the CLI's private records.",
                "Run `backend/.venv/bin/python backend/scripts/agent_evaluate.py` after migrations. Use `--no-report` for PostgreSQL/CI smoke. The UI's Run golden evaluation action creates an owned inspectable report in the current session. Older failed runs remain stored; rerunning does not erase them.",
            ]
            (ROOT / "docs/agent_evaluation_results.md").write_text("\n".join(lines) + "\n")
        if row.status != "completed" or not payload.get("acceptance_passed"):
            raise SystemExit(1)


if __name__ == "__main__":
    main()
