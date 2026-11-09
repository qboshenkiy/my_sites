"""Initial setup on the GitDeck host. Run the reviewed checkout as root."""
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
from types import SimpleNamespace

HOST = 'suilo.vano.sbena.net'
REPO = 'https://github.com/qboshenkiy/my_sites.git'
TARGET = Path('/opt/suilo')
CONFIG = Path('/etc/gitdeck/config.json')
PATHS = ['src', 'public', 'ops', 'index.html', 'package.json', 'package-lock.json', 'tsconfig.json', 'vite.config.ts']
PROJECT = {
    'id': 'suilo', 'name': 'Сүйлө · кыргызский язык', 'kind': 'docker',
    'repo': REPO, 'branch': 'suilo', 'subdir': 'suilo', 'directory': str(TARGET),
    'compose': 'compose.yaml', 'services': ['web', 'bot'], 'main_service': 'web',
    'profiles': [], 'paths': PATHS, 'wait_health': True,
}
BEGIN, END = '# Suilo HTTPS BEGIN', '# Suilo HTTPS END'
GUARD = '/data/guard-sensitive.caddy'


def route(source):
    if not re.search(r'^\s*import /data/guard-sensitive\.caddy\s*(?:#.*)?$', source, re.M):
        raise ValueError('В общем Caddy не найден действующий импорт Guard.')
    if BEGIN in source or END in source:
        matches = list(re.finditer(r'^' + BEGIN + r'\n.*?^' + END + r'\n?', source, re.M | re.S))
        if len(matches) != 1 or source.count(BEGIN) != 1 or source.count(END) != 1:
            raise ValueError('Неоднозначный блок маршрута «Сүйлө».')
        match = matches[0]
        source = source[:match.start()] + source[match.end():]
    if re.search(r'(?im)^\s*[^#\n]*\b' + re.escape(HOST) + r'(?=[\s,:{]|$)', source):
        raise ValueError('Домен «Сүйлө» уже используется в другом маршруте.')
    if re.search(r'(?m)^\s*reverse_proxy\s+(?:http://)?web:80(?:\s|$)', source):
        raise ValueError('Сначала задайте стабильный Docker alias основному сайту (сейчас web:80).')
    return source.rstrip() + f'''

{BEGIN}
{HOST} {{
    import {GUARD} # Guard sensitive files
    log {{
        output stdout
        format json
    }}
    encode gzip zstd
    reverse_proxy suilo-web:8080
}}
{END}
'''


def run(*args, **kwargs):
    return subprocess.run(args, check=True, text=True, **kwargs)


def copy_initial(source):
    if TARGET.is_symlink() or (TARGET.exists() and not TARGET.is_dir()):
        raise ValueError('Некорректный /opt/suilo.')
    TARGET.mkdir(exist_ok=True)
    if any(TARGET.iterdir()) and not (TARGET / '.suilo-managed').is_file():
        raise ValueError('/opt/suilo уже занят. Выберите отдельный каталог.')
    (TARGET / '.suilo-managed').touch(mode=0o600)
    for name in [*PATHS, 'compose.yaml', 'Dockerfile', '.dockerignore']:
        src, dst = source / name, TARGET / name
        if dst.is_symlink():
            raise ValueError(f'Символическая ссылка недопустима: {dst}')
        if dst.exists():
            continue
        if src.is_dir():
            shutil.copytree(src, dst)
        else:
            shutil.copy2(src, dst)
    env = TARGET / '.env'
    if env.is_symlink():
        raise ValueError('Файл .env является символической ссылкой.')
    if not env.exists():
        with env.open('x') as stream:
            os.fchmod(stream.fileno(), 0o600)
            stream.write((source / '.env.example').read_text())


def main():
    if os.geteuid() != 0:
        raise SystemExit('Запустите через sudo python3 suilo/ops/install.py.')
    os.umask(0o077)
    with open('/run/lock/suilo-install.lock', 'w') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        install(Path(__file__).resolve().parents[1])


