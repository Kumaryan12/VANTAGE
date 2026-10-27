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

## Phase 3 — `/api/v1/ml`

Strict typed schemas, same-origin session authentication, private owner filtering and existing structured errors apply. No broker execution. Dates are ISO observation dates; variance is decimal return², volatility decimal daily standard deviation, loss/VaR INR at the saved snapshot notional.

| Method and suffix | Behavior |
| --- | --- |
| POST `/train` or `/backtest` | Same controlled four-model workflow; `ResearchRequest` (defaults/bounds in OpenAPI), return 202 `JobSummary` with id; busy capacity 503 |
| GET `/jobs/{id}` | Queued/running/completed/partial/failed/interrupted, progress/stage and typed error |
| GET `/experiments?limit=20&offset=0` | Owner's recent jobs, SQL pagination |
| GET `/experiments/{id}` | Parameters, dataset/protocol/runtime, model ids, matched metrics, warnings and reproduction status |
| POST `/experiments/{id}/reproduce` | 202 new job using immutable inputs and saved parameters after hash/version verification |
| POST `/experiments/compare` | `experiment_ids` (2–4 distinct); require completed results with identical dataset hash/test dates and excluded-date subsets; inspect configs/metrics, no automatic winner |
| GET `/models?experiment_id=…` | Four saved registry models; missing during active/failed pre-persistence jobs is an explicit empty list |
| GET `/models/{id}` | Kind/role/status, configuration/search, refit lineage, metrics, latest unscored forecast, importance/drift, artifacts and governance audit |
| GET `/models/{id}/forecasts?start=…&end=…` | Scored predictions, origin/availability/target dates, actual proxy/return/loss, h/sigma/VaR/exceptions, source/version, features/missing/floor/failure and checkpoint id |
| GET `/models/{id}/metrics?start=…&end=…` | Full matched four-model comparison containing this model; not a mismatched individual score |
| GET `/comparison?experiment_id=…&start=…&end=…` | Shared valid-date metrics, requested/matched/excluded dates, coverage and paired uncertainty |
| GET `/var-backtests?experiment_id=…` | Same comparison/coverage contract; supports start/end |
| GET `/regimes?experiment_id=…` | Fixed training thresholds, dated origin indicators and full-test per-regime metrics |
| GET `/experiments/{id}/series?start=…&end=…` | Backend-generated observed absolute return/loss, all four sigma and 95/99% VaR/exception series, 20-target rolling QLIKE within selected window |
| GET `/models/{id}/explain?target=…` | LightGBM saved-point TreeSHAP, feature values, raw/bias/floor reconciliation and sensitivity; default latest scored target |
| GET `/models/{id}/artifact` | Authorized ZIP of checksum-verified text/JSON checkpoints; unavailable/corrupt files raise errors |
| POST `/models/{id}/governance` | `role`, written `rationale` (>=20 chars), `acknowledge_limitations:true`; audited manual review; champion needs complete >=100-common-date model |
| GET `/experiments/{id}/report` | `{markdown: …}` generated from saved actual evidence; unavailable sections explicit |

Training supports expanding/rolling estimation, bounded history/train/validation/test windows, refit cadence, rolling 20/60, fixed EWMA lambda, variance floor, deterministic LightGBM search/seed/rounds/learning rate, basic/full features and optional aligned context dataset/benchmark instrument. No future or mixed-mode context is accepted. See [research protocol](research_protocol.md) for the exact boundaries.

A sample request is `{ "mode":"demo", "scheme":"expanding", "test_size":100, "max_trees":120, "search_candidates":3, "seed":42 }`. Poll the returned id, then request its models/comparison. Failed fits remain null with failures; low-sample statistical tests are null with reasons rather than zero. Model origins use observed dates; the unscored final prediction has no invented next-date. Authentication/ownership errors remain 401/404, invalid inputs/windows 422, ineligible/not-ready evidence or integrity/version failures use structured errors (typically 409). Jobs are bounded to one per backend process; interrupted jobs do not silently resume.

