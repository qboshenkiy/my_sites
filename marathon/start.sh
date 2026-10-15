#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo 'Use a server with Docker and Docker Compose, e.g. Hetzner Docker CE.'; exit 1; }
docker compose version >/dev/null
docker info >/dev/null 2>&1 || { echo 'Start the Docker service first.'; exit 1; }
mode="${1:-http}"
case "$mode" in
    http) file=compose.yaml ;;
    https) file=compose.https.yaml ;;
    shared) file=compose.shared.yaml ;;
    *) echo 'Usage: bash start.sh [http|https|shared] [telegram]'; exit 1 ;;
esac
options=()
if [ "${2:-}" = telegram ]; then options=(--profile telegram); fi
docker compose -f "$file" up -d --build --wait --wait-timeout 180 web
if [ "$mode" = https ]; then docker compose -f "$file" up -d --no-deps proxy; fi
if [ "${2:-}" = telegram ]; then
    docker compose -f "$file" "${options[@]}" up -d --build --no-deps bot
fi
echo 'Site started. Open APP_URL from your .env file and create the first administrator.'
