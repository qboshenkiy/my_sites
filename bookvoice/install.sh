#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Запустите через sudo bash install.sh'; exit 1; fi
source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
target=/opt/bookvoice
command -v docker >/dev/null
docker compose version >/dev/null
install -d -m 755 "$target"
if [[ "$source_dir" != "$target" ]]; then
  cp -a "$source_dir/src" "$source_dir/web" "$target/"
  for file in Dockerfile compose.yaml requirements.txt .dockerignore README.md .env.example LICENSE THIRD_PARTY.md; do install -m 644 "$source_dir/$file" "$target/$file"; done
fi
cd "$target"
if [[ ! -e .env ]]; then install -m 600 .env.example .env; fi
docker compose build web
docker compose run --rm --no-deps web python src/download_models.py
docker compose up -d --wait
docker compose exec web python src/app.py password
if [[ -f /etc/gitdeck/config.json && -f /opt/gitdeck/app.py ]]; then
  python3 src/register_gitdeck.py
  python3 src/connect_https.py books.vano.sbena.net
else
  echo 'GitDeck не найден. Сайт установлен, но карточку нужно подключить отдельно.'
fi
echo 'Готово: https://books.vano.sbena.net (DNS должен указывать на сервер).'
echo 'Если HTTPS пока недоступен: ssh -N -L 8140:127.0.0.1:8140 root@IP_СЕРВЕРА'
echo 'Затем откройте http://localhost:8140'
