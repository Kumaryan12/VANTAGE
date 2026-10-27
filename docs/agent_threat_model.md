# Financial investigator threat model

## Trust boundaries

The browser's opaque session authenticates the existing local owner. User questions, documents and tool/provider text are untrusted data. Financial authority is the existing tested backend service, not an LLM. The registry injects owner/mode/snapshot/dataset scope and revalidates every typed argument. Provider keys remain backend-only and HTTPS hosts are fixed in adapters. The parser has bounded resources but is not a complete operating-system security sandbox.

| Threat | Enforced control | Remaining limit |
| --- | --- | --- |
| Cross-session access | Owner checks on jobs, tools, models, filings, chunks, reports and downloads; filter before keyword/vector scoring | Ephemeral sessions have no durable recovery; local admin/DB operators remain trusted |
| Prompt injection in PDFs | Document content is data; strict tool allowlists by intent; no execution/SQL/shell/trading/governance capabilities; final schema has no arbitrary financial prose | Semantic relevance is imperfect; live-provider compliance/quality is unmeasured |
| Fake values/units/dates | Structured authoritative facts, sealed evidence, mandatory comparison/scenario facts, deterministic equality checks and P&L reconciliation; invalid answer rejected | Correctness of input prices/source assertions is not guaranteed |
| Fake citations | Exact authorized retrieved quote, real page/chunk and hash revalidation | Extraction may misorder complex PDF/table text; user can inspect original |
| Exfiltration | No arbitrary URL tools; fixed provider hosts, explicit external-processing consent, redaction and minimized evidence | Redaction is pattern/config based, not complete DLP; external provider policies apply |
| Secrets in logs/history | No raw prompts/provider payloads/credentials logged; known credentials, bearer/key/password/database-URL patterns redacted | Arbitrary unknown sensitive text may not match patterns; documents are private plaintext storage |
| Malformed/large uploads | Bound complete stream/file/pages/text/chunks, separate parser process, CPU/wall/Linux memory limits, no active/encrypted content | No full malware scanner or OS sandbox; macOS lacks the Linux address-space cap |
| Infinite/costly jobs | Single interactive worker, tool helper slot, strict step/tool/time/context/token bounds, one transient provider retry, quotas | Session-local rate limits can be bypassed with new identity; not public-deployment protection |
| Cancellation/restart | Cancellation event, no subsequent tools/published late answer; explicit interrupted state | In-flight bounded requests/calculations may finish; audit runs can already exist |
| Deleted source reuse | Remove index/vectors/file and purge persisted copied passages/quotes; mark old citations unavailable | Not forensic erasure of backups/DB pages or every historical search argument |
| Model/portfolio mutation | No governance or portfolio editing tools; append-only calculation audit records | Separate controlled governance API still exists for explicit user actions |
| Misleading evaluation | Versioned 60-case fixture set, fixed thresholds, per-case failures and denominators, explicit demo/probe labels | Curated regression tests are not unbiased live-AI accuracy or real-market validity evidence |

No institution-grade production readiness is claimed. Durable encrypted identity/secrets, distributed scheduling, hardened parser sandbox, global quotas, retention/backups, TLS operations and deployment adversarial assessment remain Phase 6.
