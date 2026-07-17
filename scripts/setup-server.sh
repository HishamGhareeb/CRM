#!/usr/bin/env bash
# =====================================================================
# RAL CRM — Phase 1: base server bootstrap
# Target: any Ubuntu 22.04/24.04 server, x86_64 or ARM64 (Twenty's Docker
# images are multi-arch — no architecture-specific setup needed).
# Run as a sudo-capable user:  bash scripts/setup-server.sh
#
# Installs: Docker Engine + Compose plugin, Nginx, certbot.
# Idempotent — safe to re-run.
# =====================================================================
set -euo pipefail

echo "==> RAL CRM server bootstrap starting (detected arch: $(uname -m))"

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

# ---- Firewall (if hosted on a cloud VM, also open 80/443/22 in its
#      network security group / security list, separately from ufw) -----
echo "==> Configuring host firewall (ufw)"
sudo ufw allow OpenSSH
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw --force enable

echo "==> Done. Next: deploy nginx config, then run scripts/setup-ssl.sh"
