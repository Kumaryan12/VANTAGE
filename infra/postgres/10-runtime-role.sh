#!/bin/sh
set -eu
# Executed only by the official image's trusted first initialization, not an app/agent tool.
# No shell tracing or SQL echo; mounted secrets never enter Compose environment values.
if ! psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --no-psqlrc --quiet --set ON_ERROR_STOP=1 >/dev/null 2>&1 <<'SQL'
\set app_password `cat /run/secrets/db_app_password`
CREATE ROLE vantage_app LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD :'app_password';
GRANT CONNECT ON DATABASE vantage TO vantage_app;
GRANT USAGE ON SCHEMA public TO vantage_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO vantage_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO vantage_app;
SQL
then
  echo 'Runtime database-role provisioning failed; inspect private operator state, not raw secret-bearing SQL.' >&2
  exit 1
fi
