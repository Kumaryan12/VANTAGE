# Delivery roadmap

## Phase 1 — implemented

- [x] Pure risk engine and analytical tests
- [x] Versioned demo portfolio and daily history
- [x] FastAPI, persistence, migrations, and validated imports
- [x] Secure read-only Kite integration (mocked authentication/read contracts; live credentials required)
- [x] Optional Alpha Vantage, FRED, and Frankfurter adapters (Frankfurter live-tested; keyed services contract-tested)
- [x] Working Next.js portfolio/risk/data-source views
- [x] CI, Compose configuration, documentation, and local workflow verification

Evidence and precise limits: [verification.md](verification.md). The complete Compose image stack has not been built in this session; documented local startup and PostgreSQL-backed workflows were tested.

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
