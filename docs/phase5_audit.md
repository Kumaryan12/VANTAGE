# Phase 5 audit and implementation protocol

Audited 2026-10-27 at `ab5328f`, starting with a clean working tree and migration 0005. The previously reported Phase 4 results are rerun rather than assumed. Baseline backend: 188 tests and Ruff passed; frontend lint/typecheck/production build passed. Browser/PostgreSQL/golden results are recorded in verification.md after execution.

## Reuse and boundaries

- `risk/service.resolve_prices` enforces owner, source mode, split/dividend adjustment, freshness, exact held-instrument coverage and no future observations. `asset_returns` constructs canonical aligned float64 daily simple returns.
- `risk/covariance` supplies sample ddof=1 and explicit identity-target shrinkage plus symmetry/PSD/rank/correction diagnostics. Preserve these conventions and asset order.
- `risk/tails`, `parametric`, `simulation`, `advanced.attribution_result` and `stress` are the financial authority for current-versus-proposed comparisons. The optimizer must not duplicate VaR/ES/stress mathematics.
- Immutable owner-scoped snapshots/input artifacts and hashes already support replay. Add optimization jobs/results/studies and a local model-review audit after migration 0005; keep earlier records/endpoints compatible.
- Phase 4 supplies typed scoped tools, sealed facts and deterministic financial verification. New tools can calculate/read hypothetical allocations; they cannot relax pinned constraints, invent returns, change governance, edit holdings or execute orders.
- Reuse Next.js panels, query client, tables/charts, navigation and explicit error/provenance patterns.

## Financial contract

Optimize the held **INR equity sleeve**, fully invested and long-only in its existing ordered holdings. Its notional excludes unavailable account cash, derivatives and non-equity positions; those balances are unknown, not assumed zero. No new securities, silent exclusions or sector invention. Unknown sectors remain an explicit group or cause a requested eligibility rejection.

Use CVXPY with explicit CLARABEL settings, annual variance `252*w'Σ_daily*w` and a documented positive common objective scaling. One-way turnover is `0.5*sum(abs(delta weights))`; estimated symmetric/asymmetric research costs are not broker quotes. Penalties multiply turnover/cost fractions in annual-variance units, never raw INR. Expected-return frontiers require a complete explicitly sourced annual return-assumption vector; Phase 3 variance forecasts are not return forecasts.

Independent checks cover finite weights/objective, sum, long-only, position/sector/frozen/turnover/target constraints, and costs. Tiny solver-roundoff canonicalization must be recorded, bounded and rechecked; never silently relax constraints. Infeasible/failed/timeout/inaccurate states remain distinct and cannot become invented allocations. Degenerate/singular objectives can have nonunique, unstable weights even with valid risk values.

## Incremental delivery

1. Pure solver/contracts, analytical cases and independent constraints; working saved/reproduced minimum-variance UI slice with position/turnover controls.
2. Complete practical bounds, sector/frozen constraints, costs/objectives and explicit infeasibility diagnostics.
3. Matched financial comparisons, risk–turnover and explicitly gated return frontier, labeled sensitivity and identical counterfactual stress.
4. Persisted immutable inputs/studies, reproduction, local review statuses and authorized rationale/evidence transitions.
5. Pinned authorized agent tools and optimization-specific evaluation; full decision laboratory and governance UI.
6. Execute numerical/security/API/PostgreSQL/frontend/browser/golden checks, generate an actual synthetic validation report and update all documentation.

The Phase 3/4 reports retain their original provenance and scientific limitations. Synthetic in-sample optimization is not evidence of future investment benefits, and session-bound reviews are not enterprise maker-checker governance. Durable identity, distributed scheduling, retention, hardened deployment and real-provider quality remain Phase 6 or separate validation work.

## Baseline ordering defect found and repaired

All nine baseline browser workflows and Phase 1–3 PostgreSQL smokes passed. The PostgreSQL golden rerun `6a6341d0-ea63-40e4-b2b9-68ea36e38bd9` reported 59/60 tasks and 44/45 tool-order checks: G029's database rows returned search first although the ordered execution trace proved it ran last. SQL had no ORDER BY, so heap/update order was accidentally treated as execution order. Migration 0006 adds nullable legacy/new explicit tool-call sequencing; new calls and retrieval/evaluation use it. Old sequence values remain unknown rather than invented. This changes audit ordering, not expected tool sequences or evaluation thresholds.
