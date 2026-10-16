"""Real PostgreSQL smoke test, using only disposable application/database copies."""
import http.cookiejar
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PHP = os.environ.get('PHP_BIN', 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe' if os.name == 'nt' else 'php')
PG = Path(os.environ.get('PG_BIN', 'C:/laragon/bin/postgresql/postgresql/bin' if os.name == 'nt' else '/usr/bin'))


def port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def run(args, **kw):
    result = subprocess.run([str(v) for v in args], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=90, **kw)
    if result.returncode:
        raise RuntimeError(result.stdout + result.stderr)
    return result.stdout


with tempfile.TemporaryDirectory(prefix='chrono-deploy-test-') as tmp:
    tmp = Path(tmp)
    site, cluster = tmp / 'site', tmp / 'pg'
    site.mkdir()
    for name in ('app', 'vendor', 'public'):
        shutil.copytree(ROOT / name, site / name, ignore=shutil.ignore_patterns('uploads', '*.log'))
    shutil.copy2(ROOT / 'spark', site / 'spark')
    for name in ('cache', 'logs', 'session', 'uploads', 'debugbar'):
        (site / 'writable' / name).mkdir(parents=True, exist_ok=True)
    db_port, web_port = port(), port()
    env = dict(os.environ, CI_ENVIRONMENT='production', ADMIN_USERNAME='deployadmin', ADMIN_PASSWORD='test-password-for-deployment',
               PGHOST='127.0.0.1', PGPORT=str(db_port), PGUSER='postgres',
               DB_HOST='127.0.0.1', DB_PORT=str(db_port), DB_DATABASE='chrono_test', DB_USERNAME='postgres', DB_PASSWORD='')
    env.update({'app_baseURL': f'http://127.0.0.1:{web_port}/', 'app_indexPage': '',
                'database_default_hostname': '127.0.0.1', 'database_default_port': str(db_port),
                'database_default_username': 'postgres', 'database_default_password': '',
                'database_default_database': 'chrono_test', 'database_default_DBDriver': 'Postgre',
                'database_default_charset': 'utf8', 'database_default_DBDebug': 'false'})
    run([PG / 'initdb', '-D', cluster, '-A', 'trust', '-U', 'postgres', '--no-locale', '-E', 'UTF8'])
    # On Windows, background PostgreSQL can retain a pipe handle inherited from
    # pg_ctl. Redirect to a file instead of waiting for capture_output EOF.
    with (tmp / 'pg_ctl.log').open('w') as pg_log:
        subprocess.run([str(PG / 'pg_ctl'), '-D', str(cluster), '-l', str(tmp / 'postgres.log'),
                        '-o', f'-h 127.0.0.1 -p {db_port}', '-w', 'start'],
                       stdout=pg_log, stderr=pg_log, check=True, timeout=30)
    server = None
    try:
        run([PG / 'createdb', 'chrono_test'], env=env)
        output = run([PHP, 'spark', 'migrate', '--all'], cwd=site, env=env)
        assert 'done' in output.lower() or 'complete' in output.lower(), output
        print('PASS: fresh PostgreSQL migrations')
        run([PHP, 'spark', 'migrate', '--all'], cwd=site, env=env)
        for _ in range(2):
            run([PHP, 'spark', 'deploy:admin'], cwd=site, env=env)
        users = run([PG / 'psql', '-d', 'chrono_test', '-Atc', "SELECT username || ':' || r.code FROM users u JOIN roles r ON r.id=u.role_id"], env=env).strip()
        assert users == 'deployadmin:ADMIN', users
        print('PASS: repeated migrations and idempotent administrator provisioning')
        # Simulate an existing database receiving the new earlier migration.
        run([PG / 'psql', '-d', 'chrono_test', '-Atc', "DELETE FROM migrations WHERE class LIKE '%BootstrapRooms'"], env=env)
        run([PHP, 'spark', 'migrate', '--all'], cwd=site, env=env)
        assert run([PG / 'psql', '-d', 'chrono_test', '-Atc', 'SELECT count(*) FROM users'], env=env).strip() == '1'
        dump = tmp / 'database.dump'
        run([PG / 'pg_dump', '-d', 'chrono_test', '-Fc', '-f', dump], env=env)
        run([PG / 'psql', '-d', 'chrono_test', '-Atc', "CREATE TABLE failed_migration (id int); DELETE FROM users;"], env=env)
        run([PG / 'pg_restore', '-d', 'postgres', '--create', '--clean', '--if-exists', '--no-owner', '--exit-on-error', dump], env=env)
        assert run([PG / 'psql', '-d', 'chrono_test', '-Atc', "SELECT count(*) FROM users; SELECT to_regclass('public.failed_migration') IS NULL;"], env=env).strip().splitlines() == ['1', 't']
        print('PASS: existing schema upgrade and full PostgreSQL backup/restore')
        router = site / 'router.php'
        router.write_text("<?php $p=__DIR__.'/public'.parse_url($_SERVER['REQUEST_URI'],PHP_URL_PATH); if(is_file($p))return false; require __DIR__.'/public/index.php';", encoding='utf-8')
        with (tmp / 'http.log').open('w') as logfile:
            server = subprocess.Popen([PHP, '-S', f'127.0.0.1:{web_port}', '-t', str(site / 'public'), str(router)], cwd=site, env=env,
                                      stdin=subprocess.DEVNULL, stdout=logfile, stderr=logfile)
            base = f'http://127.0.0.1:{web_port}'
            client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
            for _ in range(40):
                try:
                    with client.open(base + '/games', timeout=2) as response:
                        assert response.status == 200
                        break
                except OSError:
                    if server.poll() is not None:
                        raise RuntimeError('Test HTTP process exited')
                    time.sleep(.15)
            else:
                raise RuntimeError('Test HTTP server did not respond')
            html = client.open(base + '/auth/login-page').read().decode()
            assert json.loads(client.open(base + '/_health.php').read()) == {'status': 'ok'}
            token = re.search(r'<input[^>]*name="(csrf_[^"]+)"[^>]*value="([^"]+)"', html)
            assert token, 'CSRF input missing from login page'
            fields = {'login': env['ADMIN_USERNAME'], 'password': env['ADMIN_PASSWORD'], token[1]: token[2]}
            data = json.loads(client.open(base + '/auth/login-page', data=urllib.parse.urlencode(fields).encode()).read())
            assert data.get('success'), data
            assert client.open(base + '/admin/users').status == 200
            print('PASS: catalogue, CSRF-protected login and administrator page')
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)
        run([PG / 'pg_ctl', '-D', cluster, '-m', 'immediate', '-w', 'stop'])
