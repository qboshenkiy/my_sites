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

VERSION = '1.0.0'
LAYOUT = {
    'pulse': ['index.php', 'api.php', 'seed.php', '.htaccess', 'assets', 'tools/check.php', 'tools/backup.php'],
    'marathon': ['index.php', 'api.php', '.htaccess', 'assets', 'lib', 'tools/bot.php', 'tools/backup.php'],
    'self': ['app.py', 'index.html', 'VERSION', 'README.md', 'install.sh', 'config.example.json', '.gitignore'],
}
REQUIRED = {'pulse': ['index.php', 'api.php', 'assets/app.js'],
            'marathon': ['index.php', 'api.php', 'lib/core.php', 'lib/telegram.php'],
            'self': ['app.py', 'index.html', 'VERSION']}


def validate_project(p):
    if not re.fullmatch(r'[a-z][a-z0-9-]{0,39}', p['id']) or p['kind'] not in LAYOUT:
        raise ValueError('Некорректный id или тип проекта')
    repo = p['repo']
    url = urllib.parse.urlsplit(repo)
    https = url.scheme == 'https' and url.hostname and not url.username and not url.password and not url.query and not url.fragment
    ssh = re.fullmatch(r'git@[a-zA-Z0-9.-]+:[a-zA-Z0-9_./-]+\.git', repo)
    if not (https or ssh) or any(c.isspace() for c in repo):
        raise ValueError('Используйте HTTPS без токена в URL или git@host:owner/repo.git')
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_./-]{0,150}', p['branch']) or '..' in p['branch']:
        raise ValueError('Некорректная ветка')
    sub = p.get('subdir', '')
    if sub and (not re.fullmatch(r'[A-Za-z0-9_./-]+', sub) or any(s in ('', '.', '..') for s in sub.split('/'))):
        raise ValueError('Некорректный путь в репозитории')
    dest = Path(p['directory'])
    if not dest.is_absolute() or len(dest.parts) < 3 or dest.is_symlink():
        raise ValueError('Укажите отдельный абсолютный каталог приложения')
    if p['kind'] != 'self':
        if p['compose'] not in ('compose.yaml', 'compose.https.yaml', 'compose.shared.yaml'):
            raise ValueError('Неизвестный compose-файл')
        if p.get('services') not in (['web'], ['web', 'bot']):
            raise ValueError('Разрешены сервисы web и bot')
        if p.get('profiles', []) not in ([], ['telegram']):
            raise ValueError('Неизвестный профиль')
    return p


def load_config(path):
    config = json.loads(Path(path).read_text(encoding='utf-8-sig'))
    ids = set()
    directories = set()
    for p in config['projects']:
        validate_project(p)
        d = str(Path(p['directory']).resolve())
        if p['id'] in ids or d in directories:
            raise ValueError('Проекты должны иметь разные id и каталоги')
        ids.add(p['id'])
        directories.add(d)
    return config


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
    for profile in p.get('profiles', []):
        command += ['--profile', profile]
    return run(command + args, log, cwd=p['directory'])


def allowed(name, kind):
    return any(name == entry or name.startswith(entry + '/') for entry in LAYOUT[kind])


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
    for name in REQUIRED[kind]:
        if not (target / name).is_file():
            raise ValueError('В репозитории отсутствует обязательный файл: ' + name)


def checkout(p, config, folder, log):
    cache = Path(config['state_dir']) / 'repos' / p['id']
    cache.parent.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ, GIT_TERMINAL_PROMPT='0')
    if p.get('ssh_key'):
        key = Path(p['ssh_key'])
        if not key.is_file():
            raise ValueError('Не найден SSH-ключ для репозитория')
        env['GIT_SSH_COMMAND'] = 'ssh -o BatchMode=yes -o StrictHostKeyChecking=yes -o IdentitiesOnly=yes -i ' + shlex.quote(str(key))
    if not cache.exists():
        run(['git', 'init', '--bare', str(cache)], log, env=env)
    run(['git', '--git-dir', str(cache), 'fetch', '--no-tags', '--force', '--', p['repo'],
         '+refs/heads/' + p['branch'] + ':refs/heads/deploy'], log, env=env)
    sha = run(['git', '--git-dir', str(cache), 'rev-parse', 'refs/heads/deploy'], env=env).decode().strip()
    if not re.fullmatch('[a-f0-9]{40,64}', sha):
        raise ValueError('Git вернул некорректный commit')
    ref = sha + (':' + p.get('subdir', '') if p.get('subdir') else '')
    archive = run(['git', '--git-dir', str(cache), 'archive', '--format=tar', ref], env=env)
    extract_source(archive, folder, p['kind'])
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
    for name in LAYOUT[kind]:
        validate_destination(dest, name)
        src = validate_destination(source, name)
        out = dest / name
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
    tool = '/opt/pulse/backup.php' if p['kind'] == 'pulse' else '/opt/marathon/backup.php'
    compose(p, ['run', '--rm', '--no-deps', '--user', 'root', '-v', str(jobdir) + ':/gitdeck-backup',
                '--entrypoint', 'php', 'web', tool, '/gitdeck-backup/data.sqlite'], log)
    if not (jobdir / 'data.sqlite').is_file():
        raise RuntimeError('Не создана резервная копия базы')


