"""GitDeck: loopback-only deployment console; Python standard library, Linux/systemd."""
import argparse
import base64
import getpass
import hashlib
import hmac
import http.cookies
import http.server
import io
import json
import os
from pathlib import Path, PurePosixPath
import re
import secrets
import shlex
import shutil
import sqlite3
import subprocess
import sys
import tarfile
import threading
import time
import urllib.parse

VERSION = '1.5.1'
LAYOUT = {
    'drawing': ['index.php', 'api.php', 'lib', 'assets', 'ops', '.dockerignore'],
    'pulse': ['index.php', 'api.php', 'seed.php', '.htaccess', 'assets', 'tools/check.php', 'tools/backup.php'],
    'marathon': ['index.php', 'api.php', '.htaccess', 'assets', 'lib', 'tools/bot.php', 'tools/backup.php'],
    'chrono': ['app', 'public/assets', 'public/index.php', 'public/_health.php', 'public/.htaccess',
               'public/favicon.ico', 'public/robots.txt', 'composer.json', 'composer.lock', 'spark', 'ops', '.dockerignore'],
    'self': ['app.py', 'index.html', 'VERSION', 'README.md', 'install.sh', 'config.example.json', '.gitignore'],
}
REQUIRED = {'drawing': ['index.php', 'api.php', 'lib/core.php', 'lib/ai.php', 'ops/compose.yaml', 'ops/Dockerfile'],
            'pulse': ['index.php', 'api.php', 'assets/app.js'],
            'marathon': ['index.php', 'api.php', 'lib/core.php', 'lib/telegram.php'],
            'chrono': ['app/Config/Paths.php', 'public/index.php', 'composer.lock', 'spark', 'ops/compose.yaml',
                       'ops/Dockerfile', 'ops/entrypoint.sh', 'app/Commands/DeployAdmin.php'],
            'self': ['app.py', 'index.html', 'VERSION']}


def valid_ref(ref):
    if not isinstance(ref, str) or not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,150}', ref) or '..' in ref:
        raise ValueError('Укажите ветку или SHA коммита без пробелов и специальных символов')
    return ref


def code_paths(p):
    return p['paths'] if p['kind'] == 'docker' else LAYOUT[p['kind']]


def validate_paths(paths):
    if not isinstance(paths, list) or not 1 <= len(paths) <= 30:
        raise ValueError('Укажите от 1 до 30 файлов или папок с кодом')
    for name in paths:
        if not isinstance(name, str) or not re.fullmatch(r'[A-Za-z0-9_.-]+(?:/[A-Za-z0-9_.-]+)*', name):
            raise ValueError('Некорректный путь к коду')
        if any(s in ('.', '..', '.git', 'storage', 'uploads', 'data', 'deploy') or s.startswith('.env') for s in name.split('/')):
            raise ValueError('Данные, .env, .git и настройки сервера нельзя заменять кодом')
        if name in ('Dockerfile', '.dockerignore') or re.search(r'(?:compose.*\.ya?ml|\.sqlite.*|\.db|\.pem|\.key)$', name, re.I):
            raise ValueError('Настройки Docker, ключи и базы не входят в обновление кода')
    for a in paths:
        if any(a != b and (a.startswith(b + '/') or b.startswith(a + '/')) for b in paths):
            raise ValueError('Пути к коду не должны вкладываться друг в друга')
    if len(set(paths)) != len(paths):
        raise ValueError('Пути не должны повторяться')


def validate_project(p):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', p['id']) or p['kind'] not in (*LAYOUT, 'docker'):
        raise ValueError('Некорректный id или тип проекта')
    repo = p['repo']
    url = urllib.parse.urlsplit(repo)
    https = url.scheme == 'https' and url.hostname and not url.username and not url.password and not url.query and not url.fragment
    ssh = re.fullmatch(r'git@[a-zA-Z0-9.-]+:[a-zA-Z0-9_./-]+\.git', repo)
    if not (https or ssh) or any(c.isspace() for c in repo):
        raise ValueError('Используйте HTTPS без токена в URL или git@host:owner/repo.git')
    valid_ref(p['branch'])
    sub = p.get('subdir', '')
    if sub and (not re.fullmatch(r'[A-Za-z0-9_./-]+', sub) or any(s in ('', '.', '..') for s in sub.split('/'))):
        raise ValueError('Некорректный путь в репозитории')
    dest = Path(p['directory'])
    if not dest.is_absolute() or len(dest.parts) < 3 or dest.is_symlink():
        raise ValueError('Укажите отдельный абсолютный каталог приложения')
    if p['kind'] != 'self':
        if p['compose'] not in ('compose.yaml', 'compose.https.yaml', 'compose.shared.yaml'):
            raise ValueError('Неизвестный compose-файл')
        if p['kind'] == 'docker':
            validate_paths(p.get('paths'))
            for key in ('services', 'profiles'):
                values = p.get(key, [])
                if not isinstance(values, list) or len(values) > 10 or any(not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,60}', s) for s in values):
                    raise ValueError('Некорректные имена сервисов или профилей')
            if not p.get('services') or p.get('main_service') not in p['services']:
                raise ValueError('Основной сервис должен входить в список запуска')
            if not isinstance(p.get('wait_health', True), bool):
                raise ValueError('Некорректный режим проверки готовности')
        else:
            if p['kind'] in ('chrono', 'drawing') and (p['compose'] != 'compose.yaml' or p.get('services') != ['web'] or p.get('profiles', [])):
                raise ValueError('Этот модуль использует compose.yaml, сервис web без профилей')
            if p.get('services') not in (['web'], ['web', 'bot']):
                raise ValueError('Разрешены сервисы web и bot')
            if p.get('profiles', []) not in ([], ['telegram']):
                raise ValueError('Неизвестный профиль')
    return p


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    return validate_config(config)


def validate_config(config):
    ids = set()
    directories = set()
    for p in config['projects']:
        validate_project(p)
        d = str(Path(p['directory']).resolve())
        if p['id'] in ids or any(Path(d).is_relative_to(Path(old)) or Path(old).is_relative_to(Path(d)) for old in directories):
            raise ValueError('Проекты должны иметь разные id и каталоги')
        ids.add(p['id'])
        directories.add(d)
    return config


def config_revision(config):
    return hashlib.sha256(json.dumps(config, sort_keys=True).encode()).hexdigest()


def save_config(server, projects, revision):
    if revision != config_revision(server.config):
        raise ValueError('Настройки уже изменились. Обновите страницу и повторите')
    config = dict(server.config, projects=projects)
    validate_config(config)
    state = Path(config['state_dir']).resolve()
    for p in projects:
        dest = Path(p['directory']).resolve()
        if state.is_relative_to(dest) or dest.is_relative_to(state):
            raise ValueError('Каталог модуля пересекается с данными панели')
    path = Path(server.config_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + '.' + secrets.token_hex(6) + '.tmp')
    try:
        temp.write_text(json.dumps(config, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
        os.chmod(temp, 0o600)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)
    server.config = config


def project_from_form(data, old, config):
    fields = ('id', 'name', 'kind', 'repo', 'branch', 'subdir', 'directory', 'compose',
              'profiles', 'services', 'paths', 'main_service', 'wait_health')
    p = {k: data[k] for k in fields if k in data}
    for key in ('id', 'name', 'kind', 'repo', 'branch', 'directory'):
        if not isinstance(p.get(key), str) or not p[key].strip():
            raise ValueError('Заполните обязательные поля модуля')
        p[key] = p[key].strip()
    if len(p['name']) > 100:
        raise ValueError('Название слишком длинное')
    if old and (p['id'] != old['id'] or p['kind'] != old['kind']):
        raise ValueError('Тип и идентификатор установленного модуля менять нельзя')
    if p['kind'] == 'self' and not old:
        raise ValueError('Карточка самой панели уже задана при установке')
    if old and old['kind'] == 'self' and p['directory'] != old['directory']:
        raise ValueError('Каталог самой панели менять нельзя')
    root = Path(config.get('projects_root', '/opt')).resolve()
    dest = Path(p['directory']).resolve()
    if dest == root or not dest.is_relative_to(root):
        raise ValueError('Модули должны находиться внутри ' + str(root))
    if any(parent.is_symlink() for parent in [Path(p['directory']), *Path(p['directory']).parents]):
        raise ValueError('Каталог модуля не должен содержать символические ссылки')
    p['ssh_key'] = old.get('ssh_key', '') if old else ''
    return validate_project(p)


class Connection(sqlite3.Connection):
    def __exit__(self, *args):
        try:
            return super().__exit__(*args)
        finally:
            self.close()


def db_open(config):
    state = Path(config['state_dir'])
    state.mkdir(parents=True, exist_ok=True, mode=0o700)
    db = sqlite3.connect(state / 'panel.sqlite', timeout=15, factory=Connection)
    db.row_factory = sqlite3.Row
    db.executescript('''
      CREATE TABLE IF NOT EXISTS credentials (id INTEGER PRIMARY KEY, salt TEXT, digest TEXT);
      CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, project TEXT, action TEXT,
        status TEXT, created REAL, updated REAL, commit_sha TEXT DEFAULT '', error TEXT DEFAULT '');
      CREATE TABLE IF NOT EXISTS versions (project TEXT PRIMARY KEY, commit_sha TEXT, updated REAL);
    ''')
    columns = {r[1] for r in db.execute('PRAGMA table_info(jobs)')}
    if 'target_ref' not in columns:
        db.execute("ALTER TABLE jobs ADD COLUMN target_ref TEXT NOT NULL DEFAULT ''")
    db.commit()
    return db


def password_digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt), n=16384, r=8, p=1).hex()


