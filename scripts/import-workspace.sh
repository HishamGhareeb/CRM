#!/usr/bin/env bash
# =====================================================================
# RAL CRM — restore a workspace bundle on a new machine.
# Usage: bash scripts/import-workspace.sh migration/ral-crm-export-XXXX.tar.gz
# Prereqs on the new machine: Docker, this git repo cloned.
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."
BUNDLE="${1:?usage: import-workspace.sh <bundle.tar.gz>}"

TMP="$(mktemp -d)"; tar -xzf "${BUNDLE}" -C "${TMP}"
SRC="$(find "${TMP}" -maxdepth 1 -type d -name 'ral-crm-export-*')"

echo "==> Restoring .env"
[[ -f .env ]] || cp "${SRC}/.env.bundle" .env

echo "==> Starting stack"
docker compose up -d db redis
until docker compose exec -T db pg_isready -U twenty >/dev/null 2>&1; do sleep 2; done

# load DB creds
while IFS='=' read -r k v; do k="${k%$'\r'}"; v="${v%$'\r'}"; [[ "$k" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue; export "$k=$v"; done < .env
DB_USER="${PG_DATABASE_USER:-twenty}"; DB_NAME="${PG_DATABASE_NAME:-twenty}"

echo "==> Restoring Postgres (drops & recreates schema)"
docker compose exec -T db psql -U "${DB_USER}" -d "${DB_NAME}" -c \
  "DROP SCHEMA IF EXISTS public CASCADE; DROP SCHEMA IF EXISTS core CASCADE; DROP SCHEMA IF EXISTS metadata CASCADE;" || true
gunzip -c "${SRC}/db.sql.gz" | docker compose exec -T db psql -U "${DB_USER}" -d "${DB_NAME}"

if [[ -d "${SRC}/local-storage" ]]; then
  echo "==> Restoring local storage"
  docker compose cp "${SRC}/local-storage/." server:/app/packages/twenty-server/.local-storage/ 2>/dev/null || true
fi

echo "==> Bringing up the full stack"
docker compose up -d
rm -rf "${TMP}"
echo "==> Done. Open the CRM and verify your data is present."
