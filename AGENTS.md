# VANTAGE engineering conventions

VANTAGE is a read-only portfolio risk and research application. Phases 1–3 are implemented; Phase 4 agentic investigations remain planned.

- Keep numerical finance in `backend/app/risk`; forecasting in `backend/app/ml`; never calculate risk or ML metrics in the UI or an LLM.
- Never fabricate real prices, API results, backtests, or test outcomes. Label synthetic data throughout.
- Do not add order submission, shell tools for agents, or client-side broker secrets.
- Real holdings must never fall back to demo history. Missing coverage is a typed error.
- Keep source, adjustment, currency, observation date, retrieval time, and content hash with history.
- Tests are required for meaningful financial calculations and adapter error/security behavior.
- Use Python 3.12+, FastAPI/Pydantic, SQLAlchemy/Alembic, NumPy/Pandas, and Next.js/TypeScript.
- Add dependencies only for implemented functionality. Future RAG, agents, and optimization live in the roadmap.
- Use `backend/.venv/bin/pytest backend/tests` and `backend/.venv/bin/ruff check backend` from the repository root.
- Frontend checks: `cd frontend && npm run lint && npm run typecheck && npm run build`.
- Local startup and database migration commands are in README.md. SQLite is a local fallback; PostgreSQL is the Compose deployment database.
- Never commit `.env`, credentials, private holdings, uploads, local databases, or browser artifacts.
- Do not log query strings, uploaded data, upstream responses, or authentication tokens.
- Prefer explicit validation errors to silent alignment, filling, or unit/currency assumptions.

- Phase 2 calculations share `risk/conventions.py`, `tails.py`, `covariance.py`, `parametric.py`, `simulation.py`, and `stress.py`; API handlers must not duplicate mathematics.
- Loss is -V times one-day simple return. Tail outputs are INR with decimal-return equivalents. Confidence range is .90–.995; historical ES integrates fractional empirical tail mass.
- Gaussian/Monte Carlo/volatility attribution use the same explicitly selected covariance. Record every shrinkage/roundoff correction. Singular PSD matrices are valid; material indefiniteness is not.
- No synthetic data for actual historical market events. Replay uses exact endpoints, fixed virtual adjusted-series units scaled to current initial weights, and no rebalancing.
- Direct shocks replace in security > sector > broad order. Never invent factor sensitivities or sum overlapping shocks.
- Persist compact histograms/quantiles and immutable dated price inputs, never large Monte Carlo draw matrices. Private snapshots now persist, under session ownership and existing retention limitations.
- Replay verifies snapshot/artifact/parameter hashes and model version before recomputing without provider access. Keep migration 0001 and legacy endpoints compatible.
- Apply `backend/.venv/bin/alembic -c backend/alembic.ini upgrade head` after pulling Phase 2. Browser tests require current backend and frontend processes; do not reuse a stale server.
- Run `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` in frontend when installed Chrome is available, or install Playwright Chromium. Include existing Phase 1 and new Phase 2 browser suites.

- Phase 3 forecasts next observed daily portfolio return² under zero mean, with h in decimal variance and sigma=sqrt(h). Current weights are retrospective frozen baskets, never reconstructed account performance.
- Keep features at/before origin, next-day labels available before fitting, training-only imputation and validation-only locked tuning/regime thresholds. Test expanding/rolling refits and future mutation invariance.
- Use real ARCH/LightGBM implementations and checksum-verified text/JSON artifacts outside DB rows. No pickle; authorize every job/model/forecast/artifact and preserve failed predictions as null.
- Compare all four models on common valid target dates. Show sample exclusions, noisy targets, sparse coverage tests and manual documented governance; no automatic champion or synthetic real-market claim.
- Run `backend/.venv/bin/python backend/scripts/research_report.py --smoke` against PostgreSQL after migration 0003, and include the Phase 3 browser suite. The no-flag CLI regenerates the actual research report.
- See docs/research_protocol.md for feature definitions, source availability, queue/storage limits and reproduction tolerances. Do not add Phase 4 functionality during Phase 3 maintenance.