def set_password(config):
    password = getpass.getpass('Новый пароль GitDeck (от 12 символов): ')
    if len(password) < 12 or password != getpass.getpass('Повторите пароль: '):
        raise ValueError('Пароли не совпадают или пароль короче 12 символов')
    salt = secrets.token_hex(16)
    with db_open(config) as db:
        db.execute('INSERT OR REPLACE INTO credentials VALUES (1, ?, ?)', (salt, password_digest(password, salt)))
    print('Пароль сохранён. Для завершения прежних сессий: systemctl restart gitdeck')


def run(command, log=None, cwd=None, env=None, timeout=900):
    # Config controls paths; never interpret shell text or print credentials.
    result = subprocess.run(command, cwd=cwd, env=env, stdout=subprocess.PIPE,
                            stderr=subprocess.STDOUT, timeout=timeout, check=False)
    if log:
        log.write(result.stdout.decode('utf-8', errors='replace'))
        log.flush()
    if result.returncode:
        raise RuntimeError(f'Команда {Path(command[0]).name} завершилась с кодом {result.returncode}; см. журнал')
    return result.stdout


def compose(p, args, log):
    command = ['docker', 'compose', '-f', p['compose']]
    if p['kind'] == 'chrono' and (Path(p['directory']) / 'ops/compose.runtime.yaml').is_file():
        command += ['-f', 'ops/compose.runtime.yaml']
    if (Path(p['directory']) / 'compose.gitdeck-https.yaml').is_file():
        command += ['-f', 'compose.gitdeck-https.yaml']
    if (Path(p['directory']) / 'compose.gitdeck-community.yaml').is_file():
        command += ['-f', 'compose.gitdeck-community.yaml']
    if (Path(p['directory']) / 'compose.gitdeck-telegram.yaml').is_file():
        command += ['-f', 'compose.gitdeck-telegram.yaml']
    for profile in p.get('profiles', []):
        command += ['--profile', profile]
    return run(command + args, log, cwd=p['directory'])


def project_services(p):
    services = list(p['services'])
    if p['kind'] == 'pulse' and (Path(p['directory']) / 'compose.gitdeck-telegram.yaml').is_file() and 'bot' not in services:
        services.append('bot')
    return services


def start_services(p, log, build=True):
    # Compose must only wait for services that actually have a healthcheck.
    flags = ['--build'] if build else []
    main = p.get('main_service', 'web')
    wait = ['--wait', '--wait-timeout', '180'] if p.get('wait_health', True) else []
    compose(p, ['up', '-d'] + flags + wait + [main], log)
    extras = [s for s in project_services(p) if s != main]
    if extras:
        compose(p, ['up', '-d'] + flags + ['--no-deps'] + extras, log)
    checks = extras + ([main] if not wait else [])
    if checks:
        # This checks process startup, not Telegram connectivity.
        for _ in range(3):
            time.sleep(1)
            for service in checks:
                if not compose(p, ['ps', '--status', 'running', '-q', service], log).strip():
                    raise RuntimeError('Бот/сервис ' + service + ' не остаётся запущенным; проверьте его журнал')
        log.write('\nСервисы без healthcheck остаются запущенными.\n')
        log.flush()


def allowed(name, kind):
    if isinstance(kind, dict) and kind['kind'] == 'docker' and runtime_path(name):
        return False
    paths = code_paths(kind) if isinstance(kind, dict) else LAYOUT[kind]
    return any(name == entry or name.startswith(entry + '/') for entry in paths)


def runtime_path(name):
    return any(s in ('storage', 'uploads', 'data', '.git') or s.startswith('.env') for s in PurePosixPath(name).parts) or bool(re.search(r'\.(?:sqlite.*|db|pem|key)$', name, re.I))


def git_environment(p):
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    if p.get('ssh_key'):
        key = Path(p['ssh_key'])
        if not key.is_file():
            raise ValueError('Не найден SSH-ключ для репозитория')
        env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i ' + shlex.quote(str(key))
    return env


REF_LOCK = threading.Lock()

PUBLIC_ENV = {'DOMAIN', 'APP_URL', 'APP_PORT', 'APP_BIND', 'TELEGRAM_BOT_USERNAME', 'MARATHON_TIMEZONE', 'TZ', 'ADMIN_USERNAME', 'HTTPS_PROXY_PROJECT', 'OPENAI_MODEL', 'AI_DAILY_LIMIT', 'MARATHON_URL', 'PULSE_URL'}


def env_file(p):
    if p['kind'] == 'self':
        raise ValueError('У панели нет .env сайта. Используйте настройки её репозитория')
    return validate_destination(Path(p['directory']), '.env')


def env_text(p):
    file = env_file(p)
    if file.exists() and (not file.is_file() or file.stat().st_size > 262144):
        raise ValueError('Файл .env слишком большой или не является обычным файлом')
    return file.read_text(encoding='utf-8-sig') if file.exists() else ''


def env_records(text):
    records = []
    # Preserve original spans, comments and multiline values not being edited.
    pattern = re.compile(r'(?m)^(?:export[ \t]+)?([A-Za-z_][A-Za-z0-9_]*)[ \t]*=[ \t]*')
    offset = 0
    while True:
        match = pattern.search(text, offset)
        if not match:
            return records
        start = match.end()
        if start < len(text) and text[start] in "\"'":
            quote = text[start]
            end = start + 1
            while end < len(text):
                if text[end] == quote and (end == 0 or text[end - 1] != '\\'):
                    break
                end += 1
            raw = text[start:end + 1]
            value = raw[1:-1].replace("\\'", "'") if quote == "'" else raw[1:-1]
        else:
            end = text.find('\n', start)
            if end < 0:
                end = len(text)
            raw = text[start:end]
            value = re.split(r'\s+#', raw, maxsplit=1)[0].strip()
        line_end = text.find('\n', end)
        line_end = len(text) if line_end < 0 else line_end + 1
        records.append((match.group(1), value, match.start(), line_end))
        offset = max(line_end, match.end())


def env_revision(text):
    return hashlib.sha256(text.encode()).hexdigest()


