#!/usr/bin/env bash
# =====================================================================
# RAL CRM — Phase 1: daily PostgreSQL backup
# Dumps the Twenty DB from the `db` container to $BACKUP_DIR, gzipped,
# and prunes dumps older than $BACKUP_RETENTION_DAYS.
# Invoked by cron (see install-backup-cron.sh).
# =====================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${REPO_DIR}"

# Load env (.env holds DB creds + backup config)
if [[ -f .env ]]; then
  set -a; . ./.env; set +a
fi

BACKUP_DIR="${BACKUP_DIR:-/opt/ral-crm/backups}"
RETENTION="${BACKUP_RETENTION_DAYS:-14}"
DB_USER="${PG_DATABASE_USER:-twenty}"
DB_NAME="${PG_DATABASE_NAME:-twenty}"
TS="$(date +%Y%m%d-%H%M%S)"
OUT="${BACKUP_DIR}/ral-crm-${DB_NAME}-${TS}.sql.gz"

mkdir -p "${BACKUP_DIR}"

echo "==> Dumping ${DB_NAME} -> ${OUT}"
docker compose exec -T db pg_dump -U "${DB_USER}" "${DB_NAME}" | gzip > "${OUT}"

# Verify the dump is non-trivial
if [[ ! -s "${OUT}" ]]; then
  echo "ERROR: backup file is empty — dump failed" >&2
  rm -f "${OUT}"
  exit 1
fi

echo "==> Pruning backups older than ${RETENTION} days"
find "${BACKUP_DIR}" -name 'ral-crm-*.sql.gz' -type f -mtime +"${RETENTION}" -print -delete

echo "==> Backup complete: $(du -h "${OUT}" | cut -f1) — $(ls -1 "${BACKUP_DIR}" | wc -l) dumps retained"
