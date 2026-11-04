"""Add the managed Telegram worker without replacing an existing deployment or volume."""
from pathlib import Path
OVERLAY='''# Notes managed Telegram runtime
services:
  web:
    environment:
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
      TELEGRAM_BOT_USERNAME: ${TELEGRAM_BOT_USERNAME:-}
  bot:
    build: .
    restart: unless-stopped
    command: ["python", "src/bot.py"]
    environment:
      DATA_DIR: /data
      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}
    volumes: ["notes-data:/data"]
    read_only: true
    tmpfs: [/tmp]
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    healthcheck: {disable: true}
    logging:
      driver: json-file
      options: {max-size: "5m", max-file: "2"}
volumes:
  notes-data:
'''
def ensure(root):
    p=Path(root)/'compose.gitdeck-telegram.yaml'
    if p.is_symlink():raise ValueError('Ссылка вместо Compose-конфигурации')
    if p.exists() and not p.read_text().startswith('# Notes managed Telegram runtime\n'):raise ValueError('Существующая Telegram-конфигурация не принадлежит установщику Заметок')
    p.write_text(OVERLAY)
