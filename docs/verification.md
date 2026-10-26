# Phase 1 verification

Checked locally on 2026-10-26 with Python 3.12, Node 26, Chrome, and PostgreSQL 17 in Docker. CI targets Python 3.12 and Node 22.

| Check | Actual result |
| --- | --- |
| `pytest -c backend/pyproject.toml backend/tests -q` | **51 passed**; one upstream Starlette TestClient/httpx deprecation warning |
| `ruff check backend data/sample/generate.py` | Passed |
| `ruff format --check backend data/sample/generate.py` | Passed |
| `pip check` | No broken requirements |
| Frontend ESLint | Passed |
| Frontend TypeScript | Passed |
| Next.js production build | Passed |
| Playwright, `PLAYWRIGHT_CHANNEL=chrome npm run test:e2e` | **3 passed** against real backend/frontend processes |
| PostgreSQL Alembic migration | Applied successfully |
| PostgreSQL-backed readiness, demo portfolio/risk, import, ownership listing, audit persistence | Passed |
| Frankfurter live provider request | Passed with observed/retrieved dates retained |
| Frankfurter live fetch through browser → Next.js → backend | Passed; no uncaught browser errors |
| Desktop and mobile screenshots | Reviewed; 390 px document width at a 390 px viewport |
| `docker compose config --quiet` | Passed |
| Complete Compose backend/frontend image build | Not executed; local startup and containerized PostgreSQL tested |

Browser workflows cover source selection, 95%/99% confidence, window changes, charts/correlations, risk-run JSON download, holding search, account authentication errors without demo fallback, missing FRED-key errors, historical imports, and mobile navigation. An explicit query-parameter regression discovered by the browser suite now has four backend tests.

Browser verification uses a clean session and no broker or keyed-provider credentials. The optional `PLAYWRIGHT_CHANNEL=chrome` uses installed Chrome; CI installs Playwright Chromium. Screenshots are local ignored artifacts at `artifacts/overview.png`, `artifacts/risk.png`, `artifacts/sources.png`, and `artifacts/mobile.png`.

GitHub Actions runs backend checks with a PostgreSQL smoke test and frontend checks with browser tests. Remote execution logs are the source of truth for CI outcomes.

Live broker and keyed-provider access require the owner's credentials and entitlements. Mock contract tests do not imply a successful live authorization or licensed data retrieval.
