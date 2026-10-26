# Phase 1 audit and Phase 2 implementation plan

Audited 2026-10-26 at commit `73fcd8e` before modifying the implementation.

## Reuse

- All 51 baseline Python tests pass. Ruff lint/format pass. Existing frontend lint/type/build checks were run before implementation.
- Valuation uses positive cash-equity quantities and INR prices; current weights sum to one. Sample volatility uses ddof=1 and 252 days/year.
- Historical VaR correctly uses the inverse empirical loss CDF, retaining negative VaR for all-gain samples. Drawdown includes initial wealth. Correlation uses aligned observations and null for undefined entries.
- Independent data adapters, import provenance, strict full-date alignment, seven-day freshness checks, session-owned datasets, read-only Kite authorization, and the existing design system are reusable.

## Extend or correct

- Confidence is restricted to 95%/99%; Phase 2 will validate 90%–99.5%, with at least 60 observations and at least one empirical tail observation. Tail mass below 20 will be flagged as unstable.
- Runs store hashes/results but no immutable snapshot, dated estimation inputs, model parameters, environment version, retrieval API, or replay mechanism. Add snapshot/input records and versioned run metadata without dropping old records.
- Covariance is sample-only, with no explicit numerical diagnostics. Add documented optional linear shrinkage, symmetry/PSD validation, and a spectral square root suitable for singular matrices. Every numerical correction must be recorded.
- Demo/source hashes are recorded but not checked on load. Verify fixture and imported canonical-record hashes to detect input mutation.
- Full-date equality does not certify an exchange holiday calendar or detect a day missing from every asset. Preserve this limitation explicitly; do not invent prices or claim verified exchange continuity.
- Historical scenario coverage requires exact start/end observations and alignment across all holdings; old scenario datasets need not satisfy *current-estimation* freshness. Synthetic fixtures must never be represented as actual historical market events.
- Run IDs and immutable inputs require owner authorization. Existing sessions expire on restart; durable user identity remains outside this phase. Runs remain private and available only to their originating active session.

## Implementation sequence

1. Establish shared validation and units; implement quantile-integral empirical ES and analytical Gaussian VaR/ES with known-case tests.
2. Implement covariance diagnostics/shrinkage, Euler volatility attribution, and seeded correlated Gaussian simulation with spectral PSD sampling and numerical uncertainty estimates.
3. Implement explicit direct security/sector shocks with replacement precedence and fixed-initial-weight buy-and-hold historical/synthetic replay; reconcile every position and sector P&L.
4. Add Alembic migration, immutable portfolio snapshot/daily-return input artifacts, complete model parameters and runtime versions, session-owned run retrieval/comparison/replay. Persist histograms and compact summaries, never full simulation matrices.
5. Add typed Phase 2 endpoints using one shared calculation service while preserving Phase 1 endpoints and broker integration.
6. Extend Risk Analytics; add functional Stress Testing and Risk Runs views using backend outputs exclusively.
7. Verify analytical/numerical/security/integration/browser tests, PostgreSQL migrations, frontend production checks, documentation, and GitHub CI. Commit and push coherent milestones.

No ML forecasting, inferred factor sensitivities, trade execution, or artificial real-market observations are in scope.