## Phase 4 — financial investigations and documents

All new routes use existing same-origin mutation protection, opaque session ownership, structured errors and no-store responses. No arbitrary account/SQL/shell/URL/trading/governance input is accepted. Models in OpenAPI are the typed contract; flexible evidence/registry metadata are distinct from strictly verified financial facts.

| Method and route | Request / response |
| --- | --- |
| GET `/api/v1/agent/status` | Provider/model availability, explicit no-key message, labeled demo and embedding capabilities; never credentials |
| POST `/api/v1/agent/investigate` | Strict `InvestigationRequest`; 202 job id/status/stage. `engine:demo` is deterministic; `engine:llm` needs configuration and `external_data_consent:true` |
| GET `/api/v1/agent/investigations?limit=20&offset=0` | SQL-paginated current-session summaries |
| GET `/api/v1/agent/investigations/{id}` | Owned state, original context/provider/workflow, usage/budgets, verification, error and validated answer |
| POST `/api/v1/agent/investigations/{id}/cancel` | Request cancellation; in-flight bounded work may finish but its output cannot publish an answer |
| GET `/api/v1/agent/investigations/{id}/trace` | Ordered concise activity and timings; no private chain-of-thought |
| GET `/api/v1/agent/investigations/{id}/tool-calls` | Sanitized strict-call arguments, actual name/status/timing/error/evidence reference |
| GET `/api/v1/agent/investigations/{id}/evidence` | Owned checksummed source records, facts, provenance and bounded data |
| POST `/api/v1/research/documents` | Multipart `file`, `source`, `permitted:true`; optional company/reporting period/publication date and semantic/external-consent flags; 202 processing record |
| GET `/api/v1/research/documents?company=…&limit=20&offset=0` | Owned active library records and extraction/index status |
| GET `/api/v1/research/documents/{id}` | Version/hash/metadata/status/page and chunk counts/errors |
| DELETE `/api/v1/research/documents/{id}` | Remove private file/index/vectors, tombstone metadata, purge copied passages/quotes and mark old citations unavailable |
| GET `/api/v1/research/documents/{id}/file` | Owner-authorized checksum-verified PDF attachment, sandbox/CSP/nosniff headers |
| GET `/api/v1/research/documents/{id}/chunks/{chunk_id}` | Exact authorized page/section/text/hash for source inspection |
| POST `/api/v1/research/search` | Strict query/document IDs/company/limit and optional semantic consent; ranked real passages, method/scores/warnings and index version |
| POST `/api/v1/agent/evaluation-runs` | 202 actual fixed golden suite in an isolated synthetic workspace; no broker data or paid requests |
| GET `/api/v1/agent/evaluation-runs?limit=10` | Owned recent summaries/metrics; case payloads excluded from list responses |
| GET `/api/v1/agent/evaluation-runs/{id}` | Full owned per-case expectations/checks/actual trace/failures and measured aggregate results |

Example investigation: `{"question":"Compare forecasting models on QLIKE and explain limitations.","engine":"demo","mode":"demo","experiment_id":"<accessible-id>"}`. Omitting the experiment chooses only the latest accessible completed/partial experiment in the selected mode; missing coverage never falls back to another session or the checked-in report. Portfolio tools use a captured authorized snapshot. Optional dataset/run/document selections are reauthorized inside tools. Confidence/window/shrinkage controls remain explicit; a typed `scenario` must match mode/dataset and the agent permits direct hypothetical scenarios only.

Bounds: question 8–1600 chars; up to four selected risk runs, twenty documents, eight tools, 24 graph steps and 5–90 seconds (60 default). Tool output cap is 60,000 bytes and timeout eight seconds. Provider context/available usage have independent bounds. No-key live requests return 503 `AI_NOT_CONFIGURED`; invalid consent/arguments 422; busy capacity 503; rate limits 429; foreign records 404; integrity/verification failures typically 409. Jobs persist `queued/running/completed/limited/failed/cancelled/interrupted` rather than inventing completion.

