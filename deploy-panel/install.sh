#!/usr/bin/env bash
set -euo pipefail
if [[ $(id -u) != 0 ]]; then echo 'Запустите через sudo bash install.sh'; exit 1; fi
command -v python3 >/dev/null
command -v git >/dev/null
command -v docker >/dev/null
command -v systemd-run >/dev/null
docker compose version >/dev/null
source_dir="$(cd -- "$(dirname -- "$0")" && pwd)"
install -d -m 700 /etc/gitdeck /var/lib/gitdeck
install -d -m 755 /opt/gitdeck
if [[ "$source_dir" != /opt/gitdeck ]]; then
  for file in app.py index.html VERSION README.md config.example.json install.sh .gitignore; do
    install -m 644 "$source_dir/$file" "/opt/gitdeck/$file"
  done
fi
if [[ ! -e /etc/gitdeck/config.json ]]; then
  install -m 600 "$source_dir/config.example.json" /etc/gitdeck/config.json
fi
chmod 600 /etc/gitdeck/config.json
cat > /etc/systemd/system/gitdeck.service <<'UNIT'
[Unit]
Description=GitDeck local deployment panel
After=network.target docker.service

[Service]
Type=simple
User=root
WorkingDirectory=/opt/gitdeck
ExecStart=/usr/bin/python3 /opt/gitdeck/app.py --config /etc/gitdeck/config.json serve
Restart=on-failure
RestartSec=3
UMask=0077
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
UNIT
python3 /opt/gitdeck/app.py --config /etc/gitdeck/config.json password
systemctl daemon-reload
systemctl enable --now gitdeck
echo 'GitDeck установлен. Отредактируйте /etc/gitdeck/config.json и выполните systemctl restart gitdeck.'
echo 'На своём ПК: ssh -L 8120:127.0.0.1:8120 root@SERVER_IP'
echo 'Затем откройте http://localhost:8120'
