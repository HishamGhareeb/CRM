#!/usr/bin/env bash
# =====================================================================
# RAL CRM — export the whole workspace for moving to another machine.
# Produces a single timestamped bundle in ./migration/ containing:
#   - Postgres dump (all CRM data: leads, views, dashboard, config)
#   - Redis dump
#   - Twenty local-storage (uploaded files/logos)
#   - the .env (secrets — keep the bundle private!)
# Restore with scripts/import-workspace.sh on the new machine.
# =====================================================================
set -euo pipefail
cd "$(dirname "${BASH_SOURCE[0]}")/.."

# load DB creds from .env (line-by-line; values may contain spaces)
[[ -f .env ]] && while IFS='=' read -r k v; do k="${k%$'\r'}"; v="${v%$'\r'}"; [[ "$k" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue; export "$k=$v"; done < .env
DB_USER="${PG_DATABASE_USER:-twenty}"; DB_NAME="${PG_DATABASE_NAME:-twenty}"
TS="$(date +%Y%m%d-%H%M%S)"; OUT="migration/ral-crm-export-${TS}"
mkdir -p "${OUT}"

echo "==> Postgres dump"
docker compose exec -T db pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${OUT}/db.sql.gz"
echo "==> Redis dump"
docker compose exec -T redis redis-cli SAVE >/dev/null 2>&1 || true
docker compose cp redis:/data/dump.rdb "${OUT}/redis-dump.rdb" 2>/dev/null || echo "   (redis dump skipped)"
echo "==> Twenty local storage"
docker compose cp server:/app/packages/twenty-server/.local-storage "${OUT}/local-storage" 2>/dev/null || echo "   (no local storage)"
echo "==> .env"
cp .env "${OUT}/.env.bundle"

tar -czf "${OUT}.tar.gz" -C migration "$(basename "${OUT}")" && rm -rf "${OUT}"
echo "==> Bundle ready: ${OUT}.tar.gz"
echo "    Copy it (and the git repo) to the new machine, then run import-workspace.sh."
echo "    NOTE: the bundle contains secrets + lead PII — keep it private, never commit it."
