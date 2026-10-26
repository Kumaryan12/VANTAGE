# Phase 4 foundation audit and acceptance protocol

Audited `f8f68aa66b96c465849c8f215fddf8b8b609d76e` on 2026-10-26, starting with a clean working tree. SQLite and PostgreSQL were at migration 0003. Baseline: 169 backend tests and Ruff passed; frontend lint, types and production build passed. Existing browser and database integration results are recorded in verification.md after execution.

## Reusable boundaries

- `risk/advanced.py`, `stress_service.py`, `records.py` provide validated, saved analytical results without duplicating mathematics. `api/routes.py` resolves broker snapshots using the current opaque session, and `risk/artifacts.py` preserves immutable inputs.
- `ml/service.py` enforces owner-scoped experiment/model access, computes matched evaluation windows, reloads checksummed model text and exposes actual explanations. It must remain the source for investigations, with missing/unauthorized experiments explicit.
- The original Phase 3 report is based on 504 synthetic frozen-current-weight retrospective returns, 100 final targets, and code `b971c18`. Rolling had lower QLIKE than LightGBM; paired intervals include zero, 99% exceptions are zero, and the high-volatility test regime is empty. Preserve that report and its original provenance.
- SQLAlchemy/Alembic and the existing same-origin API boundary are suitable for additive investigation/document/evaluation records. Existing browser sessions expire and disappear on restart. Keep one backend process; do not redesign identity or distributed workers.
- Reuse Next.js navigation, panels, typed API client, TanStack Query and table/chart conventions. UI calculations must not become a second financial engine.

## Risks and implementation decisions

Use one explicit typed state machine, bounded steps/tools/time/retries, owner checks inside every tool, and a backend allowlist. No shell/SQL/trading/governance tools. LLMs may choose approved calls and reference verified facts/quoted passages; final numerical tables and source limitations are composed deterministically. Reject unsupported values/units/dates/citations and seal tool evidence with hashes. Do not expose hidden reasoning or persist raw provider prompts.

Provider integration is backend-only and opt-in; absent credentials show **AI provider not configured**. Credential-free deterministic workflows are labeled as demonstrations. External processing requires explicit request consent and only bounded/redacted relevant evidence. Provider tests use mocks; live-provider financial validity remains unmeasured without an opt-in actual call.

PDFs are private untrusted inputs: bound size/pages/text/chunks/time, isolate parsing in a subprocess, retain page references, never follow embedded instructions/links, and do not infer unreliable tables. Start with keyword retrieval, then add opt-in embeddings and an owner-filtered bounded cosine vector index with hybrid rank fusion. No unrestricted scraping.

## Incremental milestones

1. Typed graph, provider interface, authorized research tools, deterministic verification, persistence, and a working model-comparison API/UI slice; test it before document work.
2. Private PDF ingestion, deletion, page-aware chunking, keyword and optional embedding retrieval, citation validation.
3. Integrate portfolio/risk/stress/document tools and bounded multistep investigations.
4. Execute a versioned golden suite of at least 60 cases; retain per-case failures, traces, timings and actual provider/demo labels.
5. Complete library/evidence/history/evaluation UI, PostgreSQL/browser regression checks and documentation.

## Evaluation thresholds fixed before execution

For the deterministic fixture/probe suite: task success >=95%, exact authorized-tool and numeric/citation checks >=98%, all cross-owner/action-execution/secret-leak probes blocked (100%), zero unsupported published financial values, and <=8 tools/<=24 graph transitions per investigation. No live-LLM accuracy claim derives from this suite. Record numerical/retrieval/citation denominators and inapplicable measurements separately; tokens/cost are unavailable for deterministic runs. A failing case remains visible and blocks a completion claim if a critical safety threshold fails.