def database_restore(p, jobdir, log):
    # SQLite backup is taken with web/bot stopped. Restore DB and remove matching WAL files.
    location = '/var/lib/pulse/quiz.sqlite' if p['kind'] == 'pulse' else '/var/lib/marathon/marathon.sqlite'
    php = '$p=$argv[1]; if(!copy("/gitdeck-backup/data.sqlite",$p))exit(1); foreach(["-wal","-shm"] as $s)if(is_file($p.$s))unlink($p.$s); chown($p,"www-data"); chmod($p,0660);'
    compose(p, ['run', '--rm', '--no-deps', '--user', 'root', '-v', str(jobdir) + ':/gitdeck-backup:ro',
                '--entrypoint', 'php', 'web', '-r', php, location], log)


def deploy(config, p, job, log):
    jobdir = Path(config['state_dir']) / 'jobs' / job
    source = jobdir / 'new'
    old = jobdir / 'previous'
    dest = Path(p['directory'])
    sha = checkout(p, config, source, log)
    status_update(config, job, 'preparing', sha=sha)
    if p['kind'] == 'self':
        run([sys.executable, '-m', 'py_compile', str(source / 'app.py')], log)
        # The config is outside code; the independent job runs a frozen copy of this worker.
        if dest.resolve() != Path(__file__).resolve().parent and not (dest / 'app.py').is_file():
            raise ValueError('Каталог панели не содержит установленного app.py')
    else:
        if not (dest / p['compose']).is_file():
            raise ValueError('Не найден compose-файл установленного сайта')
        compose(p, ['config', '--quiet'], log)
    copy_code(dest, old, p['kind'], save=True)
    # Remember actual previous commit independently of candidate or failed deployments.
    with db_open(config) as db:
        prev = db.execute('SELECT commit_sha FROM versions WHERE project=?', (p['id'],)).fetchone()
    (jobdir / 'previous-version.json').write_text(json.dumps({'sha': prev[0] if prev else ''}))
    stopped = False
    mutated = False
    try:
        if p['kind'] != 'self':
            status_update(config, job, 'backup', sha=sha)
            stopped = True  # A partially failed stop must also be recovered.
            compose(p, ['stop'] + p['services'], log)
            database_backup(p, jobdir, log)
        mutated = True
        copy_code(source, dest, p['kind'])
        status_update(config, job, 'installing', sha=sha)
        if p['kind'] != 'self':
            compose(p, ['up', '-d', '--build', '--wait', '--wait-timeout', '180'] + p['services'], log)
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
                compose(p, ['stop'] + p['services'], log)
            copy_code(old, dest, p['kind'])
            if p['kind'] != 'self':
                database_restore(p, jobdir, log)
                compose(p, ['up', '-d', '--build', '--wait', '--wait-timeout', '180'] + p['services'], log)
            else:
                run(['systemctl', 'restart', 'gitdeck'], log, timeout=60)
            with db_open(config) as db:
                if prev:
                    db.execute('INSERT OR REPLACE INTO versions VALUES (?, ?, ?)', (p['id'], prev[0], time.time()))
                else:
                    db.execute('DELETE FROM versions WHERE project=?', (p['id'],))
            log.write('\nПредыдущий код и база восстановлены.\n')
        elif stopped:
            compose(p, ['up', '-d', '--wait'] + p['services'], log)
        raise


def work(config, job):
    import fcntl
    with (Path(config['state_dir']) / 'worker.lock').open('a') as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        with db_open(config) as db:
            row = db.execute('SELECT * FROM jobs WHERE id=?', (job,)).fetchone()
        if not row or row['status'] != 'queued':
            raise ValueError('Задание не ожидает выполнения')
        p = next(x for x in config['projects'] if x['id'] == row['project'])
        jobdir = Path(config['state_dir']) / 'jobs' / job
        with (jobdir / 'output.log').open('a', encoding='utf-8') as log:
            try:
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
            projects = [{k: p.get(k, '') for k in ('id', 'name', 'kind', 'repo', 'branch', 'subdir', 'directory')}
                        for p in self.server.config['projects']]
            return self.send(200, {'projects': projects, 'jobs': jobs, 'versions': versions,
                                   'csrf': session['csrf'], 'version': VERSION, 'demo': self.server.demo})
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
        self.send(404, {'error': 'Не найдено'})

    def do_POST(self):
        if not self.valid_host() or self.headers.get('Origin') != 'http://' + self.headers.get('Host', ''):
            return self.send(403, {'error': 'Недопустимый источник запроса'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 4096:
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
        if self.path == '/api/update':
            if self.server.demo:
                return self.send(403, {'error': 'Предпросмотр: команды на сервере отключены'})
            p = next((p for p in self.server.config['projects'] if p['id'] == data.get('project')), None)
            if not p:
                return self.send(400, {'error': 'Неизвестный проект'})
            job = secrets.token_hex(12)
            with db_open(self.server.config) as db:
                db.execute('BEGIN IMMEDIATE')
                if db.execute("SELECT 1 FROM jobs WHERE status NOT IN ('success','failed')").fetchone():
                    return self.send(409, {'error': 'Дождитесь завершения текущего обновления'})
                db.execute('INSERT INTO jobs (id,project,action,status,created,updated) VALUES (?,?,?,?,?,?)',
                           (job, p['id'], 'update', 'queued', time.time(), time.time()))
            folder = Path(self.server.config['state_dir']) / 'jobs' / job
            try:
                folder.mkdir(parents=True, mode=0o700)
                snapshot = folder / 'worker.py'
                shutil.copy2(__file__, snapshot)
                run(['systemd-run', '--quiet', '--collect', '--unit=gitdeck-job-' + job,
                     '--property=Type=exec', sys.executable, str(snapshot), '--config', self.server.config_path,
                     'worker', '--job', job], timeout=20)
            except Exception as exc:
                status_update(self.server.config, job, 'failed', str(exc))
                return self.send(500, {'error': str(exc)})
            return self.send(202, {'job': job})
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
