# API contracts — Phase 1

OpenAPI at `/api/docs` is the authoritative typed contract. Errors have `error: {code, message, details}` and `request_id`.

| Route | Behavior |
| --- | --- |
| GET /api/health | Database readiness; 503 on failure |
| GET /api/session | Issue/reuse opaque session; report Kite configured/connected status |
| GET /api/portfolio?mode=demo\|kite | Validated holding snapshot with weights, source, retrieval and valuation dates |
| GET /api/risk?mode=…&confidence=0.95&window=252&dataset_id=… | Deterministic risk calculation; store audit record; 422 for missing/ineligible history |
| GET /api/history | List only this session's real historical datasets |
| POST /api/history/import | Multipart file + source + adjustment; validate/persist CSV or Parquet |
| POST /api/history/alpha-vantage | Explicit canonical/provider symbol mapping + currency attestation; import adjusted history |
| GET /api/sources | Configured provider capabilities and limitations (no credentials) |
| GET /api/context/fx?base=USD&quote=INR | Frankfurter daily reference context with provenance |
| GET /api/context/macro?series_id=VIXCLS&vintage=YYYY-MM-DD | FRED observations with explicit vintage (today if omitted) |
| GET /api/auth/kite/login | Redirect to official Kite login after issuing session-bound state |
| GET /api/auth/kite/callback | Validate state, exchange request token server-side, redirect to dashboard |
| POST /api/auth/kite/logout | Clear/revoke authorized broker session |
| GET /api/kite/positions | Read-only positions, excluded from holding-portfolio risk |
| GET /api/kite/margins | Read-only broker account margin snapshot |
| GET /api/kite/instruments?exchange=NSE | Read-only instrument catalog, capped results |

No trading routes. Live-only routes require an authorized broker session. Data imports require a same-origin browser session but no broker credentials. A real dataset is never eligible for Demo Mode and synthetic data is never eligible for Kite Mode. FRED/FX context is never merged into risk returns. API provider failures use 502/503 with structured errors; authentication failures use 401; session ownership failures use 404.

## Phase 2 — `/api/v1/risk`

All Phase 1 routes remain. Phase 2 uses strict Pydantic schemas (unknown fields rejected), the existing HttpOnly session/ownership checks, structured errors, and backend-only calculations. OpenAPI contains nested result schemas, units and bounds. Every new analysis/stress response contains its saved `run_id`, immutable snapshot, normalized parameters, calculation/valuation timestamps, input/source hashes, model version, runtime versions, assumptions and warnings.

| Method and route | Request / response |
| --- | --- |
| POST `/analysis` | `AnalysisRequest` → 201 `AnalysisResult`, complete three-model comparison |
| POST `/var`, `/expected-shortfall`, `/monte-carlo` | Aliases of the same comparison service; complete validated outputs and one saved run, not duplicated calculations |
| GET `/contributions` | mode/dataset/confidence/window/shrinkage query → 200 complete comparison including Euler attribution; also persists its run |
| POST `/stress-test` | `StressRequest` → 201 `StressResult`, position/sector P&L, mappings, assumptions, optional eligible current VaR/ES reference |
| GET `/scenarios` | mode and optional historical dataset ID → named windows, availability and explicit reason; no hardcoded shocks |
| GET `/runs?mode=demo&limit=20&offset=0` | Owner-filtered Phase 2 summaries, database pagination; limit 1–100 |
| GET `/runs/{id}` | Owned saved result; legacy Phase 1 IDs are readable but not replayable |
| POST `/runs/compare` | 2–4 distinct `run_ids` of the same Phase 2 kind → INR risk/P&L deltas and comparability warnings |
| POST `/runs/{id}/replay` | Verify owned snapshot/artifact/parameter hashes and methodology version, calculate without network access, save a new run, report input/numerical agreement |

Example analysis body:

```json
{"mode":"demo","confidence":0.975,"window":252,"simulations":10000,"seed":42,"shrinkage":0.1}
```

`mode` defaults to demo. `dataset_id` is mandatory for current real-portfolio estimation and forbidden for demo. Confidence range .90–.995; return window 60–1260; simulations integer 2,000–100,000; unsigned 32-bit integer seed; shrinkage 0–1. Confidence is decimal, not percentage. Monte Carlo requests are limited to five million asset draws; one advanced calculation can run at a time per backend process. Means and covariance are always fitted by validated services, not supplied arbitrarily by the frontend.

Results expose historical/Gaussian/Monte Carlo VaR and ES in INR plus decimal portfolio-return equivalents; daily and annualized volatility; full selected covariance/correlation; source/window metadata; component/marginal/percentage volatility contributions with sector reconciliation; histogram, P&L/return/terminal-value quantiles; conditional asymptotic Monte Carlo SEs and sampling intervals. Undefined zero-volatility contributions/correlations and singular condition numbers are null, never fabricated zeros.

Example hypothetical body:

```json
{"mode":"demo","kind":"hypothetical","name":"User-defined sector shock","market_shock":-0.1,"sector_shocks":{"Technology":-0.2},"security_shocks":{}}
```

Shocks range −1 to +5 in simple-return units. Replacement order: security > sector > broad. Missing broader mapping means unchanged. Unknown targets and empty scenarios are errors. No factor sensitivities are invented. Hypothetical P&L does not require historical data; an unavailable current VaR reference is explicitly reported. Invalid ownership or data integrity is always an error, never ignored as missing reference coverage.

Demo synthetic replay body:

```json
{"mode":"demo","kind":"historical","name":"Synthetic fixture replay","scenario_id":"synthetic_2026"}
```

`scenario_id` is exclusive with explicit `start`/`end`; historical replay cannot accept hypothetical shocks. For real mode, use exact dates or a covered named event and an optional independently owned `scenario_dataset_id`; `dataset_id` independently selects fresh current-estimation history for comparison. A historical scenario dataset may be old but cannot extend beyond the saved valuation date. Missing exact endpoints or cross-asset coverage produces `SCENARIO_COVERAGE`/alignment errors. Synthetic mode returns `scenario_kind=synthetic_replay` and disables actual market events.

Relevant errors: 401 broker authorization/expiry; 404 unauthorized or absent dataset/run (same response to avoid existence leaks); 409 source/input integrity or unavailable model version; 422 invalid confidence, weights, covariance, sample, date, shock, or scenario coverage; 503 bounded engine busy. Validation errors omit raw inputs and secrets. No public order/execution endpoint exists.
