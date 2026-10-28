# Deployment

Stage D is being verified locally. Do not treat this document or an image build alone as production readiness; the final executed matrix belongs in `production_readiness.md` after the remaining stages.

The hardened configuration is `infra/compose.production.yml`. The original root Compose file remains a loopback-only development compatibility stack. Both now use a separate one-shot migration service; API and worker startup never run migrations. Never automatically downgrade populated identity/storage/job schemas. Preserve a coordinated backup and use authorized forward recovery.

## Local production-style setup

Use Docker Compose v2, Python 3.12+ for provisioning scripts and a private directory. No cloud service or paid provider is needed. Generate new local-only random credentials and an external Fernet keyring; values are never printed:

```bash
backend/.venv/bin/python infra/provision_local.py --output-dir "$PWD/artifacts/phase6/deploy-secrets"
export VANTAGE_SECRET_DIR="$PWD/artifacts/phase6/deploy-secrets"
export BUILD_COMMIT="$(git rev-parse HEAD)"
docker compose -p vantage-phase6 -f infra/compose.production.yml build --no-cache backend frontend proxy
docker compose -p vantage-phase6 -f infra/compose.production.yml up -d --wait
```

On native Linux, local bind-mounted secret files must be readable by their designated container UIDs. The provisioning script's explicit `--container-readable` option creates read-only 0444 files **inside its mode-0700 private parent** for this local Compose fixture. Keep that parent private. An actual secret manager should mount service-owned 0400/0440 files instead. This is not managed-secret/KMS validation. Docker Desktop's bind-mount permission behavior differs from native Linux. Existing directories are never overwritten.

The app and workers run UID 10001, frontend UID 1000, PostgreSQL UID 70, Redis UID 999 and proxy UID 10001. Root filesystems are read-only, capabilities dropped and no-new-privileges enabled. Writable temporary areas have explicit size and ownership; source/model/document/object/database/broker/proxy certificate data live on separate named volumes. CPU, memory, process and bounded log-file limits are explicit. Do not mount the Docker socket in application containers.

PostgreSQL and Redis use an internal network with no host ports. Runtime SQL uses a non-superuser, non-creator `vantage_app` with table DML privileges; only the one-shot migrator receives the distinct owner/superuser connection. Redis uses a mounted ACL and persistent AOF with no eviction. API/workers have an outbound network for explicitly consented configured providers; no external calls occur with absent credentials. Static edge subnet 172.29.123.0/24 identifies the sole trusted forwarding proxy; change both the subnet/proxy IP and the Uvicorn trust setting if this conflicts with the host's routes. Never trust arbitrary forwarded client addresses.

Only `127.0.0.1:8443` is exposed. The proxy handles `/api` directly and forwards remaining requests to the standalone Next server. Caddy access logs are disabled and structured error logging removes request, message, error and upstream fields that can contain private URLs/headers. Backend access logs and HTTP-client URL logs are disabled. Application-generated IDs and safe structured events are the diagnostic boundary.

## TLS and identity

The local configuration uses [Caddy internal TLS](https://caddyserver.com/docs/caddyfile/directives/tls), with its CA/certificate material persisted privately. Export only the public root certificate for a temporary verification client:

```bash
docker compose -p vantage-phase6 -f infra/compose.production.yml cp proxy:/data/caddy/pki/authorities/local/root.crt artifacts/phase6/local-root.crt
curl --cacert artifacts/phase6/local-root.crt https://localhost:8443/api/health
```

The task does not install a CA into the user's system trust store or expose the application publicly. Browser tests may explicitly ignore the untrusted *local test CA* while a separate HTTPS client verifies the certificate against the exported root. External domain ownership, public CA issuance, production routing/firewalls and hosting are not executed. `Caddyfile.production.example` expects operator-provided domain/certificate/key settings; it is a template, not an external deployment claim. See [Compose secret mounts](https://docs.docker.com/compose/how-tos/use-secrets/) and [service hardening settings](https://docs.docker.com/reference/compose-file/services/).

`ENVIRONMENT=production` fails startup unless durable authentication, Secure cookies, closed registration/docs, explicit HTTPS origin, mounted PostgreSQL/Redis credentials, authenticated broker, external versioned master keyring, required Linux document sandbox and Celery are configured. Secrets can use backend-only `*_FILE` settings for database, Redis and optional Kite/market/LLM keys; conflicting value/file settings fail explicitly. Secrets are absent from browser/build arguments and image layers. Source/build revisions are image labels and explicit runtime metadata; pinned base-image digests and a separately derived runtime lock exclude test/lint packages.

Provision accounts through the trusted operator CLI; passwords are privately prompted:

```bash
docker compose -p vantage-phase6 -f infra/compose.production.yml exec backend python -m app.auth.admin create-user user@example.com
```

Registration is disabled in this production-style stack. The separate local development journey verifies registration; operator provisioning is the production identity model. No role is inferred from signup or a broker account. Use independent reviewer assignment for research approval.

## Validation and recovery boundaries

`backend/scripts/deployment_smoke.py --ca-file artifacts/phase6/local-root.crt` runs the synthetic HTTPS risk/ML/PDF/agent/optimization/export journey, logs out, restarts runtime services, logs in, verifies saved hashes and risk/ML/optimization reproduction, and denies another platform administrator access to financial resources. It writes a new mode-0600 ignored identity/evidence file for subsequent disposable restoration verification. `--verify-only --identity-file ...` reuses that proof. No paid calls or real financial data are used.

Worker/container readiness checks prove a responsive local service with database/broker access, not completion of every future task. Actual numerical/job evidence is checked separately. Volume ownership must be migrated explicitly before attaching an old differently owned volume; never delete old data to fix permissions. Financial artifacts retain their original runtime/version provenance. A model created under another numerical/Python runtime may require that original environment; incompatible reproduction must return a typed error, never silently relabel the model.

Coordinated encrypted backup, actual disposable restore, infrastructure monitoring, load measurements, dependency/container scans and the final end-to-end browser journey are subsequent gates. No regulatory certification or blanket public/institutional production approval is implied.
