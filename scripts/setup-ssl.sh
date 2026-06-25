#!/usr/bin/env bash
# =====================================================================
# RAL CRM — Phase 1: Nginx site + Let's Encrypt SSL for crm.raltech.dev
# Run AFTER setup-server.sh and AFTER DNS A-record points to this server.
#   bash scripts/setup-ssl.sh
# =====================================================================
set -euo pipefail

DOMAIN="crm.raltech.dev"
EMAIL="info@raltech.dev"
REPO_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE_SRC="${REPO_DIR}/nginx/${DOMAIN}.conf"
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
