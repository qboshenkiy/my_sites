# Быстрый запуск на Hetzner Cloud

## 1. Создайте сервер

В Hetzner Console при создании сервера выберите **Apps → Docker CE**. Этот образ содержит Docker и Docker Compose: [официальная инструкция Hetzner](https://docs.hetzner.com/cloud/apps/list/docker-ce/).

Укажите SSH-ключ. Проект не требует отдельного MySQL или Node.js. Для начальной небольшой аудитории можно начать с выбранного небольшого VPS; число одновременно подключённых игроков нужно проверять на вашем тарифе. Лимит комнаты 500 — ограничение приложения, не гарантия производительности.

В Hetzner Firewall разрешите TCP 22 для вашего IP, TCP 80 и TCP 443 для посетителей. IPv4 сервера будет в панели Hetzner. Если на сервере уже есть сайты на портах 80/443, используйте свободный порт для HTTP через `.env` или подключайте приложение к существующему reverse proxy.

## 2. Загрузите проект

С компьютера (PowerShell), заменив `SERVER_IP` на адрес вашего сервера:

```powershell
scp C:/laragon/www/my_project/dist/pulse-server.tar.gz root@SERVER_IP:/root/
ssh root@SERVER_IP
```

На сервере:

```bash
mkdir -p /opt/pulse
tar -xzf /root/pulse-server.tar.gz -C /opt/pulse
cd /opt/pulse
bash start.sh
```

Первый запуск скачает и соберёт контейнер. Затем откройте `http://SERVER_IP/`, сразу создайте пароль администратора и запускайте игры. Можно также загрузить ZIP через SFTP и распаковать его в `/opt/pulse`.

Игроки открывают `http://SERVER_IP/#join` либо ссылку из лобби. На сервере участники могут подключаться через любой интернет, общая Wi-Fi сеть не нужна.

## 3. Домен и HTTPS

Создайте DNS-запись A для вашего домена, указывающую на IPv4 сервера. Если задана AAAA-запись, IPv6 тоже должен вести на этот сервер. После обновления DNS:

```bash
cd /opt/pulse
bash start.sh quiz.example.com
```

Скрипт сохранит домен в `.env`, остановит HTTP-контейнер и запустит вариант с Caddy. База останется в том же Docker volume. Откройте `https://quiz.example.com/`. Caddy получает и обновляет сертификаты автоматически, если DNS правильный и порты 80/443 доступны: [документация Caddy](https://caddyserver.com/docs/automatic-https).

Для входа администратора и постоянной эксплуатации используйте HTTPS. Пока нет домена, HTTP-вариант подходит для первоначальной проверки.

## Управление

HTTP-режим:

```bash
docker compose ps
docker compose logs --tail=100
docker compose stop
docker compose up -d
```

HTTPS-режим — добавляйте `-f compose.https.yaml`:

```bash
docker compose -f compose.https.yaml ps
docker compose -f compose.https.yaml logs --tail=100
docker compose -f compose.https.yaml stop
docker compose -f compose.https.yaml up -d
```

После изменения кода пересоберите контейнер: `docker compose up -d --build` (с `-f compose.https.yaml` для HTTPS). После перезагрузки сервера контейнеры запускаются автоматически, если работает Docker. Команда `up -d` запускает контейнеры в фоне: [документация Docker](https://docs.docker.com/reference/cli/docker/compose/up/).

Данные хранятся в Docker volume `pulse_pulse_data`, вне веб-каталога. Не используйте `docker compose down -v`: этот флаг удаляет базу вместе с volume. Архивы для загрузки не содержат локальных паролей, игроков и базы данных. Обновление проекта не требует повторного создания администратора.

## Резервная копия

После первого открытия сайта, для HTTP:

```bash
docker compose exec -T web php /opt/pulse/backup.php /var/lib/pulse/backup.sqlite
docker compose cp web:/var/lib/pulse/backup.sqlite ./backup.sqlite
docker compose exec -T web rm /var/lib/pulse/backup.sqlite
```

Для HTTPS используйте `docker compose -f compose.https.yaml` во всех трёх командах. Встроенный инструмент создаёт согласованную копию SQLite даже во время работы приложения. Скачайте `backup.sqlite` по SFTP и храните отдельно от сервера.

Восстановление заменяет текущую базу: остановите приложение, сохраните текущую копию, восстановите файл в volume и уберите старые WAL/SHM-файлы перед запуском. Не копируйте SQLite поверх работающего приложения.

## Если запуск не удался

- `docker compose version`: проверяет наличие Compose.
- `docker compose logs --tail=100`: причина ошибки приложения.
- `docker compose exec web php /opt/pulse/check.php`: проверка PHP-модулей и папки данных.
- «Port already allocated»: порт занят; задайте `APP_PORT=8080` в `.env` для HTTP-режима.
- Сайт не открывается: проверьте IP, Hetzner Firewall и брандмауэр Linux.
- HTTPS не появился: проверьте A/AAAA-записи и порты 80/443, затем логи `proxy`.

## Обычный хостинг без Docker

Распакуйте `pulse-server.zip` в папку сайта. Нужны PHP 8.1+, `pdo_sqlite`, `mbstring`, Apache с поддержкой `.htaccess` и права PHP на запись в `storage`. База и таблицы создаются автоматически. Включите HTTPS в панели хостинга. На Nginx `.htaccess` не работает: настройте закрытый каталог данных через `QUIZ_DATA_DIR` вне веб-каталога и запретите HTTP-доступ к служебным папкам.