def install(source):
    spec = importlib.util.spec_from_file_location('gitdeck', '/opt/gitdeck/app.py')
    panel = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(panel)
    config = panel.load_config(CONFIG)
    project = panel.project_from_form(PROJECT, None, config)
    prior = next((p for p in config['projects'] if p['id'] == 'suilo'), None)
    if prior and any(prior.get(k) != project[k] for k in ('repo', 'kind', 'subdir', 'directory', 'compose')):
        raise ValueError('В GitDeck уже зарегистрирован другой проект suilo.')
    panel.validate_config(dict(config, projects=config['projects'] if prior else [*config['projects'], project]))
    revision = panel.config_revision(config)

    options = [p for p in config['projects'] if p['kind'] in ('marathon', 'pulse') and p['compose'] == 'compose.https.yaml']
    proxy = next((p for p in options if p['kind'] == 'marathon'), options[0] if options else None)
    if not proxy:
        raise ValueError('Не найден общий HTTPS-прокси GitDeck.')
    details = json.loads(panel.compose(proxy, ['config', '--format', 'json'], None))
    network = details.get('networks', {}).get('default', {}).get('name', '')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', network):
        raise ValueError('Не найдена сеть Caddy.')
    caddyfile = Path(proxy['directory']) / 'deploy/Caddyfile'
    overlay = TARGET / 'compose.gitdeck-https.yaml'
    if caddyfile.is_symlink() or overlay.is_symlink() or not caddyfile.is_file():
        raise ValueError('Проверьте путь к Caddyfile и Compose overlay.')
    original = caddyfile.read_text()
    updated = route(original)
    panel.compose(proxy, ['exec','-T','proxy','sh','-ec',
        f'test -S /data/guard-request.sock && grep -q "forward_auth unix//data/guard-request.sock" {GUARD}'], None)

    for service in ('guard-request-gate.service', 'guard-firewall.service'):
        run('systemctl', 'is-active', '--quiet', service)
    copy_initial(source)
    old_overlay = overlay.read_bytes() if overlay.exists() else None
    overlay.write_text(json.dumps({
        'services': {'web': {'networks': {'default': {}, 'gitdeck_https': {'aliases': ['suilo-web']}}}},
        'networks': {'gitdeck_https': {'external': True, 'name': network}},
    }))
    edited = False
    registered = False
    try:
        run('docker','compose','-f','compose.yaml','-f',overlay.name,'up','-d','--build','--wait','--wait-timeout','90',cwd=TARGET)
        if caddyfile.read_text() != original:
            raise ValueError('Caddyfile изменился во время сборки. Повторите установку.')
        if not prior:
            with panel.db_open(config) as db:
                active = db.execute("SELECT 1 FROM jobs WHERE status NOT IN ('success','failed') LIMIT 1").fetchone()
                if active:
                    raise ValueError('Дождитесь завершения активных задач GitDeck.')
        edited = True
        caddyfile.write_text(updated)
        for operation in ('validate', 'reload'):
            panel.compose(proxy, ['exec','-T','proxy','caddy',operation,'--config','/etc/caddy/Caddyfile','--adapter','caddyfile'], None)
        if not prior:
            latest = panel.load_config(CONFIG)
            server = SimpleNamespace(config=latest, config_path=CONFIG)
            panel.save_config(server, [*latest['projects'], project], revision)
            registered = True
            run('systemctl','restart','gitdeck')
    except Exception:
        if registered:
            latest = panel.load_config(CONFIG)
            server = SimpleNamespace(config=latest, config_path=CONFIG)
            panel.save_config(server, [p for p in latest['projects'] if p['id'] != 'suilo'], panel.config_revision(latest))
            subprocess.run(['systemctl','restart','gitdeck'], check=False)
        if edited:
            caddyfile.write_text(original)
            panel.compose(proxy, ['exec','-T','proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'], None)
        if old_overlay is None:
            subprocess.run(['docker','compose','-f','compose.yaml','-f',overlay.name,'down'], cwd=TARGET, check=False)
            overlay.unlink(missing_ok=True)
        else:
            overlay.write_bytes(old_overlay)
        raise
    print(f'Маршрут с Guard подключён: https://{HOST}/')


if __name__ == '__main__':
    main()
