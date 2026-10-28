# Durable authentication

Phase 6 Stage A uses maintained `pwdlib` Argon2id hashing and standard opaque server-side sessions. No JWT or new cryptographic algorithm is implemented. Accounts are identified by UUID and a normalized email login identifier. Local registration does not verify email delivery and never grants privileged roles; production deployment uses explicitly administrator-provisioned accounts. No paid identity provider is required.

Passwords require 15–128 characters, reject obvious common/repetitive strings and the email name, and are salted/encoded by Argon2id. This small built-in check is not an exhaustive breached-password corpus. Login verifies a dummy Argon2id hash for unknown accounts and returns the same error for absent, incorrect or suspended accounts. SQL-backed atomic counters limit login per account (10/15 minutes) and peer address (50/15 minutes), registration (5/hour), password changes and recovery. Proxy trust configuration must prevent forged forwarded addresses. No password, auth token or private payload belongs in logs, URLs or localStorage.

`vantage_auth` is an opaque random 256-bit cookie; SQL stores its SHA-256 hash, UUID, user/scope foreign keys, expiry, idle last-seen and revocation. Cookies are HttpOnly, SameSite=Lax, path `/`, no broad domain, and Secure when HTTPS is configured. Default lifetime is 12 hours, idle timeout 60 minutes; bounds are explicit settings. Each request validates user activity, session revocation/expiry/idle timeout and scope ownership. Invalid auth cookies never fall back to guests. Login, explicit rotation, workspace change, legacy adoption and password change rotate sessions. Logout/revocation/suspension and password recovery invalidate applicable sessions. The account UI clears cached research and fully reloads on identity/workspace changes; persisted browser history triggers reload.

## Account provisioning and recovery

Trusted operators, not agents, can provision accounts and assign roles:

```bash
backend/.venv/bin/python -m app.auth.admin create-user administrator@example.com --role PLATFORM_ADMIN
backend/.venv/bin/python -m app.auth.admin grant-role reviewer@example.com --role RESEARCH_REVIEWER
```

Passwords are prompted privately, not passed in command arguments. Account recovery uses a cryptographically random, expiring, single-use capability whose hash alone is stored. The operator must verify the person out of band and create a new mode-0600 token file in a trusted private directory:

```bash
backend/.venv/bin/python -m app.auth.admin issue-recovery user@example.com --output-file /private/approved-directory/recovery-token
```

The token is never printed to server/stdout logs or returned by a public lookup endpoint. Deliver it through an independently trusted channel, then use Account & Security → Account recovery. It expires in 15 minutes and revokes all sessions after use. There is no automatic email delivery, hosted recovery guarantee or arbitrary lost-workspace recovery endpoint. Operator host/database access is a high-trust administrative boundary.

## Ownership-preserving upgrade

Migration 0009 backfills existing owner keys as **unclaimed ownership scopes**, adds durable users/sessions/RBAC/audit and owner foreign keys, and does not rewrite financial payloads, immutable hashes, source IDs or artifact paths. A new user gets a new personal scope. Local guest mode remains explicitly temporary for backward compatibility; production requires authentication.

Legacy adoption requires both authenticated identity and the still-live original in-memory `vantage_session` cookie. The backend atomically binds its unclaimed scope to that user, audits the proof, invalidates the legacy session, rotates the authenticated session and selects that workspace. Different scopes stay separate; no deduplication/hash collisions or implicit merging. Registered users can select only their own persisted workspaces.

**A pre-upgrade process that already lost its in-memory sessions cannot establish proof from the cookie alone.** Restart/expiry before adoption makes automatic recovery unavailable. No filename, portfolio/content match or administrator financial-data privilege substitutes for possession. Unclaimable orphan records remain private under retention policy. A recovered durable account can re-login after restart and retrieve its owned scopes without legacy memory.

Migration was tested on genuine legacy schemas and a disposable restored PostgreSQL database containing 19 financial tables / 14,082 unchanged rows. Empty identity schemas can be downgraded for migration regression; populated identity/security data is forward-only and requires coordinated backup restoration to revert. Never run destructive automatic rollback in deployment.

The actual two-uvicorn-process PostgreSQL restart smoke is `backend/scripts/identity_smoke.py`; it saves risk/optimization, logs out, stops/restarts the server, re-authenticates, retrieves identical outputs, reproduces saved inputs and denies a second user. Its outputs are synthetic private fixtures under ignored artifacts. Run after migration using a disposable configured database.

Broker identity remains separate: OAuth state is hashed, expiring and atomically single-use. Stage A keeps broker access tokens in process memory; encrypted durable broker storage is a subsequent Stage B gate. Being signed in to VANTAGE never proves current broker authorization.
