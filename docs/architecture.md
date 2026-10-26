# Architecture and implementation plan

## Phase 1 vertical slice

1. Establish conventions, source policy, quantitative definitions, and API contracts.
2. Implement a pure NumPy/Pandas risk package, deterministic versioned demo fixtures, and independent numerical tests.
3. Add typed broker adapters, validated historical imports, persistence, and FastAPI endpoints.
4. Add server-side Kite authentication with opaque, expiring browser sessions; expose read-only holdings, positions, margins, and instrument metadata.
5. Add independent Alpha Vantage adjusted-history, FRED macro, and Frankfurter FX adapters with explicit configuration and upstream errors.
6. Build a Next.js dashboard with working source selection, portfolio/risk views, import controls, charts, and error states.
7. Verify tests, static checks, frontend production build, and end-to-end demo; document evidence and remaining limitations.

## Boundaries

Browser → Next.js same-origin `/api/*` proxy → FastAPI → broker/history/provider services. The risk package has no network or database dependency. FastAPI validates and serializes results. SQLAlchemy stores history datasets and risk-run audit records. Alembic owns schema migrations. PostgreSQL is the deployment target; SQLite supports credential-free local development and tests.

Demo holdings and prices are immutable checked-in synthetic fixtures. Kite snapshots are fetched on demand; Phase 2 persists normalized snapshots when a risk/stress run is saved. Broker tokens stay only in an expiring in-memory server-side session store; process restart requires reauthentication. A single backend worker is required until an encrypted shared session store is implemented. Browser cookies contain opaque random identifiers only. No trading routes exist.

History datasets are session-owned; imported real history can be selected only with Kite mode. Full-date alignment is strict: all held instruments must share the exact observation dates. No forward fill, price invention, or automatic venue mapping. Every history has provenance and a SHA-256 content hash. Risk runs persist input hashes and methodology versions; legacy Phase 1 runs do not persist quantities. Phase 2 explicitly persists private immutable snapshots under session ownership for replay.

Additional APIs are optional. Alpha Vantage requires an explicit provider-symbol-to-canonical-instrument mapping and entitled adjusted daily data. FRED and Frankfurter provide context only; neither feeds risk calculations. FRED responses retain vintage dates and must not be treated as point-in-time-safe model features without further release-calendar work.

## Deployment boundary

This is a local single-user application, not a public multi-tenant service. Compose isolates PostgreSQL and binds web/API ports to loopback. Before public deployment: add identity, durable encrypted sessions, access policies, rate limits, retention, backups, TLS, and operational monitoring. See security.md and roadmap.md.


## Phase 2 extension

The original `/api/risk` and broker/auth/import endpoints remain compatible. A new `/api/v1/risk` router calls a single comparison service for historical, Gaussian and Monte Carlo risk. Pure numerical modules share confidence/units/weight validation; no finance is calculated in route handlers or the frontend. An explicit identity-shrinkage option and PSD diagnostics apply consistently to Gaussian risk, simulation and Euler attribution.

Alembic migration 0002 adds `portfolio_snapshots` and `risk_input_artifacts` and extends `risk_runs` with schema version, kind, parameters, and foreign keys. Artifacts contain selected dated prices and provenance, not simulation matrices. Content hashes cover snapshots, artifacts and normalized model parameters. Replay rehydrates immutable inputs without calling a broker or provider, records a new run, and reports numerical/hash agreement. Old Phase 1 rows remain intact and individually readable but cannot be replayed.

A bounded semaphore permits one advanced calculation per backend process; API simulations are capped at 100,000 and five million asset draws. Vectorized synchronous calculation is sufficient for these bounded requests. Run list pagination and owner filtering execute in SQL. Public multi-user identity, durable encrypted sessions and quotas remain Phase 6 requirements; existing expiring browser sessions still define private ownership.

Stress calculations use direct per-position P&L or fixed-initial-allocation buy-and-hold replay. Historical scenario history may be older than the current estimation dataset and has independent provenance. Missing current reference history does not fabricate VaR: the comparison is explicitly unavailable. Real named events cannot use synthetic data. No estimated factor exposures are invented.

The frontend reuses the existing sidebar, metric/panel/table patterns, Recharts, and query client. Risk Analytics adds a calculate-and-save comparison, histogram, attribution and audit evidence; Stress Testing adds executable scenario forms and impact inspection; Risk Runs provides owned pagination, comparison, saved-snapshot inspection, and replay. Existing portfolio/overview/source views remain functional.

Relative SQLite file URLs resolve against the repository root, so Alembic, root backend startup and frontend-launched browser-test processes use the same database. Absolute and in-memory SQLite URLs are preserved.


## Phase 3 extension

`app/ml` separates contracts, immutable dataset capture, point-in-time features, actual statistical/boosted models, evaluation, pure walk-forward execution, private artifacts, report rendering and persistence services. `/api/v1/ml` supplies typed asynchronous jobs and owned evidence. The worker consumes a saved portfolio snapshot and dated artifact without brokerage/network access, then atomically saves compact forecasts/model metadata. Migration 0003 adds four registry tables, preserving migrations 0001/0002 and legacy APIs.

A one-job background executor and explicit interrupted-job state support the current single-process local deployment. Model text/JSON lives outside relational rows in a checksummed persistent volume; database and artifact backups must remain consistent. Governance is explicit and audited, never metric-selected automatically. Existing ephemeral browser ownership remains a recovery limitation. The research frontend consumes only backend metrics/series/explanations; Phase 4 agents remain absent. See [research protocol](research_protocol.md) for component conventions, storage and scientific limits.
