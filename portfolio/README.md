# VANO · портфолио

URL: https://partfolio.vano.sbena.net/
Контент: web/site-data.js. Бренд, заголовок, Telegram и проекты редактируются в одном файле.
Превью: web/media/suilo.jpg и thugger.jpg — реальные скриншоты публичных страниц проектов.

Отдельный модуль /opt/portfolio. Docker Compose подключается к существующей сети glava-marathon_default с именем portfolio-web:8080. Внешние порты не публикуются. Caddy-маршрут импортирует /data/guard-sensitive.caddy.

GitDeck: sudo python3 ops/register_gitdeck.py после первой установки. Ветка codex/portfolio-lime, папка portfolio. Обновляются только файлы web; инфраструктура сохраняется.

Изменения: отредактировать web/site-data.js в Git и нажать «Обновить из Git» на карточке VANO · портфолио. Локальные серверные правки будут заменены следующей установкой.

Отмена первичной установки: удалить только блок VANO portfolio из /opt/marathon/deploy/Caddyfile, проверить Caddy и reload; затем docker compose -f /opt/portfolio/compose.yaml down без -v. Обновления и возврат к прежнему коммиту доступны через GitDeck. Полную копию Caddyfile нельзя восстанавливать поверх последующих правок других проектов.

Анимации можно отключить кнопкой внизу страницы; учитывается системная настройка уменьшения движения.
