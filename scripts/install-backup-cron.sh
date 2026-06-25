#!/usr/bin/env bash
# =====================================================================
# RAL CRM — Phase 1: install daily Postgres backup cron
# Schedules backup-postgres.sh every day at 03:00 server time.
#   bash scripts/install-backup-cron.sh
# =====================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SCRIPT="${REPO_DIR}/scripts/backup-postgres.sh"
LOG="/var/log/ral-crm-backup.log"
CRON_LINE="0 3 * * * cd ${REPO_DIR} && /usr/bin/env bash ${SCRIPT} >> ${LOG} 2>&1"

chmod +x "${SCRIPT}"
sudo touch "${LOG}" && sudo chown "$USER" "${LOG}"

# Install/refresh the cron entry idempotently (keyed on the script path)
( crontab -l 2>/dev/null | grep -v -F "${SCRIPT}" ; echo "${CRON_LINE}" ) | crontab -

echo "==> Cron installed:"
crontab -l | grep -F "${SCRIPT}"
echo "==> Logs -> ${LOG}"
