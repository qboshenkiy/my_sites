#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Запустите через sudo bash update.sh'; exit 1; fi
source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
target=/opt/milk-duty
if [[ ! -f "$target/compose.yaml" ]]; then echo 'Сначала выполните install.sh'; exit 1; fi
cd "$target"
compose=(-f compose.yaml)
if [[ -f compose.gitdeck-https.yaml ]]; then compose+=(-f compose.gitdeck-https.yaml); fi
backup="/data/before-update-$(date -u +%Y%m%d-%H%M%S).sqlite"
docker compose "${compose[@]}" exec -T web python src/backup.py "$backup"
if [[ "$source_dir" != "$target" ]]; then
  cp -a "$source_dir/src/." "$target/src/"
  cp -a "$source_dir/web/." "$target/web/"
fi
docker compose "${compose[@]}" up -d --build --wait
echo 'Обновление завершено. Пароль, участники, токен и расписание сохранены.'
