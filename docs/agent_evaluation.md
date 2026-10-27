# Agent evaluation protocol

The fixed `data/evaluations/agent_golden_v1.json` contains **60 curated cases**, six each across portfolio, risk, models, documents, multistep, missing data, conflicting evidence, unauthorized access, adversarial content and unsupported claims. Each stores question, expected behavior/tools/status, permitted fixture evidence, numerical references where applicable, citation requirements, limitation expectations and setup/probe type. Portfolio/reference figures are tied to the deterministic 2026-10-23 synthetic fixture. The suite trains a fresh bounded research fixture; it does not borrow or reassign another browser's Phase 3 experiment.

Thresholds were fixed in phase4_audit.md before running: task >=95%, tools/numeric/citations >=98%, safety 100%, zero unsupported published values; bounded eight tools/24 transitions. Fifteen direct security/verifier probes complement 45 end-to-end deterministic workflows. This measures the executed backend policy/financial workflow, not an LLM's natural-language intelligence. No paid call occurs.

## Checks and denominators

- Task success requires expected status, tool sequence, reference figures, source/citation requirements, warnings and budgets to pass.
- Tool correctness compares actual ordered audited calls against the expected approved tools. Probes do not inflate this denominator.
- Numerical accuracy checks 24 applicable workflow cases against stored reference numbers (rtol/atol 1e-9); the engine's per-claim verifier separately checks every selected authoritative value/unit/date/hash.
- Retrieval/citation correctness applies to 15 cases requiring real pages/quotes; foreign/deleted sources cannot count as support. Conflicting-report cases require both actual source IDs.
- Groundedness verifies no unsupported values are published. Safety has 17 explicit probes/malicious-document checks; blocked operations/refusals count as success only when expected.
- Latency/tool counts are measured. LLM tokens and cost are unavailable for this no-LLM run. Provider timeout, retry, error, scope and structured-output behavior have separate explicit mocked tests; live-provider quality remains unmeasured.

The first executed development run passed 25/60: ordinary user rate limits were incorrectly applied to the isolated evaluator, and `shortfall` was matched as a fall scenario. These defects were corrected without changing expected answers or thresholds. `data/evaluations/regression_failures_v1.json` retains examples and the initial measured score; failed development runs remain in the registry. The later executed run and full per-case table are in [agent_evaluation_results.md](agent_evaluation_results.md).

## Running and inspecting

`backend/.venv/bin/python backend/scripts/agent_evaluate.py` runs actual fixtures and writes the report; `--no-report` performs a DB-backed smoke without altering tracked evidence. Set DATABASE_URL to test PostgreSQL. The API/UI Run golden evaluation action returns 202, progress and a current-session owned report; it uses a separate synthetic fixture owner and never reads real broker data. Each case retains expected/actual checks, failures, timing, selected claims/citations, source identifiers and concise activity. At most one suite per process and two runs per hour per session are allowed. Its dedicated synthetic workspace bypasses interactive per-minute throttling via a private internal parameter, not a public request option.

Case data/hash, runtime packages and available git commit identify the run. The fresh final report must be generated after code is committed; do not relabel earlier results. The original Phase 3 report remains unchanged at its recorded revision. Successful tests establish consistency with synthetic fixtures and source contracts, not current market conclusions or institutional production readiness.

Actual provider smoke is deliberately opt-in: configure a key and `VANTAGE_LIVE_AI=1 .../python backend/scripts/smoke_live_ai.py`. It has not been executed without credentials. This opt-in is separate from all reported golden/CI results.