def env_settings(p):
    text = env_text(p)
    values = {key: value for key, value, *_ in env_records(text)}
    defaults = ['DOMAIN', 'APP_URL', 'APP_PORT', 'APP_BIND']
    if p['kind'] == 'marathon':
        defaults += ['TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME']
    if p['kind'] == 'pulse':
        defaults += ['HTTPS_PROXY_PROJECT', 'MARATHON_URL', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME']
    if p['kind'] == 'chrono':
        defaults = ['APP_URL', 'HTTPS_PROXY_PROJECT', 'APP_PORT', 'APP_BIND', 'TELEGRAM_BOT_TOKEN', 'TELEGRAM_BOT_USERNAME', 'ADMIN_USERNAME', 'ADMIN_PASSWORD']
    if p['kind'] == 'drawing':
        defaults = ['APP_URL', 'HTTPS_PROXY_PROJECT', 'APP_PORT', 'APP_BIND', 'ADMIN_PASSWORD', 'GAME_ACCESS_CODE', 'OPENAI_API_KEY', 'OPENAI_MODEL', 'AI_DAILY_LIMIT']
    fields = []
    for key in dict.fromkeys(defaults + list(values)):
        if key.startswith(('COMPOSE_', 'DOCKER_', 'GIT_', 'PYTHON')) or key in ('PATH', 'HOME'):
            continue
        secret = key not in PUBLIC_ENV
        fields.append({'key': key, 'secret': secret, 'value': '' if secret else values.get(key, ''),
                       'configured': bool(values.get(key))})
        if p['kind'] == 'chrono' and key in ('DB_DATABASE', 'DB_USERNAME', 'DB_PASSWORD'):
            fields[-1]['readonly'] = True
    return {'fields': fields, 'env_revision': env_revision(text)}


def validate_env_changes(changes):
    if not isinstance(changes, dict) or not 1 <= len(changes) <= 60:
        raise ValueError('Измените хотя бы одно поле настроек')
    for key, value in changes.items():
        if not re.fullmatch(r'[A-Z][A-Z0-9_]{0,79}', key) or key.startswith(('COMPOSE_', 'DOCKER_', 'GIT_', 'PYTHON')) or key in ('PATH', 'HOME'):
            raise ValueError('Недопустимое имя переменной окружения')
        if not isinstance(value, str) or len(value) > 4096 or any(c in value for c in ('\0', '\r', '\n')) or value.endswith('\\'):
            raise ValueError('Значение должно быть одной строкой без завершающего обратного слеша')
        if key == 'DOMAIN' and value and (not re.fullmatch(r'[A-Za-z0-9.-]{1,253}', value) or '..' in value or value.startswith(('.', '-'))):
            raise ValueError('Домен указывается без https://, порта и пути')
        if key == 'APP_URL' and value:
            url = urllib.parse.urlsplit(value)
            if url.scheme not in ('https', 'http') or not url.hostname or url.username or url.password:
                raise ValueError('APP_URL должен быть адресом http:// или https:// без пароля')
        if key == 'APP_PORT' and value and (not value.isdigit() or not 1 <= int(value) <= 65535):
            raise ValueError('Порт должен быть числом от 1 до 65535')
        if key == 'APP_BIND' and value not in ('', '0.0.0.0', '127.0.0.1', '::'):
            raise ValueError('APP_BIND: используйте 0.0.0.0, 127.0.0.1 или ::')
        if key == 'HTTPS_PROXY_PROJECT' and value and not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', value):
            raise ValueError('Выберите модуль с работающим HTTPS-прокси')


def prepare_chrono_https(config, p, text, log):
    """Attach to an existing Caddy proxy; preserve server files and restore on failure."""
    values = {k: v for k, v, *_ in env_records(text)}
    proxy_id = values.get('HTTPS_PROXY_PROJECT', '')
    if p['kind'] not in ('chrono', 'drawing', 'pulse'):
        return None, lambda: None
    if p['kind'] == 'pulse' and not proxy_id:
        # A Pulse instance may itself own a shared HTTPS proxy overlay.
        return None, lambda: None
    if not proxy_id:
        if (Path(p['directory']) / 'compose.gitdeck-https.yaml').exists():
            raise ValueError('HTTPS уже подключён: сохраните выбранный модуль прокси. Отключение выполняется отдельно')
        return None, lambda: None
    proxy = next((item for item in config['projects'] if item['id'] == proxy_id), None)
    if not proxy:
        raise ValueError('Модуль HTTPS-прокси «' + proxy_id + '» не найден. Выберите его из списка в настройках сайта')
    if proxy['id'] == p['id']:
        raise ValueError('Для общего прокси выберите другой модуль, например марафон')
    if proxy['kind'] not in ('marathon', 'pulse'):
        raise ValueError('HTTPS-прокси должен быть модулем марафона или Пульса')
    if proxy['compose'] != 'compose.https.yaml':
        raise ValueError('Модуль прокси «' + proxy_id + '» использует ' + proxy['compose'] + '. Если на нём уже работает HTTPS, выберите compose.https.yaml в настройках этого модуля')
    url = urllib.parse.urlsplit(values.get('APP_URL', ''))
    proxy_values = {k: v for k, v, *_ in env_records(env_text(proxy))}
    if (url.scheme != 'https' or not url.hostname or not re.fullmatch(r'[a-z0-9.-]+', url.hostname)
            or url.username or url.password or url.query or url.fragment or url.path not in ('', '/')
            or url.port == 80):
        raise ValueError('Укажите HTTPS-адрес сайта, например https://chrono.vano.sbena.net/')
    port = url.port or 443
    if port == 443 and url.hostname == proxy_values.get('DOMAIN', '').lower():
        raise ValueError('Этот домен уже используется основным сайтом. Для игры задайте отдельный поддомен, например https://chrono.vano.sbena.net/')
    # Full Compose output includes the OTHER project's bot token. Never log it.
    details = json.loads(compose(proxy, ['config', '--format', 'json'], None))
    network = details.get('networks', {}).get('default', {}).get('name')
    if not network or not re.fullmatch(r'[A-Za-z0-9_.-]+', network):
        raise ValueError('Не найдена Docker-сеть HTTPS-прокси')
    caddy = Path(proxy['directory']) / 'deploy' / 'Caddyfile'
    overlay = Path(proxy['directory']) / 'compose.gitdeck-https.yaml'
    local = Path(p['directory']) / 'compose.gitdeck-https.yaml'
    files = [caddy, overlay, local]
    if any(file.is_symlink() for file in files) or not caddy.is_file():
        raise ValueError('Не найден обычный файл deploy/Caddyfile HTTPS-прокси')
    previous = {file: file.read_bytes() if file.exists() else None for file in files}
    def restore():
        for file, content in previous.items():
            if content is None:
                file.unlink(missing_ok=True)
            else:
                # Keep the inode: Caddyfile is bind-mounted in the running container.
                with file.open('wb') as target:
                    target.write(content)
    try:
        alias = 'gitdeck-' + p['id']
        primary_alias = 'gitdeck-primary-' + proxy['id']
        marker = '# GitDeck ' + p['id']
        original = previous[caddy].decode('utf-8')
        block = marker + ' BEGIN\nhttps://' + url.netloc + ' {\n    encode gzip zstd\n    reverse_proxy ' + alias + ':80\n}\n' + marker + ' END'
        pattern = re.escape(marker + ' BEGIN') + r'.*?' + re.escape(marker + ' END')
        updated = re.sub(pattern, lambda _: block, original, flags=re.S) if marker + ' BEGIN' in original else original.rstrip() + '\n\n' + block + '\n'
        # Compose adds the service-name alias "web" to every attached network,
        # including external ones. Multiple sites therefore make "web" ambiguous.
        # Keep the primary site's route on a dedicated, stable network alias.
        updated = re.sub(r'(?m)^(\s*reverse_proxy\s+)(?:http://)?web:80(\s*(?:#.*)?)$',
                         lambda match: match[1] + primary_alias + ':80' + match[2], updated)
        hook_marker = '# GitDeck bot ' + p['id']
        hook_pattern = re.escape(hook_marker + ' BEGIN') + r'.*?' + re.escape(hook_marker + ' END')
        hook_path = '/gitdeck-telegram-' + p['id']
        webhook = 'https://' + url.hostname + hook_path
        hook = hook_marker + ' BEGIN\n    handle ' + hook_path + ' {\n        rewrite * /telegram/webhook\n        reverse_proxy ' + alias + ':80\n    }\n    ' + hook_marker + ' END'
        if port == 443:
            # The game's own HTTPS origin accepts Telegram webhooks on port 443.
            # No dependency on the main site's Caddyfile formatting is needed.
            updated = re.sub(hook_pattern, '', updated, flags=re.S)
            webhook = 'https://' + url.netloc + '/telegram/webhook'
        elif hook_marker + ' BEGIN' in updated:
            updated = re.sub(hook_pattern, lambda _: hook, updated, flags=re.S)
        elif '{$DOMAIN} {' in updated:
            updated = updated.replace('{$DOMAIN} {', '{$DOMAIN} {\n    ' + hook, 1)
        else:
            raise ValueError('Для бота нужен основной блок {$DOMAIN} в Caddyfile общего прокси')
        # Never take another site's listener silently.
        without_own = re.sub(pattern, '', original, flags=re.S)
        if re.search(r'(?m)^\s*(?:https://)?' + re.escape(url.netloc) + r'\s*\{', without_own):
            raise ValueError('Этот HTTPS-адрес уже занят другим маршрутом прокси')
        with caddy.open('w', encoding='utf-8', newline='\n') as target:
            target.write(updated)
        proxy_overlay = json.loads(previous[overlay]) if previous[overlay] else {'services': {'proxy': {'ports': []}}}
        primary = proxy_overlay.setdefault('services', {}).setdefault('web', {})
        aliases = primary.setdefault('networks', {}).setdefault('default', {}).setdefault('aliases', [])
        if primary_alias not in aliases:
            aliases.append(primary_alias)
        ports = proxy_overlay['services']['proxy']['ports']
        listener = str(port) + ':' + str(port)
        if port != 443 and listener not in ports:
            ports.append(listener)
        overlay.write_text(json.dumps(proxy_overlay, indent=2), encoding='utf-8')
        # !reset requires Compose 2.24+; remove the old HTTP listener before Caddy claims it.
        site_env = '      QUIZ_TRUST_PROXY: "1"\n' if p['kind'] == 'pulse' else '      TELEGRAM_BOT_TOKEN: ${TELEGRAM_BOT_TOKEN:-}\n      TELEGRAM_BOT_USERNAME: ${TELEGRAM_BOT_USERNAME:-}\n      TELEGRAM_WEBHOOK_URL: ' + webhook + '\n      cookie_secure: "true"\n      cookie_samesite: None\n'
        local.write_text('services:\n  web:\n    ports: !reset []\n    environment:\n' + site_env + '    networks:\n      default: {}\n      gitdeck_https:\n        aliases: [' + alias + ']\nnetworks:\n  gitdeck_https:\n    external: true\n    name: ' + network + '\n', encoding='utf-8')
        compose(proxy, ['exec', '-T', 'proxy', 'caddy', 'validate', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'], log)
        return proxy, restore
    except Exception:
        restore()
        raise


def patch_env(text, changes):
    validate_env_changes(changes)
    records = env_records(text)
    last = {key: start for key, value, start, end in records}
    lines = dict(changes)
    for key, value, start, end in reversed(records):
        if key in changes:
            replacement = key + "='" + changes[key].replace("'", "\\'") + "'\n" if last[key] == start else ''
            text = text[:start] + replacement + text[end:]
            lines.pop(key, None)
    for key, value in lines.items():
        if text and not text.endswith('\n'):
            text += '\n'
        text += key + "='" + value.replace("'", "\\'") + "'\n"
    return text


def write_env(p, text):
    file = env_file(p)
    temp = file.with_name('.env.gitdeck-' + secrets.token_hex(6))
    try:
        temp.write_text(text, encoding='utf-8')
        os.chmod(temp, 0o600)
        os.replace(temp, file)
    finally:
        temp.unlink(missing_ok=True)


class RedactedLog:
    def __init__(self, log, values):
        self.log, self.values = log, sorted(set(v for v in values if len(v) >= 4), key=len, reverse=True)

    def write(self, text):
        for value in self.values:
            text = text.replace(value, '[секрет скрыт]')
        return self.log.write(text)

    def flush(self):
        self.log.flush()


def apply_environment(config, p, job, log):
    folder = Path(config['state_dir']) / 'jobs' / job
    payload = json.loads((folder / 'environment.json').read_text(encoding='utf-8'))
    old = env_text(p)
    if env_revision(old) != payload['env_revision']:
        raise ValueError('Файл .env изменился после открытия формы. Откройте настройки заново')
    new = patch_env(old, payload['changes'])
    if p['kind'] == 'drawing':
        for key, minimum in [('ADMIN_PASSWORD', 12), ('GAME_ACCESS_CODE', 8)]:
            if key in payload['changes'] and not minimum <= len(payload['changes'][key]) <= 255:
                raise ValueError(key + ': минимум ' + str(minimum) + ' символов')
        if 'AI_DAILY_LIMIT' in payload['changes'] and not re.fullmatch(r'[1-9][0-9]{0,2}|1000', payload['changes']['AI_DAILY_LIMIT']):
            raise ValueError('AI_DAILY_LIMIT: от 1 до 1000 оценок')
    if p['kind'] == 'chrono':
        existing = {k: v for k, v, *_ in env_records(old)}
        for key in ('DB_DATABASE', 'DB_USERNAME', 'DB_PASSWORD'):
            if key in payload['changes'] and payload['changes'][key] != existing.get(key):
                raise ValueError('Реквизиты созданной PostgreSQL нельзя менять через .env: это не меняет саму базу')
        if 'ADMIN_PASSWORD' in payload['changes'] and not 12 <= len(payload['changes']['ADMIN_PASSWORD']) <= 255:
            raise ValueError('Пароль администратора должен содержать от 12 до 255 символов')
        if 'ADMIN_USERNAME' in payload['changes'] and not re.fullmatch(r'[A-Za-z0-9_-]{3,30}', payload['changes']['ADMIN_USERNAME']):
            raise ValueError('Логин администратора: 3–30 латинских букв, цифры, дефис или подчёркивание')
    previous = folder / 'previous.env'
    previous.write_text(old, encoding='utf-8')
    os.chmod(previous, 0o600)
    values = [v for k, v, *_ in env_records(old) if k not in PUBLIC_ENV]
    values += [v for k, v in payload['changes'].items() if k not in PUBLIC_ENV]
    protected_log = RedactedLog(log, values)
    shared_proxy, restore_https = None, lambda: None
    services_touched = False
    try:
        status_update(config, job, 'configuring')
        write_env(p, new)
        shared_proxy, restore_https = prepare_chrono_https(config, p, new, protected_log)
        compose(p, ['config', '--quiet'], protected_log)
        services_touched = True
        start_services(p, protected_log, build=False)
        if shared_proxy:
            compose(shared_proxy, ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', 'web'], protected_log)
            compose(shared_proxy, ['up', '-d', '--no-deps', 'proxy'], protected_log)
            compose(shared_proxy, ['exec', '-T', 'proxy', 'caddy', 'reload', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'], protected_log)
        services = compose(p, ['config', '--services'], protected_log).decode().splitlines()
        if 'proxy' in services:
            compose(p, ['up', '-d', '--no-deps', 'proxy'], protected_log)
        status_update(config, job, 'success')
        protected_log.write('\nНастройки применены. Домен DNS настраивается отдельно у провайдера.\n')
    except Exception as error:
        protected_log.write('\nПричина ошибки: ' + str(error) + '\n')
        protected_log.write('\nНе удалось применить настройки; возвращается прежний .env.\n')
        restore_https()
        write_env(p, old)
        try:
            if shared_proxy and services_touched:
                compose(shared_proxy, ['up', '-d', '--no-deps', '--wait', '--wait-timeout', '180', 'web'], protected_log)
                compose(shared_proxy, ['up', '-d', '--no-deps', 'proxy'], protected_log)
                compose(shared_proxy, ['exec', '-T', 'proxy', 'caddy', 'reload', '--config', '/etc/caddy/Caddyfile', '--adapter', 'caddyfile'], protected_log)
            if services_touched:
                start_services(p, protected_log, build=False)
                services = compose(p, ['config', '--services'], protected_log).decode().splitlines()
                if 'proxy' in services:
                    compose(p, ['up', '-d', '--no-deps', 'proxy'], protected_log)
        except Exception as rollback_error:
            protected_log.write('\nОшибка перезапуска при возврате прежних настроек: ' + str(rollback_error) + '\n')
        raise RuntimeError('Ошибка применения настроек сайта. См. журнал задания') from None


def connect_marathon(config, p, job, log):
    """Connect two installed sites without copying credentials or reading results."""
    folder = Path(config['state_dir']) / 'jobs' / job
    payload = json.loads((folder / 'environment.json').read_text(encoding='utf-8'))
    marathon = next(x for x in config['projects'] if x['id'] == payload['marathon'] and x['kind'] == 'marathon')
    if p['kind'] != 'pulse' or not (Path(p['directory']) / 'assets/community.php').is_file() or not (Path(marathon['directory']) / 'lib/pulse.php').is_file():
        raise ValueError('Сначала обновите Пульс и марафон из Git до версии с общими аккаунтами')
    old_pulse, old_marathon = env_text(p), env_text(marathon)
    if env_revision(old_pulse) != payload['pulse_revision'] or env_revision(old_marathon) != payload['marathon_revision']:
        raise ValueError('Настройки сайтов изменились. Откройте подключение заново')
    values = {k: v for k, v, *_ in env_records(old_marathon)}
    marathon_url = values.get('APP_URL', '')
    if not marathon_url.startswith('https://') and values.get('DOMAIN'):
        marathon_url = 'https://' + values['DOMAIN']
    for value in (marathon_url, payload['pulse_url']):
        parsed = urllib.parse.urlsplit(value)
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment or parsed.path not in ('', '/') or parsed.port not in (None, 443):
            raise ValueError('Для общих аккаунтов укажите HTTPS-адреса сайтов без нестандартных портов')
    key = secrets.token_hex(32)
    pulse_changes = {'MARATHON_URL': marathon_url.rstrip('/'), 'APP_URL': payload['pulse_url'], 'PULSE_BRIDGE_SECRET': key}
    if marathon['compose'] == 'compose.https.yaml':
        pulse_changes['HTTPS_PROXY_PROJECT'] = marathon['id']
    files = [env_file(p), env_file(marathon)]
    for site in (p, marathon):
        files.append(validate_destination(Path(site['directory']), 'compose.gitdeck-community.yaml'))
    previous = {file: file.read_bytes() if file.exists() else None for file in files}
    for i, (file, data) in enumerate(previous.items()):
        if data is not None:
            backup = folder / ('connection-backup-' + str(i))
            backup.write_bytes(data); os.chmod(backup, 0o600)
    restore_https = lambda: None
    proxy = None
    safe_log = RedactedLog(log, [key])
    try:
        status_update(config, job, 'configuring')
        write_env(p, patch_env(old_pulse, pulse_changes))
        write_env(marathon, patch_env(old_marathon, {'PULSE_URL': payload['pulse_url'].rstrip('/'), 'PULSE_BRIDGE_SECRET': key}))
        for site, names in ((p, ['APP_URL','MARATHON_URL','PULSE_BRIDGE_SECRET']), (marathon, ['PULSE_URL','PULSE_BRIDGE_SECRET'])):
            overlay = {'services': {'web': {'environment': {name: '${' + name + ':-}' for name in names}}}}
            (Path(site['directory']) / 'compose.gitdeck-community.yaml').write_text(json.dumps(overlay), encoding='utf-8')
        proxy, restore_https = prepare_chrono_https(config, p, env_text(p), safe_log)
        for site in (p, marathon):
            compose(site, ['config', '--quiet'], safe_log)
            start_services(site, safe_log, build=False)
        if proxy:
            compose(proxy, ['up','-d','--no-deps','--wait','--wait-timeout','180','web'], safe_log)
            compose(proxy, ['up','-d','--no-deps','proxy'], safe_log)
            compose(proxy, ['exec','-T','proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'], safe_log)
        safe_log.write('\nАккаунты подключены. В Пульсе откройте «Участники» → «Обновить список из марафона».\n')
        status_update(config, job, 'success')
    except Exception:
        restore_https()
        for file, data in previous.items():
            if data is None:
                file.unlink(missing_ok=True)
            else:
                file.write_bytes(data)
                if file.name == '.env': os.chmod(file, 0o600)
        for site in (p, marathon):
            try: start_services(site, safe_log, build=False)
            except Exception: safe_log.write('\nНе удалось перезапустить сайт при возврате настроек. Проверьте его статус.\n')
        if proxy:
            try: compose(proxy, ['exec','-T','proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'], safe_log)
            except Exception: safe_log.write('\nПроверьте перезагрузку HTTPS-прокси после возврата настроек.\n')
        raise RuntimeError('Не удалось подключить аккаунты. Прежние настройки восстановлены; см. журнал') from None


def start_pulse_bot(config, p, job, log):
    if p['kind'] != 'pulse' or not (Path(p['directory']) / 'assets/pulse-bot-worker.php').is_file():
        raise ValueError('Сначала обновите Пульс из Git до версии с отдельным Telegram-ботом')
    values = {k:v for k,v,*_ in env_records(env_text(p))}
    if not re.fullmatch(r'[0-9]+:[A-Za-z0-9_-]+', values.get('TELEGRAM_BOT_TOKEN','')) or not re.fullmatch(r'[A-Za-z0-9_]{5,32}',values.get('TELEGRAM_BOT_USERNAME','')):
        raise ValueError('В настройках Пульса задайте токен и имя нового бота без @')
    if not values.get('MARATHON_URL') or len(values.get('PULSE_BRIDGE_SECRET','')) < 32:
        raise ValueError('Сначала нажмите «Подключить марафон» на карточке Пульса')
    for other in config['projects']:
        if other['id'] != p['id'] and other['kind'] in ('marathon','chrono','drawing'):
            other_values = {k:v for k,v,*_ in env_records(env_text(other))}
            if other_values.get('TELEGRAM_BOT_TOKEN') == values['TELEGRAM_BOT_TOKEN']:
                raise ValueError('Этот токен уже используется другим сайтом. Создайте отдельного нового бота для Пульса')
    safe_log = RedactedLog(log,[values['TELEGRAM_BOT_TOKEN'],values['PULSE_BRIDGE_SECRET']])
    file = validate_destination(Path(p['directory']), 'compose.gitdeck-telegram.yaml')
    previous = file.read_bytes() if file.exists() else None
    details = json.loads(compose(p,['config','--format','json'],None))
    web = details.get('services',{}).get('web',{})
    project_name = details.get('name','')
    if not re.fullmatch(r'[a-zA-Z0-9_-]+',project_name):raise ValueError('Не найдено имя Docker-проекта Пульса')
    data_dir = web.get('environment',{}).get('QUIZ_DATA_DIR','/var/lib/pulse')
    mounts = [v for v in web.get('volumes',[]) if isinstance(v,dict) and v.get('target') == data_dir]
    if not mounts:raise ValueError('Не найден постоянный том базы Пульса')
    env = {key:'${'+key+':-}' for key in ['TELEGRAM_BOT_TOKEN','TELEGRAM_BOT_USERNAME','MARATHON_URL','PULSE_BRIDGE_SECRET','APP_URL']}
    overlay = {'services':{'web':{'environment':env},'bot':{
        'image':web.get('image') or project_name+'-web','restart':'unless-stopped','user':'www-data',
        'command':['php','/var/www/html/assets/pulse-bot-worker.php'],'healthcheck':{'disable':True},
        'environment':dict(env,QUIZ_DATA_DIR=data_dir),'volumes':mounts,
        'depends_on':{'web':{'condition':'service_healthy'}},
        'logging':{'driver':'json-file','options':{'max-size':'10m','max-file':'3'}}}}}
    try:
        status_update(config,job,'configuring')
        file.write_text(json.dumps(overlay,indent=2),encoding='utf-8')
        compose(p,['config','--quiet'],safe_log)
        compose(p,['run','--rm','--no-deps','-T','web','php','/var/www/html/assets/pulse-bot-worker.php','--check'],safe_log)
        start_services(p,safe_log,build=False)
        status_update(config,job,'success')
        safe_log.write('\nОтдельный бот Пульса запущен. На странице входа Пульса доступна кнопка «Войти через Telegram».\n')
    except Exception:
        if previous is None:
            try:compose(p,['rm','-sf','bot'],safe_log)
            except Exception:pass
            file.unlink(missing_ok=True)
        else:file.write_bytes(previous)
        try:start_services(p,safe_log,build=False)
        except Exception:safe_log.write('\nПроверьте запуск Пульса после возврата настроек.\n')
        raise RuntimeError('Бот Пульса не запустился. Проверьте токен, имя и отсутствие webhook/другого экземпляра бота; прежние настройки запуска восстановлены') from None


def enqueue(server, p, action, ref='', payload=None):
    job = secrets.token_hex(12)
    with db_open(server.config) as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute("SELECT 1 FROM jobs WHERE status NOT IN ('success','failed')").fetchone():
            raise ValueError('Дождитесь завершения текущего задания')
        db.execute('INSERT INTO jobs (id,project,action,status,created,updated,target_ref) VALUES (?,?,?,?,?,?,?)',
                   (job, p['id'], action, 'queued', time.time(), time.time(), ref))
    folder = Path(server.config['state_dir']) / 'jobs' / job
    try:
        folder.mkdir(parents=True, mode=0o700)
        for name, value in [('project.json', p)] + ([('environment.json', payload)] if payload is not None else []):
            file = folder / name
            file.write_text(json.dumps(value), encoding='utf-8')
            os.chmod(file, 0o600)
        snapshot = folder / 'worker.py'
        shutil.copy2(__file__, snapshot)
        run(['systemd-run', '--quiet', '--collect', '--unit=gitdeck-job-' + job,
             '--property=Type=exec', sys.executable, str(snapshot), '--config', server.config_path,
             'worker', '--job', job], timeout=20)
    except Exception as exc:
        status_update(server.config, job, 'failed', str(exc))
        raise
    return job


def revisions(config, p, branch):
    with REF_LOCK:
        cache = Path(config['state_dir']) / 'ref-cache' / (p['id'] + '-' + hashlib.sha256(p['repo'].encode()).hexdigest()[:12])
        cache.parent.mkdir(parents=True, exist_ok=True)
        env = git_environment(p)
        if not cache.exists():
            run(['git', 'init', '--bare', str(cache)], env=env, timeout=60)
        prefix = ['git', '--git-dir', str(cache)]
        run(prefix + ['fetch', '--no-tags', '--prune', '--force', '--', p['repo'], '+refs/heads/*:refs/heads/*'], env=env, timeout=60)
        branches = run(prefix + ['for-each-ref', '--format=%(refname:strip=2)', 'refs/heads/'], env=env, timeout=30).decode().splitlines()
        if branch not in branches:
            return {'branches': branches, 'commits': [], 'error': 'Выбранной ветки нет в репозитории'}
        raw = run(prefix + ['log', '-30', '-z', '--format=%H%x00%ct%x00%s', 'refs/heads/' + branch, '--'], env=env, timeout=30).decode('utf-8', errors='replace')
        parts = raw.rstrip('\0').split('\0')
        commits = [{'sha': parts[i], 'time': int(parts[i + 1]), 'subject': parts[i + 2]} for i in range(0, len(parts) - 2, 3)] if raw else []
        return {'branches': branches, 'commits': commits}


def extract_source(data, target, kind):
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        for item in archive:
            path = PurePosixPath(item.name)
            if path.is_absolute() or '..' in path.parts or '\\' in item.name:
                raise ValueError('Опасный путь в Git-архиве')
            if not allowed(item.name.rstrip('/'), kind):
                continue
            if not (item.isfile() or item.isdir()):
                raise ValueError('Ссылки и специальные файлы в коде не поддерживаются')
            dest = target.joinpath(*path.parts)
            if item.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            else:
                dest.parent.mkdir(parents=True, exist_ok=True)
                with archive.extractfile(item) as src, dest.open('wb') as out:
                    shutil.copyfileobj(src, out)
    actual_kind = kind['kind'] if isinstance(kind, dict) else kind
    required = kind['paths'] if actual_kind == 'docker' else REQUIRED[actual_kind]
    for name in required:
        if not (target / name).exists():
            raise ValueError('В репозитории отсутствует обязательный файл: ' + name)


def checkout(p, config, folder, log, target_ref=None):
    cache = Path(config['state_dir']) / 'repos' / (p['id'] + '-' + hashlib.sha256(p['repo'].encode()).hexdigest()[:12])
    cache.parent.mkdir(parents=True, exist_ok=True)
    env = git_environment(p)
    if not cache.exists():
        run(['git', 'init', '--bare', str(cache)], log, env=env)
    chosen = valid_ref(target_ref or p['branch'])
    is_commit = bool(re.fullmatch(r'[a-fA-F0-9]{7,64}', chosen))
    if is_commit:
        # Fetch advertised branch history first, so abbreviated historical SHAs resolve too.
        run(['git', '--git-dir', str(cache), 'fetch', '--no-tags', '--force', '--', p['repo'],
             '+refs/heads/*:refs/heads/*'], log, env=env)
        full = run(['git', '--git-dir', str(cache), 'rev-parse', '--verify', chosen + '^{commit}'], env=env).decode().strip()
        run(['git', '--git-dir', str(cache), 'update-ref', 'refs/heads/deploy', full], env=env)
    else:
        run(['git', '--git-dir', str(cache), 'fetch', '--no-tags', '--force', '--', p['repo'],
             '+refs/heads/' + chosen + ':refs/heads/deploy'], log, env=env)
    sha = run(['git', '--git-dir', str(cache), 'rev-parse', 'refs/heads/deploy'], env=env).decode().strip()
    if not re.fullmatch('[a-f0-9]{40,64}', sha):
        raise ValueError('Git вернул некорректный commit')
    ref = sha + (':' + p.get('subdir', '') if p.get('subdir') else '')
    archive = run(['git', '--git-dir', str(cache), 'archive', '--format=tar', ref], env=env)
    extract_source(archive, folder, p)
    return sha


def validate_destination(dest, name):
    root = dest.resolve()
    target = dest / name
    if not target.resolve().is_relative_to(root):
        raise ValueError('Файл выходит за каталог проекта: ' + name)
    current = target
    while current != dest:
        if current.is_symlink():
            raise ValueError('Символические ссылки в рабочих файлах не поддерживаются')
        current = current.parent
    return target


def copy_code(source, dest, kind, save=False):
    """Only managed code paths; never .env, databases, compose, Dockerfile or Caddy."""
    dest.mkdir(parents=True, exist_ok=True)
    for name in code_paths(kind) if isinstance(kind, dict) else LAYOUT[kind]:
        validate_destination(dest, name)
        src = validate_destination(source, name)
        out = dest / name
        if isinstance(kind, dict) and kind['kind'] == 'docker':
            for base in (src, out):
                if base.is_dir() and any(runtime_path(str(child.relative_to(base))) for child in base.rglob('*')):
                    raise ValueError('Внутри папки кода есть данные или .env. Укажите более узкие пути для обновления')
        if src.is_dir() and any(child.is_symlink() for child in src.rglob('*')):
            raise ValueError('Символические ссылки внутри кода не поддерживаются')
        if out.exists() and not save:
            if out.is_dir():
                shutil.rmtree(out)
            else:
                out.unlink()
        if src.is_dir():
            shutil.copytree(src, out, dirs_exist_ok=True)
        elif src.is_file():
            out.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, out)


def status_update(config, job, status, error='', sha=None):
    with db_open(config) as db:
        db.execute('UPDATE jobs SET status=?, updated=?, error=? WHERE id=?', (status, time.time(), error, job))
        if sha:
            db.execute('UPDATE jobs SET commit_sha=? WHERE id=?', (sha, job))


def database_backup(p, jobdir, log):
    if p['kind'] == 'chrono':
        compose(p, ['up', '-d', '--wait', '--wait-timeout', '120', 'db'], log)
        compose(p, ['run', '--rm', '--no-deps', '--user', 'root', '-v', str(jobdir) + ':/gitdeck-backup',
                    '--entrypoint', 'sh', 'db', '-ec',
                    'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_dump -h db -U "$POSTGRES_USER" -d "$POSTGRES_DB" -Fc -f /gitdeck-backup/database.dump; chmod 600 /gitdeck-backup/database.dump'], log)
        if not (jobdir / 'database.dump').is_file():
            raise RuntimeError('Не создана резервная копия PostgreSQL')
        return
    tool = '/opt/sketch/backup.php' if p['kind'] == 'drawing' else '/opt/pulse/backup.php' if p['kind'] == 'pulse' else '/opt/marathon/backup.php'
    compose(p, ['run', '--rm', '--no-deps', '--user', 'root', '-v', str(jobdir) + ':/gitdeck-backup',
                '--entrypoint', 'php', 'web', tool, '/gitdeck-backup/data.sqlite'], log)
    if not (jobdir / 'data.sqlite').is_file():
        raise RuntimeError('Не создана резервная копия базы')


def database_restore(p, jobdir, log):
    if p['kind'] == 'chrono':
        compose(p, ['run', '--rm', '--no-deps', '--user', 'root', '-v', str(jobdir) + ':/gitdeck-backup:ro',
                    '--entrypoint', 'sh', 'db', '-ec',
                    'export PGPASSWORD="$POSTGRES_PASSWORD"; pg_restore -h db -U "$POSTGRES_USER" -d postgres --create --clean --if-exists --no-owner --exit-on-error /gitdeck-backup/database.dump'], log)
        return
    # SQLite backup is taken with web/bot stopped. Restore DB and remove matching WAL files.
    location = '/var/lib/sketch/game.sqlite' if p['kind'] == 'drawing' else '/var/lib/pulse/quiz.sqlite' if p['kind'] == 'pulse' else '/var/lib/marathon/marathon.sqlite'
    php = '$p=$argv[1]; if(!copy("/gitdeck-backup/data.sqlite",$p))exit(1); foreach(["-wal","-shm"] as $s)if(is_file($p.$s))unlink($p.$s); chown($p,"www-data"); chmod($p,0660);'
    compose(p, ['run', '--rm', '--no-deps', '--user', 'root', '-v', str(jobdir) + ':/gitdeck-backup:ro',
                '--entrypoint', 'php', 'web', '-r', php, location], log)


def bootstrap_chrono(p, source):
    """Provision only an empty directory; never adopt or overwrite an unknown site."""
    dest = Path(p['directory'])
    if dest.exists() and any(dest.iterdir()):
        raise ValueError('Для первой установки выберите пустой каталог')
    dest.mkdir(parents=True, exist_ok=True)
    validate_destination(dest, p['compose'])
    shutil.copy2(source / 'ops/compose.yaml', dest / p['compose'])
    if p['kind'] == 'drawing':
        write_env(p, patch_env('', {'APP_URL': 'https://draw.vano.sbena.net/', 'APP_PORT': '8084',
            'APP_BIND': '0.0.0.0', 'ADMIN_PASSWORD': secrets.token_urlsafe(32),
            'GAME_ACCESS_CODE': secrets.token_urlsafe(12), 'OPENAI_API_KEY': '',
            'OPENAI_MODEL': 'gpt-4.1-mini', 'AI_DAILY_LIMIT': '100'}))
        return
    write_env(p, patch_env('', {'APP_URL': 'https://vano.sbena.net/', 'APP_PORT': '8082',
        'APP_BIND': '0.0.0.0', 'DB_DATABASE': 'chrono', 'DB_USERNAME': 'chrono',
        'DB_PASSWORD': secrets.token_urlsafe(32), 'ADMIN_USERNAME': 'admin',
        'ADMIN_PASSWORD': secrets.token_urlsafe(32)}))


def deploy(config, p, job, log):
    jobdir = Path(config['state_dir']) / 'jobs' / job
    source = jobdir / 'new'
    old = jobdir / 'previous'
    dest = Path(p['directory'])
    sha = checkout(p, config, source, log, p['_target_ref']) if p.get('_target_ref') else checkout(p, config, source, log)
    status_update(config, job, 'preparing', sha=sha)
    first_install = p['kind'] in ('chrono', 'drawing') and not (dest / p['compose']).exists()
    if first_install:
        bootstrap_chrono(p, source)
    if p['kind'] in ('chrono', 'drawing'):
        log = RedactedLog(log, [v for k, v, *_ in env_records(env_text(p)) if k not in PUBLIC_ENV])
    if p['kind'] == 'self':
        run([sys.executable, '-m', 'py_compile', str(source / 'app.py')], log)
        validation = jobdir / 'validation-config.json'
        validation.write_text(json.dumps(config), encoding='utf-8')
        check = 'import importlib.util,sys;s=importlib.util.spec_from_file_location("candidate",sys.argv[1]);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);m.load_config(sys.argv[2])'
        run([sys.executable, '-c', check, str(source / 'app.py'), str(validation)], log)
        # The config is outside code; the independent job runs a frozen copy of this worker.
        if dest.resolve() != Path(__file__).resolve().parent and not (dest / 'app.py').is_file():
            raise ValueError('Каталог панели не содержит установленного app.py')
    else:
        if not (dest / p['compose']).is_file():
            raise ValueError('Не найден compose-файл установленного сайта')
        compose(p, ['config', '--quiet'], log)
    copy_code(dest, old, p, save=True)
    # Remember actual previous commit independently of candidate or failed deployments.
    with db_open(config) as db:
        prev = db.execute('SELECT commit_sha FROM versions WHERE project=?', (p['id'],)).fetchone()
    (jobdir / 'previous-version.json').write_text(json.dumps({'sha': prev[0] if prev else ''}))
    stopped = False
    mutated = False
    try:
        if p['kind'] != 'self' and not first_install:
            status_update(config, job, 'backup', sha=sha)
            stopped = True  # A partially failed stop must also be recovered.
            compose(p, ['stop'] + project_services(p), log)
            if p['kind'] != 'docker':
                database_backup(p, jobdir, log)
            else:
                log.write('\nDocker-модуль: сохраняется код. Резервное копирование внешней базы выполняется отдельно.\n')
        mutated = True
        copy_code(source, dest, p)
        status_update(config, job, 'installing', sha=sha)
        if p['kind'] != 'self':
            start_services(p, log)
        if p['kind'] == 'self':
            run(['systemctl', 'restart', 'gitdeck'], log, timeout=60)
            # Restart returning success must include a responsive HTTP process.
            import urllib.request
            for _ in range(30):
                try:
                    with urllib.request.urlopen('http://127.0.0.1:' + str(config.get('port', 8120)) + '/health', timeout=2) as response:
                        if response.status == 200:
                            break
                except OSError:
                    time.sleep(1)
            else:
                raise RuntimeError('Новая панель не прошла проверку запуска')
        with db_open(config) as db:
            db.execute('INSERT OR REPLACE INTO versions VALUES (?, ?, ?)', (p['id'], sha, time.time()))
        status_update(config, job, 'success', sha=sha)
    except Exception as original:
        log.write('\nОшибка установки: ' + str(original) + '\n')
        log.flush()
        if mutated:
            status_update(config, job, 'restoring', sha=sha)
            if p['kind'] != 'self':
                compose(p, ['stop'] + project_services(p), log)
            if first_install:
                log.write('\nПервая установка не завершена. Код, данные и настройки оставлены для повторной попытки.\n')
                raise original
            copy_code(old, dest, p)
            if p['kind'] != 'self':
                if p['kind'] != 'docker':
                    database_restore(p, jobdir, log)
                start_services(p, log)
            else:
                run(['systemctl', 'restart', 'gitdeck'], log, timeout=60)
            with db_open(config) as db:
                if prev:
                    db.execute('INSERT OR REPLACE INTO versions VALUES (?, ?, ?)', (p['id'], prev[0], time.time()))
                else:
                    db.execute('DELETE FROM versions WHERE project=?', (p['id'],))
            log.write('\nПредыдущий код и база восстановлены.\n')
        elif stopped:
            start_services(p, log, build=False)
        raise


def work(config, job):
    import fcntl
    with (Path(config['state_dir']) / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with db_open(config) as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
        if not row or row['status'] != 'queued':
            raise ValueError('Задание не ожидает выполнения')
        jobdir = Path(config['state_dir']) / 'jobs' / job
        project_file = jobdir / 'project.json'
        p = json.loads(project_file.read_text(encoding='utf-8')) if project_file.is_file() else dict(next(x for x in config['projects'] if x['id'] == row['project']))
        if row['target_ref']:
            p['_target_ref'] = row['target_ref']
        with (jobdir / 'output.log').open('a', encoding='utf-8') as log:
            try:
                if row['action'] == 'configure':
                    apply_environment(config, p, job, log)
                elif row['action'] == 'connect_marathon':
                    connect_marathon(config, p, job, log)
                elif row['action'] == 'pulse_bot':
                    start_pulse_bot(config, p, job, log)
                else:
                    deploy(config, p, job, log)
            except Exception as exc:
                log.write('\nОШИБКА: ' + str(exc) + '\n')
                status_update(config, job, 'failed', str(exc))


class Panel(http.server.BaseHTTPRequestHandler):
    sessions = {}
    attempts = []
    mutex = threading.RLock()

    def log_message(self, *_):
        pass

    def send(self, code, data, mime='application/json; charset=utf-8', cookie=None):
        body = data if isinstance(data, bytes) else json.dumps(data, ensure_ascii=False).encode()
        self.send_response(code)
        self.send_header('Content-Type', mime)
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:
            self.send_header('Set-Cookie', cookie)
        self.end_headers()
        self.wfile.write(body)

    def session(self):
        cookie = http.cookies.SimpleCookie()
        try:
            cookie.load(self.headers.get('Cookie', ''))
            key = cookie['gitdeck'].value if 'gitdeck' in cookie else ''
        except http.cookies.CookieError:
            return None
        with self.mutex:
            Panel.sessions = {k: v for k, v in Panel.sessions.items() if v['expires'] > time.time()}
            return Panel.sessions.get(key)

    def valid_host(self):
        return self.headers.get('Host', '') in ('localhost:' + str(self.server.server_port), '127.0.0.1:' + str(self.server.server_port))

    def do_GET(self):
        if not self.valid_host():
            return self.send(403, {'error': 'Откройте панель через localhost и SSH-туннель'})
        url = urllib.parse.urlsplit(self.path)
        if url.path == '/health':
            return self.send(200, {'ok': True, 'version': VERSION})
        if url.path == '/':
            return self.send(200, Path(__file__).with_name('index.html').read_bytes(), 'text/html; charset=utf-8')
        session = self.session()
        if not session:
            return self.send(401, {'error': 'Войдите в панель'})
        if url.path == '/api/state':
            with db_open(self.server.config) as db:
                jobs = [dict(r) for r in db.execute('SELECT * FROM jobs ORDER BY created DESC LIMIT 30')]
                versions = {r['project']: dict(r) for r in db.execute('SELECT * FROM versions')}
            projects = [{k: p[k] for k in ('id', 'name', 'kind', 'repo', 'branch', 'subdir', 'directory', 'compose', 'profiles', 'services', 'paths', 'main_service', 'wait_health') if k in p}
                        for p in self.server.config['projects']]
            return self.send(200, {'projects': projects, 'jobs': jobs, 'versions': versions,
                                   'csrf': session['csrf'], 'version': VERSION, 'demo': self.server.demo,
                                   'config_revision': config_revision(self.server.config)})
        if url.path == '/api/log':
            job = urllib.parse.parse_qs(url.query).get('job', [''])[0]
            if not re.fullmatch('[a-f0-9]{24}', job):
                return self.send(400, {'error': 'Некорректный журнал'})
            file = Path(self.server.config['state_dir']) / 'jobs' / job / 'output.log'
            if not file.is_file():
                return self.send(200, {'log': 'Ожидание запуска…'})
            with file.open('rb') as stream:
                stream.seek(max(0, file.stat().st_size - 65536))
                content = stream.read().decode('utf-8', errors='replace')
            return self.send(200, {'log': content})
        if url.path == '/api/environment':
            project = urllib.parse.parse_qs(url.query).get('project', [''])[0]
            p = next((x for x in self.server.config['projects'] if x['id'] == project), None)
            if not p:
                return self.send(404, {'error': 'Модуль не найден'})
            try:
                return self.send(200, env_settings(p))
            except (ValueError, OSError):
                return self.send(400, {'error': 'Не удалось прочитать .env этого сайта'})
        self.send(404, {'error': 'Не найдено'})

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
            return self.send(403, {'error': 'Недопустимый источник запроса'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 16384:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError()
        except (ValueError, json.JSONDecodeError):
            return self.send(400, {'error': 'Некорректный запрос'})
        if self.path == '/api/login':
            with self.mutex:
                Panel.attempts = [t for t in Panel.attempts if t > time.time() - 300]
                if len(Panel.attempts) >= 10:
                    return self.send(429, {'error': 'Слишком много попыток. Подождите 5 минут'})
                Panel.attempts.append(time.time())
            password = data.get('password', '')
            if not isinstance(password, str) or len(password) > 512:
                return self.send(400, {'error': 'Некорректный пароль'})
            with db_open(self.server.config) as db:
                account = db.execute('SELECT * FROM credentials WHERE id=1').fetchone()
            if not account or not hmac.compare_digest(account['digest'], password_digest(password, account['salt'])):
                return self.send(401, {'error': 'Неверный пароль'})
            sid = secrets.token_urlsafe(32)
            with self.mutex:
                Panel.sessions[sid] = {'csrf': secrets.token_hex(24), 'expires': time.time() + 3600 * 8}
            return self.send(200, {'ok': True}, cookie='gitdeck=' + sid + '; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800')
        session = self.session()
        if not session or not hmac.compare_digest(str(data.get('csrf', '')), session['csrf']):
            return self.send(403, {'error': 'Сессия истекла. Войдите снова'})
        if self.path == '/api/logout':
            cookie = http.cookies.SimpleCookie(self.headers.get('Cookie', ''))
            with self.mutex:
                Panel.sessions.pop(cookie['gitdeck'].value, None)
            return self.send(200, {'ok': True}, cookie='gitdeck=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict')
        if self.path in ('/api/project/save', '/api/project/remove'):
            try:
                with self.mutex:
                    with db_open(self.server.config) as db:
                        if db.execute("SELECT 1 FROM jobs WHERE status NOT IN ('success','failed')").fetchone():
                            return self.send(409, {'error': 'Настройки доступны после завершения обновления'})
                    projects = list(self.server.config['projects'])
                    if self.path.endswith('/save'):
                        form = data.get('project')
                        if not isinstance(form, dict):
                            raise ValueError('Некорректные настройки модуля')
                        old = next((p for p in projects if p['id'] == data.get('original_id')), None)
                        if data.get('original_id') and not old:
                            raise ValueError('Редактируемый модуль больше не существует')
                        p = project_from_form(form, old, self.server.config)
                        if not old and any(x['id'] == p['id'] for x in projects):
                            raise ValueError('Идентификатор уже занят')
                        if not old:
                            with db_open(self.server.config) as db:
                                if db.execute('SELECT 1 FROM jobs WHERE project=?', (p['id'],)).fetchone():
                                    raise ValueError('Идентификатор занят историей удалённого модуля. Выберите другой')
                        projects = [p if x['id'] == p['id'] else x for x in projects] if old else projects + [p]
                    else:
                        old = next((p for p in projects if p['id'] == data.get('project')), None)
                        if not old or old['kind'] == 'self':
                            raise ValueError('Саму панель нельзя убрать из списка модулей')
                        projects = [p for p in projects if p['id'] != old['id']]
                    save_config(self.server, projects, data.get('config_revision'))
                return self.send(200, {'ok': True})
            except (ValueError, KeyError, TypeError) as exc:
                return self.send(400, {'error': str(exc)})
            except OSError:
                return self.send(500, {'error': 'Не удалось сохранить файл конфигурации на сервере'})
        if self.path == '/api/revisions':
            p = next((x for x in self.server.config['projects'] if x['id'] == data.get('project')), None)
            if not p:
                return self.send(400, {'error': 'Неизвестный модуль'})
            if self.server.demo:
                return self.send(200, {'branches': ['main'], 'commits': []})
            try:
                ref = valid_ref(data.get('branch') or p['branch'])
                # Separate cache keeps UI inspection independent from an active deployment.
                info = revisions(self.server.config, p, ref)
                return self.send(200, info)
            except (ValueError, RuntimeError, subprocess.TimeoutExpired) as exc:
                return self.send(400, {'error': str(exc)})
        if self.path == '/api/environment/save':
            if self.server.demo:
                return self.send(403, {'error': 'Предпросмотр: изменение настроек сайтов отключено'})
            with self.mutex:
                try:
                    p = next((x for x in self.server.config['projects'] if x['id'] == data.get('project')), None)
                    if not p or p['kind'] == 'self':
                        raise ValueError('Выберите сайт для изменения настроек')
                    if data.get('config_revision') != config_revision(self.server.config):
                        raise ValueError('Настройки модуля уже изменились. Откройте форму заново')
                    validate_env_changes(data.get('changes'))
                    if data.get('env_revision') != env_revision(env_text(p)):
                        raise ValueError('Файл .env изменился. Откройте форму заново')
                    payload = {'changes': data['changes'], 'env_revision': data['env_revision']}
                    job = enqueue(self.server, p, 'configure', payload=payload)
                    return self.send(202, {'job': job})
                except (ValueError, OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    return self.send(400, {'error': str(exc)})
        if self.path == '/api/connect-marathon':
            if self.server.demo:
                return self.send(403, {'error': 'В предпросмотре подключение отключено'})
            with self.mutex:
                try:
                    p = next(x for x in self.server.config['projects'] if x['id'] == data.get('project') and x['kind'] == 'pulse')
                    source = next(x for x in self.server.config['projects'] if x['id'] == data.get('marathon') and x['kind'] == 'marathon')
                    url = data.get('pulse_url', '')
                    if not isinstance(url, str) or len(url) > 250 or not re.fullmatch(r'https://[a-z0-9.-]+/?', url):
                        raise ValueError('Укажите HTTPS-адрес Пульса, например https://pulse.vano.sbena.net/')
                    payload = {'marathon':source['id'], 'pulse_url':url, 'pulse_revision':env_revision(env_text(p)), 'marathon_revision':env_revision(env_text(source))}
                    return self.send(202, {'job':enqueue(self.server,p,'connect_marathon',payload=payload)})
                except (ValueError, StopIteration, OSError, RuntimeError) as error:
                    return self.send(400, {'error': str(error) or 'Выберите Пульс и марафон'})
        if self.path == '/api/pulse-bot':
            if self.server.demo:return self.send(403,{'error':'В предпросмотре запуск отключён'})
            with self.mutex:
                try:
                    p=next(x for x in self.server.config['projects'] if x['id']==data.get('project') and x['kind']=='pulse')
                    return self.send(202,{'job':enqueue(self.server,p,'pulse_bot')})
                except (StopIteration,ValueError,OSError,RuntimeError) as error:
                    return self.send(400,{'error':str(error) or 'Выберите Пульс'})
        if self.path == '/api/update':
            if self.server.demo:
                return self.send(403, {'error': 'Предпросмотр: команды на сервере отключены'})
            with self.mutex:
                p = next((p for p in self.server.config['projects'] if p['id'] == data.get('project')), None)
                if not p:
                    return self.send(400, {'error': 'Неизвестный проект'})
                try:
                    target_ref = valid_ref(data.get('ref') or p['branch'])
                    job = enqueue(self.server, p, 'update', target_ref)
                    return self.send(202, {'job': job})
                except ValueError as exc:
                    return self.send(409, {'error': str(exc)})
                except (OSError, RuntimeError, subprocess.TimeoutExpired) as exc:
                    return self.send(500, {'error': str(exc)})
        self.send(404, {'error': 'Не найдено'})


def serve(config, config_path, demo=False):
    db_open(config).close()
    server = http.server.ThreadingHTTPServer(('127.0.0.1', int(config.get('port', 8120))), Panel)
    server.config, server.config_path, server.demo = config, str(Path(config_path).resolve()), demo
    print('GitDeck: http://127.0.0.1:' + str(server.server_port), flush=True)
    server.serve_forever()


def main():
    parser = argparse.ArgumentParser(description='GitDeck · обновления сайтов из Git')
    parser.add_argument('--config', default='/etc/gitdeck/config.json')
    parser.add_argument('command', choices=['serve', 'password', 'worker', 'recover'])
    parser.add_argument('--job')
    parser.add_argument('--demo', action='store_true')
    args = parser.parse_args()
    config = load_config(args.config)
    if args.command == 'serve':
        serve(config, args.config, args.demo)
    elif args.command == 'password':
        set_password(config)
    elif args.command == 'worker':
        if not args.job or not re.fullmatch('[a-f0-9]{24}', args.job):
            parser.error('Некорректное задание')
        work(config, args.job)
    elif args.command == 'recover':
        # Explicit operator recovery after reboot/process crash, without claiming a rollback.
        import fcntl
        with (Path(config['state_dir']) / 'worker.lock').open('a') as lock:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            with db_open(config) as db:
                db.execute("UPDATE jobs SET status='failed',error='Прервано. Проверьте сервисы и резервную копию перед повтором',updated=? WHERE status NOT IN ('success','failed')", (time.time(),))
        print('Прерванные задания закрыты. Резервные копии сохранены.')


if __name__ == '__main__':
    main()
