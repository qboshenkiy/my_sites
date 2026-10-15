#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
command -v docker >/dev/null || { echo 'Install Docker and Docker Compose, or use the Hetzner Docker CE image.'; exit 1; }
docker compose version >/dev/null
docker info >/dev/null 2>&1 || { echo 'Docker is not running. Start the Docker service first.'; exit 1; }
if [ $# -gt 0 ]; then
    domain="$1"
    [[ "$domain" =~ ^[a-zA-Z0-9]([a-zA-Z0-9.-]*[a-zA-Z0-9])?$ && "$domain" == *.* ]] || { echo 'Use a domain name without https:// or a path.'; exit 1; }
    config_tmp="$(mktemp .env.pulse.XXXXXX)"
    if [ -f .env ]; then awk '!/^DOMAIN=/' .env > "$config_tmp"; fi
    printf 'DOMAIN=%s\n' "$domain" >> "$config_tmp"
    chmod 600 "$config_tmp"
    mv "$config_tmp" .env
    docker compose -f compose.yaml down
    docker compose -f compose.https.yaml up -d --build --wait --wait-timeout 180
    printf '\nOpen https://%s/ and create your administrator password.\n' "$domain"
else
    docker compose -f compose.yaml up -d --build --wait --wait-timeout 180
    binding="$(docker compose -f compose.yaml port web 80)"
    printf '\nOpen http://SERVER_IP:%s/ and create your administrator password.\n' "${binding##*:}"
fi
