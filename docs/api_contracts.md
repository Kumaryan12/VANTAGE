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
