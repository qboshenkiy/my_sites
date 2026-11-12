"""One-time, reviewed infrastructure upgrade; source deployment stays in the GitDeck queue."""
import argparse
import fcntl
import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
from types import SimpleNamespace

CONFIG = Path('/etc/gitdeck/config.json')
TARGET = Path('/opt/suilo')
MARKER = '# Suilo Telegram accounts v1\n'


def overlay_text(source):
    return MARKER + (source / 'ops/compose.telegram.yaml').read_text()


def prepare(panel, source, branch=None):
    config = panel.load_config(CONFIG)
    previous = next((p for p in config['projects'] if p['id'] == 'suilo'), None)
    if not previous or previous.get('kind') != 'docker' or previous.get('directory') != str(TARGET) or previous.get('subdir') != 'suilo' or previous.get('repo') != 'https://github.com/qboshenkiy/my_sites.git':
        raise ValueError('Ожидается существующая карточка Сүйлө в /opt/suilo.')
    if TARGET.is_symlink() or (TARGET / 'ops').is_symlink() or not (TARGET / 'compose.yaml').is_file():
        raise ValueError('Некорректный каталог установленного модуля.')
    with panel.db_open(config) as db:
        if db.execute("SELECT 1 FROM jobs WHERE status NOT IN ('success','failed') LIMIT 1").fetchone():
            raise ValueError('Дождитесь завершения задания GitDeck.')
    for unit in ('guard-request-gate.service', 'guard-firewall.service'):
        subprocess.run(['systemctl', 'is-active', '--quiet', unit], check=True)
    proxies = [p for p in config['projects'] if p['kind'] in ('marathon', 'pulse') and p['compose'] == 'compose.https.yaml']
    guarded = False
    for proxy in proxies:
        caddy = Path(proxy['directory']) / 'deploy/Caddyfile'
        if caddy.is_file() and 'suilo.vano.sbena.net' in caddy.read_text() and 'import /data/guard-sensitive.caddy' in caddy.read_text():
            panel.compose(proxy, ['exec', '-T', 'proxy', 'sh', '-ec', 'test -S /data/guard-request.sock && grep -q "forward_auth unix//data/guard-request.sock" /data/guard-sensitive.caddy'], None)
            guarded = True
            break
    if not guarded:
        raise ValueError('Не подтверждён существующий маршрут Сүйлө через Guard.')
    overlay = TARGET / 'compose.gitdeck-telegram.yaml'
    if overlay.is_symlink() or (overlay.exists() and not overlay.read_text().startswith(MARKER)):
        raise ValueError('Найден другой Telegram overlay. Нужна ручная сверка, файл не заменён.')
    project = dict(previous, services=list(dict.fromkeys([*previous['services'], 'api'])))
    if branch:
        project['branch'] = panel.valid_ref(branch)
    project = panel.project_from_form(project, previous, config)
    revision = panel.config_revision(config)
    # Back up infrastructure locally; never touch .env, Caddy, or existing database volumes.
    backup = TARGET / '.telegram-infrastructure-before.json'
    files = [overlay, *(TARGET / 'ops' / name for name in ('server.py', 'Dockerfile.telegram', 'compose.telegram.yaml'))]
    old = {}
    for file in files:
        if file.is_symlink():
            raise ValueError('Символическая ссылка в инфраструктуре.')
        old[str(file.relative_to(TARGET))] = file.read_text() if file.exists() else None
    if not backup.exists():
        backup.write_text(json.dumps(old, ensure_ascii=False, indent=2)); backup.chmod(0o600)
    try:
        for name in ('server.py', 'Dockerfile.telegram', 'compose.telegram.yaml'):
            shutil.copy2(source / 'ops' / name, TARGET / 'ops' / name)
        overlay.write_text(overlay_text(source))
        panel.compose(project, ['config', '--quiet'], None)
        server = SimpleNamespace(config=config, config_path=CONFIG)
        panel.save_config(server, [project if p['id'] == 'suilo' else p for p in config['projects']], revision)
    except Exception:
        for name, content in old.items():
            file = TARGET / name
            if content is None:
                file.unlink(missing_ok=True)
            else:
                file.write_text(content)
        raise
    return project


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--branch', help='Ветка проверенного выпуска в GitHub; по умолчанию текущая ветка карточки')
    args = parser.parse_args()
    if os.geteuid() != 0:
        raise SystemExit('Запустите через sudo python3 suilo/ops/enable_telegram.py.')
    os.umask(0o077)
    spec = importlib.util.spec_from_file_location('gitdeck', '/opt/gitdeck/app.py')
    panel = importlib.util.module_from_spec(spec); spec.loader.exec_module(panel)
    config = panel.load_config(CONFIG)
    with (Path(config['state_dir']) / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        project = prepare(panel, Path(__file__).resolve().parents[1], args.branch)
    subprocess.run(['systemctl', 'restart', 'gitdeck'], check=True)
    config = panel.load_config(CONFIG)
    server = SimpleNamespace(config=config, config_path=str(CONFIG))
    job = panel.enqueue(server, project, 'update', project['branch'])
    print('Инфраструктура подготовлена. Обновление в очереди GitDeck:', job)
    print('Проверьте успех задания в GitDeck, затем откройте приложение из бота.')


if __name__ == '__main__':
    main()
