#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Запустите через sudo bash install.sh'; exit 1; fi
source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
target=/opt/milk-duty
command -v docker >/dev/null
docker compose version >/dev/null
install -d -m 755 "$target"
if [[ "$source_dir" != "$target" ]]; then
  cp -a "$source_dir/src" "$source_dir/web" "$target/"
  for file in Dockerfile compose.yaml .dockerignore README.md .env.example; do install -m 644 "$source_dir/$file" "$target/$file"; done
fi
cd "$target"
if [[ ! -e .env ]]; then install -m 600 .env.example .env; fi
docker compose up -d --build --wait
docker compose exec web python src/app.py password
echo 'Готово. На своём ПК: ssh -N -L 8130:127.0.0.1:8130 root@IP_СЕРВЕРА'
echo 'Откройте http://localhost:8130 . Токен бота и все настройки вводятся в панели.'
