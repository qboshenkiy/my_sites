# SMM · портфолио

Домен: https://smm.vano.sbena.net

Единый файл контента: `web/site-data.js`. Измените brand, telegram, instagram, услуги и works. Контакты принимают только HTTPS. Пустые ссылки не показываются. Задачи и роль в видео пока не подтверждены. Цифры референса не используются как результаты.

Видео: web/media/work-1.mp4 … work-3.mp4. Все конвертированы в H.264/AAC, faststart; постеры JPG. Оригиналы остаются во вложениях чата.

Установка: отдельный /opt/smm-portfolio, docker compose up -d --build --wait. Контейнер без опубликованных портов, в существующей сети glava-marathon_default. Для другого сервера измените сеть в compose.yaml. Маршрут Caddy должен импортировать /data/guard-sensitive.caddy и направлять на smm-portfolio-web:8080. Проверить конфигурацию перед reload. Guard и остальные проекты не переустанавливать.

Регистрация: sudo python3 ops/register_gitdeck.py. Модуль GitDeck использует ветку codex/smm-portfolio, подпапку smm; обновляет только web, сохраняет инфраструктуру. Обновления и откаты — через карточку SMM · портфолио в GitDeck. Настройки в Git: меняйте web/site-data.js, commit/push, затем «Обновить из Git».

Первичная отмена запуска: убрать только блок `# SMM portfolio BEGIN` … `# SMM portfolio END` из /opt/marathon/deploy/Caddyfile, проверить и reload Caddy, затем docker compose -f /opt/smm-portfolio/compose.yaml down (без -v). Резервная копия Caddyfile сохраняется перед установкой. Не восстанавливайте весь файл поверх последующих чужих изменений.
