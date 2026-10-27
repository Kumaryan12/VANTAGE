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

## Phase 5 — implemented local optimization and research governance

- [x] CVXPY/CLARABEL objectives, analytical tests, independent residual/termination validation and explicit infeasibility diagnostics
- [x] Position/asset/frozen/sector/Unknown policies, one-way turnover, symmetric/asymmetric assumed costs
- [x] Matched Phase 2 risk/attribution, actual risk–turnover curves and sourced conditional return frontiers
- [x] Six-axis sensitivity and immutable identical counterfactual stress/reproduction
- [x] Owner-scoped saved jobs/studies, artifact/covariance/result hashes, runtime-aware reproduction and comparable-run checks
- [x] Explicit human research-review lifecycle, eight assessments, evidence gates and event audit; no AI approval
- [x] Eight pinned optimization investigator tools and separate fixed optimization cases
- [x] Functional decision laboratory and governance dashboard, synthetic measured report and regression verification

[Executed report](research/portfolio_optimization_validation.md), [methodology](optimization_methodology.md) and [validation](optimization_validation.md). Synthetic in-sample minima are not evidence of future investment performance. Cash/execution/impact/lot-size constraints, durable reviewer roles and real-market approval are not implemented. Future quantitative research may consider independently validated forecasts, broader eligible universes and discrete allocations, each requiring its own data/methodology review.

## Phase 6 — production hardening

Durable identity and source ownership/recovery; independent reviewer roles; encrypted credential storage; session/provider/compute quotas across processes; data/document/model retention, deletion, backups and tested restore; durable distributed queues and cancellation; hardened parser isolation; performance/adversarial testing; production secret management, deployment observability and operating runbooks. CI already verifies local/PostgreSQL workflows; production deployment/CD and full image-stack validation remain separate. Validate live-provider quality and independent real-market research before making those claims. No execution/trading scope is authorized.
