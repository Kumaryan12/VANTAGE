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

Demo holdings and prices are immutable checked-in synthetic fixtures. Kite snapshots are fetched on demand and remain in memory. Broker tokens stay only in an expiring in-memory server-side session store; process restart requires reauthentication. A single backend worker is required until an encrypted shared session store is implemented. Browser cookies contain opaque random identifiers only. No trading routes exist.

History datasets are session-owned; imported real history can be selected only with Kite mode. Full-date alignment is strict: all held instruments must share the exact observation dates. No forward fill, price invention, or automatic venue mapping. Every history has provenance and a SHA-256 content hash. Risk runs persist input hashes and methodology versions; private quantities are not persisted.

Additional APIs are optional. Alpha Vantage requires an explicit provider-symbol-to-canonical-instrument mapping and entitled adjusted daily data. FRED and Frankfurter provide context only; neither feeds risk calculations. FRED responses retain vintage dates and must not be treated as point-in-time-safe model features without further release-calendar work.

## Deployment boundary

This is a local single-user application, not a public multi-tenant service. Compose isolates PostgreSQL and binds web/API ports to loopback. Before public deployment: add identity, durable encrypted sessions, access policies, rate limits, retention, backups, TLS, and operational monitoring. See security.md and roadmap.md.
