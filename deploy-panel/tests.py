"""No real Docker, systemd, remote Git, user databases or credentials are used."""
import contextlib
import http.cookiejar
import http.server
import io
import json
from pathlib import Path
import sqlite3
import subprocess
import tarfile
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import app


class GitDeckTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.dest = self.root / 'installed'
        self.dest.mkdir()
        self.source = self.root / 'git-source'
        self.source.mkdir()
        for name, value in {'api.php': 'new api', 'index.php': 'new index', 'seed.php': 'new seed',
                            'assets/app.js': 'new js', 'assets/new.css': 'new css',
                            '.env': 'PRIVATE_REPO_ENV_MUST_NOT_DEPLOY', 'compose.yaml': 'NOT_DEPLOYED'}.items():
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(value)
        for args in [['init', '-b', 'main'], ['add', '.'],
                     ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'test']]:
            subprocess.run(['git'] + args, cwd=self.source, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        self.sha = subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=self.source).decode().strip()
        (self.dest / 'api.php').write_text('old api')
        (self.dest / 'index.php').write_text('old index')
        (self.dest / '.env').write_text('real server secret')
        (self.dest / 'compose.yaml').write_text('real configuration')
        (self.dest / 'Dockerfile').write_text('real dockerfile')
        (self.dest / 'assets').mkdir()
        (self.dest / 'assets/obsolete.js').write_text('old js')
        self.project = {'id': 'pulse', 'name': 'Pulse', 'kind': 'pulse', 'repo': str(self.source),
                        'branch': 'main', 'directory': str(self.dest), 'compose': 'compose.yaml',
                        'profiles': [], 'services': ['web']}
        self.config = {'state_dir': str(self.root / 'state'), 'projects': [self.project]}
        app.db_open(self.config).close()
        self.job = 'a' * 24
        folder = self.root / 'state/jobs' / self.job
        folder.mkdir(parents=True)
        with app.db_open(self.config) as db:
            db.execute('INSERT INTO jobs (id,project,status,created,updated) VALUES (?,?,?,?,?)',
                       (self.job, 'pulse', 'queued', time.time(), time.time()))

    def test_real_git_deploy_keeps_settings_and_deletes_obsolete_assets(self):
        calls = []
        def docker(p, args, log):
            calls.append(args)
            if args[0] == 'run':
                file = self.root / 'state/jobs' / self.job / 'data.sqlite'
                with contextlib.closing(sqlite3.connect(file)) as db:
                    db.execute('CREATE TABLE previous_data (value TEXT)')
                    db.commit()
            return b''
        with patch.object(app, 'compose', side_effect=docker):
            app.deploy(self.config, self.project, self.job, io.StringIO())
        self.assertEqual((self.dest / 'api.php').read_text(), 'new api')
        self.assertEqual((self.dest / '.env').read_text(), 'real server secret')
        self.assertEqual((self.dest / 'compose.yaml').read_text(), 'real configuration')
        self.assertEqual((self.dest / 'Dockerfile').read_text(), 'real dockerfile')
        self.assertFalse((self.dest / 'assets/obsolete.js').exists())
        self.assertTrue((self.dest / 'assets/new.css').exists())
        with app.db_open(self.config) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'success')
            self.assertEqual(db.execute('SELECT commit_sha FROM versions').fetchone()[0], self.sha)
        self.assertLess(next(i for i, c in enumerate(calls) if c[0] == 'stop'), next(i for i, c in enumerate(calls) if c[0] == 'run'))

    def test_failed_build_restores_code_and_database(self):
        calls = []
        def docker(p, args, log):
            calls.append(args)
            if args[0] == 'run' and '/gitdeck-backup/data.sqlite' in args:
                (self.root / 'state/jobs' / self.job / 'data.sqlite').write_bytes(b'original database')
            if args[0] == 'up' and sum(c[0] == 'up' for c in calls) == 1:
                raise RuntimeError('Build failed')
            return b''
        with patch.object(app, 'compose', side_effect=docker):
            with self.assertRaisesRegex(RuntimeError, 'Build failed'):
                app.deploy(self.config, self.project, self.job, io.StringIO())
        self.assertEqual((self.dest / 'api.php').read_text(), 'old api')
        self.assertTrue((self.dest / 'assets/obsolete.js').exists())
        self.assertFalse((self.dest / 'assets/new.css').exists())
        self.assertEqual((self.dest / '.env').read_text(), 'real server secret')
        self.assertTrue(any('php' in c and '-r' in c for c in calls), 'Database restore must run')
        self.assertEqual(sum(c[0] == 'up' for c in calls), 2)
        with app.db_open(self.config) as db:
            self.assertIsNone(db.execute('SELECT * FROM versions').fetchone())

    def test_backup_failure_never_replaces_code_and_restarts_services(self):
        calls = []
        def docker(p, args, log):
            calls.append(args)
            if args[0] == 'run':
                raise RuntimeError('Disk full')
        with patch.object(app, 'compose', side_effect=docker):
            with self.assertRaisesRegex(RuntimeError, 'Disk full'):
                app.deploy(self.config, self.project, self.job, io.StringIO())
        self.assertEqual((self.dest / 'api.php').read_text(), 'old api')
        self.assertTrue(any(c[0] == 'up' for c in calls))

    def test_archive_traversal_and_symlink_rejected(self):
        for name, kind in [('../api.php', tarfile.REGTYPE), ('assets/secret', tarfile.SYMTYPE)]:
            data = io.BytesIO()
            with tarfile.open(fileobj=data, mode='w') as archive:
                item = tarfile.TarInfo(name)
                item.type = kind
                item.linkname = '/etc/passwd' if kind == tarfile.SYMTYPE else ''
                archive.addfile(item)
            with self.assertRaises(ValueError):
                app.extract_source(data.getvalue(), self.root / 'extract', 'pulse')

    def test_config_rejects_credentials_and_shell_text(self):
        good = dict(self.project, repo='git@github.com:user/repository.git')
        app.validate_project(good)
        for field, value in [('repo', 'https://secret@github.com/u/r.git'), ('branch', 'main;reboot'),
                             ('subdir', '../outside'), ('compose', '/etc/passwd'), ('services', ['proxy'])]:
            with self.assertRaises(ValueError):
                app.validate_project(dict(good, **{field: value}))

    def test_self_update_failure_restores_previous_panel(self):
        p = dict(self.project, kind='self')
        (self.dest / 'app.py').write_text('old panel')
        (self.dest / 'index.html').write_text('old interface')
        def checkout(p, config, folder, log):
            folder.mkdir()
            (folder / 'app.py').write_text('print("new panel")')
            (folder / 'index.html').write_text('new interface')
            (folder / 'VERSION').write_text('2.0.0')
            return self.sha
        restarts = []
        def command(args, *a, **kw):
            if args[:2] == ['systemctl', 'restart']:
                restarts.append(args)
                if len(restarts) == 1:
                    raise RuntimeError('Restart failed')
            return b''
        with patch.object(app, 'checkout', side_effect=checkout), patch.object(app, 'run', side_effect=command):
            with self.assertRaisesRegex(RuntimeError, 'Restart failed'):
                app.deploy(self.config, p, self.job, io.StringIO())
        self.assertEqual((self.dest / 'app.py').read_text(), 'old panel')
        self.assertEqual((self.dest / 'index.html').read_text(), 'old interface')
        self.assertEqual(len(restarts), 2)

    def test_http_auth_csrf_demo_and_host_protection(self):
        salt = 'a' * 32
        with app.db_open(self.config) as db:
            db.execute('INSERT INTO credentials VALUES(1,?,?)', (salt, app.password_digest('test-password-2026', salt)))
        app.Panel.sessions, app.Panel.attempts = {}, []
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), app.Panel)
        server.config, server.demo, server.config_path = self.config, True, '/not-used'
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        base = 'http://127.0.0.1:' + str(server.server_port)
        client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        def request(path, data=None, origin=None, host=None):
            headers = {'Origin': origin or base, 'Content-Type': 'application/json'}
            if host:
                headers['Host'] = host
            req = urllib.request.Request(base + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
            try:
                with client.open(req) as r:
                    return r.status, json.load(r)
            except urllib.error.HTTPError as exc:
                with exc:
                    return exc.code, json.load(exc)
        self.assertEqual(request('/api/state')[0], 401)
        self.assertEqual(request('/health', host='attacker.invalid')[0], 403)
        self.assertEqual(request('/api/login', {'password': 'wrong'})[0], 401)
        self.assertEqual(request('/api/login', {'password': 'test-password-2026'})[0], 200)
        code, state = request('/api/state')
        self.assertEqual(code, 200)
        self.assertNotIn('ssh_key', state['projects'][0])
        self.assertEqual(request('/api/update', {'project': 'pulse'})[0], 403)
        self.assertEqual(request('/api/update', {'project': 'pulse', 'csrf': state['csrf']}, origin='https://attacker.invalid')[0], 403)
        self.assertEqual(request('/api/update', {'project': 'pulse', 'csrf': state['csrf']})[0], 403)
        server.demo = False
        with app.db_open(self.config) as db:
            db.execute('DELETE FROM jobs')
        with patch.object(app, 'run', return_value=b'') as launch:
            code, queued = request('/api/update', {'project': 'pulse', 'csrf': state['csrf']})
            self.assertEqual(code, 202)
            self.assertTrue((Path(self.config['state_dir']) / 'jobs' / queued['job'] / 'worker.py').is_file())
            self.assertEqual(launch.call_args.args[0][0], 'systemd-run')
            self.assertEqual(request('/api/update', {'project': 'pulse', 'csrf': state['csrf']})[0], 409)
            self.assertEqual(launch.call_count, 1)
        self.assertEqual(request('/api/logout', {'csrf': state['csrf']})[0], 200)
        self.assertEqual(request('/api/state')[0], 401)


if __name__ == '__main__':
    unittest.main(verbosity=2)
