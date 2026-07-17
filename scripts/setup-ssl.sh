#!/usr/bin/env bash
# =====================================================================
# RAL CRM — Phase 1: Nginx site + Let's Encrypt SSL
# Run AFTER setup-server.sh and AFTER DNS A-record points to this server.
#   bash scripts/setup-ssl.sh                  # uses DOMAIN/CERTBOT_EMAIL from .env
#   bash scripts/setup-ssl.sh other.domain.com someone@example.com   # override
# =====================================================================
set -euo pipefail

REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
if [[ -f "${REPO_DIR}/.env" ]]; then set -a; source "${REPO_DIR}/.env"; set +a; fi

DOMAIN="${1:-${DOMAIN:-crm.raltech.dev}}"
EMAIL="${2:-${CERTBOT_EMAIL:-${EMAIL_SYSTEM_ADDRESS:-info@raltech.dev}}}"
SITE_SRC="${REPO_DIR}/nginx/${DOMAIN}.conf"
if [[ ! -f "${SITE_SRC}" ]]; then
  echo "No nginx/${DOMAIN}.conf found — copy nginx/crm.raltech.dev.conf to that"
  echo "filename and replace the domain inside it, then re-run."
  exit 1
fi
SITE_AVAIL="/etc/nginx/sites-available/${DOMAIN}.conf"
SITE_ENABLED="/etc/nginx/sites-enabled/${DOMAIN}.conf"

echo "==> Installing Nginx site for ${DOMAIN}"
# Temporarily serve HTTP-only so certbot can complete the ACME challenge
# before the cert files referenced in the :443 block exist.
sudo tee "${SITE_AVAIL}" > /dev/null <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name ${DOMAIN};
    location /.well-known/acme-challenge/ { root /var/www/certbot; }
    location / { return 404; }
}
EOF
sudo ln -sf "${SITE_AVAIL}" "${SITE_ENABLED}"
sudo nginx -t && sudo systemctl reload nginx

echo "==> Requesting Let's Encrypt certificate"
sudo certbot certonly --webroot -w /var/www/certbot \
  -d "${DOMAIN}" --email "${EMAIL}" --agree-tos --non-interactive

echo "==> Installing full reverse-proxy config"
sudo cp "${SITE_SRC}" "${SITE_AVAIL}"
sudo nginx -t && sudo systemctl reload nginx

echo "==> certbot auto-renew is handled by the system timer; verifying"
sudo systemctl list-timers | grep -i certbot || true
sudo certbot renew --dry-run

echo "==> SSL ready: https://${DOMAIN}"
