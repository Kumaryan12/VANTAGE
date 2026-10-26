# Security boundary

Local single-user read-only analysis. No order, GTT, execution, arbitrary URL fetch, shell, or LLM endpoints.

Kite API secret and access tokens stay on the backend. A cryptographically random, HttpOnly, SameSite=Lax cookie identifies an in-memory expiring session. Tokens are never placed in the cookie, database, frontend bundle, browser storage, or logs. OAuth-style login uses a single-use random state bound to the initiating browser session with a ten-minute expiry. Callback uses Kite `redirect_params`; failure requires a fresh login. Session expires within 12 hours and Kite can invalidate earlier; invalid token responses clear local broker access. Logout invalidates the remote token before discarding it where possible, and always clears local access. Restart invalidates all sessions; run one backend worker.

Same-origin mutation checks reject unexpected Origin headers; browser fetch-metadata checks reject cross-site mutations. CORS is not opened. Next.js proxies only to configured backend; all provider hosts are hardcoded HTTPS. Query strings and upstream exception strings are never logged, including the token-bearing callback. Sensitive responses use no-store and a restrictive referrer policy. Uploads have byte/row/instrument limits and are parsed from memory; no user-controlled paths are accepted. Session ownership is enforced for history selection. Expired session datasets are orphaned until manual retention cleanup (not exposed to subsequent users).

Configure COOKIE_SECURE=true behind HTTPS. Keep DATABASE_URL, KITE_API_SECRET, ALPHA_VANTAGE_API_KEY, and FRED_API_KEY out of source control. Do not expose this app publicly until identity, durable encrypted sessions, quotas, retention, TLS, and audit access controls have been added. PostgreSQL records contain private historical imports; protect the volume and backups.

Kite account credentials are entered only on Zerodha's official website. The UI only receives an opaque session and read-only authorized result data. Account positions/margin snapshots must be treated as private. Provider errors return generic typed messages; raw payloads and URLs containing keys must never be returned.
