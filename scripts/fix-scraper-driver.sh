#!/usr/bin/env bash
# =====================================================================
# RAL CRM — workaround for a broken Playwright driver fetch in the
# gosom/google-maps-scraper image.
#
# The gosom scraper (Go) fetches its Playwright driver as a standalone
# zip from playwright.azureedge.net. That domain no longer serves the
# "driver" artifact for any version (Microsoft appears to have retired
# it — Python/JS Playwright are unaffected because they bundle their
# driver directly instead of fetching a separate zip). Every gosom tag
# we tried (latest, v1.16.0, v1.16.3) hits the same dead URL and fails
# with: "could not install driver: driver exists but version not X.X.X"
# or a 404 from all three CDN mirrors.
#
# Fix: assemble the driver by hand from sources that still work —
# the official Node.js binary (nodejs.org) plus the playwright-core
# npm package at the exact version the scraper expects (registry.npmjs.org,
# unrelated infrastructure to the dead CDN) — and place them at the path
# the scraper's Go code checks (/opt/ms-playwright-go).
#
# Re-run this after recreating the scraper container or upgrading its
# image tag (the required driver version may change — check the error
# in `docker compose logs scraper` for the version it wants).
#
# Usage:
#   bash scripts/fix-scraper-driver.sh [driver-version] [container-name]
#   bash scripts/fix-scraper-driver.sh 1.60.0 ral-crm-scraper-1
# =====================================================================
set -euo pipefail

DRIVER_VERSION="${1:-1.60.0}"
CONTAINER="${2:-ral-crm-scraper-1}"
NODE_VERSION="v20.18.1"
WORKDIR="$(mktemp -d)"
trap 'rm -rf "$WORKDIR"' EXIT

echo "==> Fixing Playwright driver for scraper container: $CONTAINER (driver v$DRIVER_VERSION)"

if ! docker ps --format '{{.Names}}' | grep -qx "$CONTAINER"; then
  echo "ERROR: container '$CONTAINER' is not running. Start the stack first (docker compose up -d)."
  exit 1
fi

echo "==> Downloading Node.js $NODE_VERSION (linux-x64) from nodejs.org"
curl -sL -o "$WORKDIR/node.tar.gz" \
  "https://nodejs.org/dist/${NODE_VERSION}/node-${NODE_VERSION}-linux-x64.tar.gz"

echo "==> Downloading playwright-core@$DRIVER_VERSION from the npm registry"
curl -sL -o "$WORKDIR/playwright-core.tgz" \
  "https://registry.npmjs.org/playwright-core/-/playwright-core-${DRIVER_VERSION}.tgz"

mkdir -p "$WORKDIR/node" "$WORKDIR/pw"
tar -xzf "$WORKDIR/node.tar.gz" -C "$WORKDIR/node"
tar -xzf "$WORKDIR/playwright-core.tgz" -C "$WORKDIR/pw"

echo "==> Copying assembled driver into the container"
docker cp "$WORKDIR/node/node-${NODE_VERSION}-linux-x64/bin/node" "$CONTAINER:/tmp/pw-node"
docker cp "$WORKDIR/pw/package" "$CONTAINER:/tmp/pw-package"
docker exec "$CONTAINER" sh -c "
  rm -rf /opt/ms-playwright-go/*
  mv /tmp/pw-node /opt/ms-playwright-go/node
  mv /tmp/pw-package /opt/ms-playwright-go/package
  chmod +x /opt/ms-playwright-go/node
"

echo "==> Verifying"
docker exec "$CONTAINER" sh -c "grep '\"version\"' /opt/ms-playwright-go/package/package.json"
echo "==> Done. This persists in the scraper-playwright Docker volume until it's removed."