PDF files are limited to 5 MB (multipart stream 6 MB), 100 pages and bounded extracted text/chunks; unsupported/unsafe extraction is reported as failed processing. Semantic indexing and queries require explicit external processing permission; missing semantic coverage/provider failure preserves keyword retrieval with warnings. Exact source quotes and pages are revalidated before an answer is published. Deleted documents cannot support new citations.

The final response is structured: server-composed findings, copied verified claims with units/as-of/source references, exact citations and mandatory limitations. Arbitrary provider financial prose is rejected. See [agent architecture](agent_architecture.md), [tool schemas](agent_tool_contracts.md), [financial RAG](financial_rag.md) and [evaluation protocol](agent_evaluation.md).

## Phase 5 — optimization and local governance

All routes retain browser-session ownership, strict input schemas, no-store responses, same-origin mutation protection and typed errors. No owner ID is accepted as authorization. Numerical/null/error semantics and units are defined in [methodology](optimization_methodology.md).

| Method / route | Contract |
| --- | --- |
| POST `/api/v1/optimization/run`, `/feasibility` | `OptimizationRequest` → 202 saved bounded job; feasible status requires independent checks |
| POST `/api/v1/optimization/frontier` | `FrontierRequest`: base policy plus risk_turnover budgets or explicitly sourced efficient return targets, max 8 |
| POST `/api/v1/optimization/sensitivity` | Base plus up to 8 labeled variations, all windows validated before enqueueing |
| GET `/api/v1/optimization/constraints` | Policy JSON schema, defaults and sleeve/cost/turnover interpretation |
| GET `/api/v1/optimization/runs` | Owned paginated jobs; explicit solver outcomes |
| GET `/api/v1/optimization/runs/{id}` | Saved parameters, actual dataset/covariance/result, immutable references/hashes, versions and warnings |
| POST `/api/v1/optimization/runs/{id}/reproduce` | 202 child run from verified saved inputs without provider access; match/tolerances retained |
| POST `/api/v1/optimization/compare` | 2–4 distinct feasible single runs with identical economic/risk settings; structured mismatch error otherwise |
| POST `/api/v1/optimization/counterfactual` | Saved run/point plus strict Phase 2 `StressRequest`; identical current/proposed outputs and immutable scenario artifact |
| GET `/api/v1/optimization/runs/{id}/counterfactuals` | Owned scenario history with result/version/input integrity checks |
| POST `/api/v1/optimization/counterfactuals/{id}/reproduce` | Recompute identical scenario from verified original artifact and allocation inputs |
| POST `/api/v1/governance/models` | Register owned optimization/forecast source as candidate only |
| GET `/api/v1/governance/models`, `/models/{id}` | Owned registry, original/current evidence, current status and permitted next transitions |
| GET `/api/v1/governance/sources` | Owned Phase 3 model choices for explicit registration |
| POST `/api/v1/governance/models/{id}/review` | Explicit human/research acknowledgements, allowed status, rationale and required eight assessment notes; methodology_research scope only |
| GET `/api/v1/governance/events` | Owned chronological review events; optional owned model filter |

Optimization job status differs from solver status: a completed job can correctly contain an infeasible solution. Partial studies preserve solver failures; failed/interrupted jobs never claim completion. Feasible inaccurate outcomes remain visibly inaccurate. Invalid/uncovered inputs return typed 422, owner failures 404, integrity/comparison/version conflicts 409 and saturated bounded queues 503. No generic 200 response implies financial feasibility.

`InvestigationRequest` additionally accepts either `optimization_run_id` or explicit `optimization_parameters`, never both. Explicit parameters must match investigation source/confidence/window; policy percentages cannot be altered by provider tool arguments. Read-only tools do not expose review/order endpoints.
