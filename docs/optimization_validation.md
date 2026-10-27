# Optimization verification and reproduction

[Executed synthetic research report](research/portfolio_optimization_validation.md) records actual solver, risk, turnover/cost, curve, sensitivity, scenario, infeasibility and agent-case results with original input/runtime/commit hashes. It is not real-market or live-LLM validation. Earlier Phase 3/4 reports keep their original provenance. [Audit](phase5_audit.md) documents the baseline and ordering defect; [verification](verification.md) records final regression evidence.

From the repository root, install locked Python dependencies into Python 3.12+ `backend/.venv`, install frontend dependencies, then apply migrations:

```bash
backend/.venv/bin/pip install -r backend/requirements.lock
backend/.venv/bin/pip install --no-deps -e backend
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/pytest backend/tests
backend/.venv/bin/ruff check backend
backend/.venv/bin/ruff format --check backend
cd frontend
npm ci
npm run lint && npm run typecheck && npm run build
PLAYWRIGHT_CHANNEL=chrome npm run test:e2e
```

Use installed Chrome or install Playwright Chromium and omit its channel. Browser checks require a fresh backend and a frontend built from the current code; do not reuse stale processes. SQLite is the local fallback, PostgreSQL is the Compose database. For actual PostgreSQL integration set `DATABASE_URL` to the configured PostgreSQL URL in the shell before these commands:

```bash
backend/.venv/bin/alembic -c backend/alembic.ini upgrade head
backend/.venv/bin/python backend/scripts/smoke_phase2.py
backend/.venv/bin/python backend/scripts/research_report.py --smoke
backend/.venv/bin/python backend/scripts/agent_evaluate.py --no-report
backend/.venv/bin/python backend/scripts/optimization_validate.py --smoke
```

The no-flag optimization CLI executes the same deterministic synthetic experiments and writes the tracked report; `--smoke` never overwrites it. It tests allocation/scenario reproduction, source hashes, six sensitivity axes, explicit hypothetical return assumptions, owner isolation and a refused candidate→approved transition. It leaves models as candidates. Thirteen fixed cases in `data/evaluations/optimization_golden_v1.json` independently specify expected tools/status/goal/refusal behavior. Their evaluator uses the public API; the foreign-owner case uses its own unowned session. Interactive rate limits remain enabled. The Phase 4 60-case expectations/thresholds are unchanged.

Numerical tests include analytical one/two/multi-asset solutions, correlated/singular/perfect-correlation/near-zero-risk cases, independent constraints/costs, inaccurate and stopped solver states, false solver weights, scenario P&L reconciliation, immutable artifact/result tampering, worker failure, source coverage/order, per-owner retrieval and governance gates. Expensive numerical work remains backend-only. Browser coverage retains all nine Phase 1–4 workflows and adds basic allocation/reproduction/infeasibility, curve/sensitivity/stress, and governance/pinned-agent workflows.

Reproduction tolerances and limitations are in [architecture](optimization_architecture.md) and [methodology](optimization_methodology.md). Tests establish the executed fixtures and security behavior; they do not certify calendar continuity, investment suitability, actual broker fees, future market benefits, live-provider quality or production readiness. Complete Compose image builds and Phase 6 operating controls remain separate work.
