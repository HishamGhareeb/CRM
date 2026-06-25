#!/usr/bin/env bash
# =====================================================================
# RAL CRM — Phase 1: base server bootstrap
# Target: Oracle Cloud Free Tier, Ubuntu 24.04 Minimal (aarch64/ARM)
# Run as a sudo-capable user:  bash scripts/setup-server.sh
#
# Installs: Docker Engine + Compose plugin, Nginx, certbot.
# Idempotent — safe to re-run.
# =====================================================================
set -euo pipefail

echo "==> RAL CRM server bootstrap starting"

if [[ "$(uname -m)" != "aarch64" ]]; then
  echo "WARNING: expected aarch64 (ARM). Detected $(uname -m). Continuing anyway."
fi

echo "==> Updating apt and installing prerequisites"
sudo apt-get update -y
sudo apt-get install -y ca-certificates curl gnupg lsb-release ufw

# ---- Docker Engine + Compose plugin (official repo) ----------------
if ! command -v docker >/dev/null 2>&1; then
  echo "==> Installing Docker Engine"
  sudo install -m 0755 -d /etc/apt/keyrings
  curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
    | sudo gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo chmod a+r /etc/apt/keyrings/docker.gpg
  echo \
    "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
    https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
    | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
  sudo apt-get update -y
  sudo apt-get install -y docker-ce docker-ce-cli containerd.io \
    docker-buildx-plugin docker-compose-plugin
  sudo usermod -aG docker "$USER"
  echo "    (log out/in for docker group to take effect)"
else
  echo "==> Docker already installed: $(docker --version)"
fi

# ---- Nginx + certbot -----------------------------------------------
echo "==> Installing Nginx + certbot"
sudo apt-get install -y nginx certbot python3-certbot-nginx
sudo mkdir -p /var/www/certbot

# ---- Firewall (Oracle security list also needs 80/443/22 open) -----
echo "==> Configuring host firewall (ufw)"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "==> Done. Next: deploy nginx config, then run scripts/setup-ssl.sh"
