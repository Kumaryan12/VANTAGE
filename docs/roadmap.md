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

## Phase 2 — implemented

- [x] Historical/Gaussian/Monte Carlo VaR and Expected Shortfall, including exact fractional empirical tail mass
- [x] Configurable validated confidence, sample rules and common loss units
- [x] Full covariance estimation, explicit identity shrinkage, symmetry/PSD/condition diagnostics
- [x] Seeded spectral correlated simulation with compact distributions and conditional sampling uncertainty
- [x] Euler security/sector volatility attribution and reconciliation
- [x] Direct hypothetical shocks with replacement precedence and explicit mappings
- [x] Covered historical replay, independent scenario datasets, disabled missing coverage, clearly labeled synthetic replay
- [x] Immutable snapshots/input artifacts, complete versioned run metadata, private retrieval/comparison/replay
- [x] Functional risk/stress/run-history visualizations and browser workflows
- [x] Numerical, API, authorization, migration, PostgreSQL and regression validation

No verified actual market-event loss is claimed without a permitted covered dataset. Common-date exchange-calendar gaps cannot be independently certified. Full Compose image builds remain unverified; local processes and PostgreSQL are tested. Durable identity/session recovery, storage retention and public deployment remain Phase 6 work.

## Phase 3 — implemented

- [x] Rolling/EWMA/actual ARCH GARCH and LightGBM portfolio conditional variance models
- [x] Lagged point-in-time features, strict source alignment, training-only imputation, bounded pre-test validation
- [x] Expanding/rolling walk-forward refits with saved chronological lineage
- [x] Matched QLIKE/MSE/MAE, rolling loss diagnostics and descriptive paired uncertainty
- [x] Phase 2 Gaussian conditional VaR, Kupiec/Christoffersen/conditional coverage with sparse-sample handling
- [x] Training-threshold regime analysis, actual saved-origin TreeSHAP, gain importance, drift and sensitivity
- [x] Owned asynchronous registry, checksum artifacts, reproduction, manual model-role audit
- [x] Functional research terminal, executed synthetic report, numerical/API/browser/PostgreSQL regression evidence

[Report](research/volatility_model_comparison.md) and [protocol/limitations](research_protocol.md). Synthetic evidence does not establish economic ML superiority. Future research includes independent point-in-time market datasets, explicit feature ablation studies, richer tail models and multivariate covariance. Distributed workers, persistent identity, retention and deployment remain Phase 6.

## Phase 4 — implemented local investigation workflow

- [x] Typed bounded single-investigator state machine, optional provider interface, explicit no-key/demo states
- [x] Fourteen authorized read-only financial/research/retrieval tools; existing quantitative engines reused
- [x] Verified model comparison, portfolio exposures/contributions and reconciled user-requested hypothetical stress
- [x] Private permitted PDF ingestion, exact page/chunk metadata, keyword and opt-in embedding/hybrid retrieval
- [x] Deterministic value/unit/date/hash/citation verification and conservative structured response composition
- [x] Owned investigation/evidence/activity/evaluation records and source deletion cleanup
- [x] Executed 60-case deterministic golden suite with fixed thresholds and retained failures
- [x] AI Risk Assistant, evidence/citation inspection, document library, history and actual evaluation dashboard
- [x] Numerical/security/API/provider-mock/PostgreSQL/frontend/browser regression checks

[Executed measurements](agent_evaluation_results.md) cover synthetic workflows/probes, not live-LLM accuracy or real-market validity. Actual paid-provider contract smoke is opt-in and remains unexecuted without credentials. Richer free-form synthesis, independent provider/retrieval quality studies, verified OCR/table extraction and broader source coverage are future research; production hardening remains Phase 6.

## Phase 5 — optimization and governance

CVXPY minimum variance with long-only, position/sector/turnover constraints and transaction costs; policy checks; evidence-grounded reports; trace and model/data versioning; safety evaluation.

## Phase 6 — production hardening

Identity/authorization, encrypted durable credential storage, session and provider rate limits, retention/backup policies, performance and adversarial testing, deployment observability, CI/CD, and operational runbooks. No execution/trading scope is authorized.
