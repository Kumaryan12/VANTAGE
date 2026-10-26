# VANTAGE engineering conventions

VANTAGE is a read-only portfolio risk and research application. Phase 1 is the current scope.

- Keep numerical finance in `backend/app/risk`; never calculate risk in the UI or an LLM.
- Never fabricate real prices, API results, backtests, or test outcomes. Label synthetic data throughout.
- Do not add order submission, shell tools for agents, or client-side broker secrets.
- Real holdings must never fall back to demo history. Missing coverage is a typed error.
- Keep source, adjustment, currency, observation date, retrieval time, and content hash with history.
- Tests are required for meaningful financial calculations and adapter error/security behavior.
- Use Python 3.11+, FastAPI/Pydantic, SQLAlchemy/Alembic, NumPy/Pandas, and Next.js/TypeScript.
- Add dependencies only for implemented functionality. Future ML, RAG, agents, optimization, and stress testing live in the roadmap.
- Use `backend/.venv/bin/pytest backend/tests` and `backend/.venv/bin/ruff check backend` from the repository root.
- Frontend checks: `cd frontend && npm run lint && npm run typecheck && npm run build`.
- Local startup and database migration commands are in README.md. SQLite is a local fallback; PostgreSQL is the Compose deployment database.
- Never commit `.env`, credentials, private holdings, uploads, local databases, or browser artifacts.
- Do not log query strings, uploaded data, upstream responses, or authentication tokens.
- Prefer explicit validation errors to silent alignment, filling, or unit/currency assumptions.
