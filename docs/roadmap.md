# Delivery roadmap

## Phase 1 — current implementation target

- [ ] Pure risk engine and analytical tests
- [ ] Versioned demo portfolio and daily history
- [ ] FastAPI, persistence, migrations, and validated imports
- [ ] Secure read-only Kite integration
- [ ] Optional Alpha Vantage, FRED, and Frankfurter adapters
- [ ] Working Next.js portfolio/risk/data-source views
- [ ] CI, Compose, documentation, and workflow verification

## Phase 2 — advanced risk

Fractionally weighted empirical Expected Shortfall; Gaussian and correlated Monte Carlo VaR; Euler risk attribution; historical replay; factor shocks; immutable reproducible input artifacts and replayable risk runs. Validate analytical cases and simulation convergence.

## Phase 3 — ML research

Rolling/EWMA/GARCH benchmarks, lagged features, chronological splits, training-only preprocessing, walk-forward LightGBM, QLIKE and volatility errors, Kupiec/Christoffersen coverage, regime stability, ablations, versioned model registry. Report measured out-of-sample results only.

## Phase 4 — agentic investigations

Document ingestion and hybrid retrieval, typed authorized quantitative tools, explicit LangGraph state machine, citation validation, prompt-injection defenses, golden evaluation questions, and numerical verification. LLMs must never invent financial calculations.

## Phase 5 — optimization and governance

CVXPY minimum variance with long-only, position/sector/turnover constraints and transaction costs; policy checks; evidence-grounded reports; trace and model/data versioning; safety evaluation.

## Phase 6 — production hardening

Identity/authorization, encrypted durable credential storage, session and provider rate limits, retention/backup policies, performance and adversarial testing, deployment observability, CI/CD, and operational runbooks. No execution/trading scope is authorized.
