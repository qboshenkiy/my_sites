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

    def test_bot_starts_without_compose_healthcheck_wait(self):
        p = dict(self.project, services=['web', 'bot'])
        calls = []
        def docker(project, args, log):
            calls.append(args)
            if args[0] == 'ps':
                return b'bot-container-id\n'
            return b''
        with patch.object(app, 'compose', side_effect=docker), patch.object(app.time, 'sleep'):
            app.start_services(p, io.StringIO())
        self.assertIn('--wait', calls[0])
        self.assertEqual(calls[0][-1], 'web')
        self.assertNotIn('--wait', calls[1])
        self.assertEqual(calls[1][-1], 'bot')
        self.assertEqual(sum(c[0] == 'ps' for c in calls), 3)

    def test_exited_bot_fails_startup(self):
        p = dict(self.project, services=['web', 'bot'])
        with patch.object(app, 'compose', return_value=b''), patch.object(app.time, 'sleep'):
            with self.assertRaisesRegex(RuntimeError, 'Бот'):
                app.start_services(p, io.StringIO())

    def test_config_rejects_credentials_and_shell_text(self):
        good = dict(self.project, repo='git@github.com:user/repository.git')
        app.validate_project(good)
        for field, value in [('repo', 'https://secret@github.com/u/r.git'), ('branch', 'main;reboot'),
                             ('subdir', '../outside'), ('compose', '/etc/passwd'), ('services', ['proxy'])]:
            with self.assertRaises(ValueError):
                app.validate_project(dict(good, **{field: value}))

    def test_branches_and_historical_commit_checkout(self):
        original = self.sha
        (self.source / 'api.php').write_text('latest api')
        subprocess.run(['git', 'add', '.'], cwd=self.source, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', '-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'second version'], cwd=self.source, check=True, stdout=subprocess.DEVNULL)
        subprocess.run(['git', 'branch', 'stable', original], cwd=self.source, check=True)
        info = app.revisions(self.config, self.project, 'main')
        self.assertIn('stable', info['branches'])
        self.assertEqual(len(info['commits']), 2)
        self.assertEqual(info['commits'][1]['sha'], original)
        folder = self.root / 'historic'
        sha = app.checkout(self.project, self.config, folder, io.StringIO(), original[:8])
        self.assertEqual(sha, original)
        self.assertEqual((folder / 'api.php').read_text(), 'new api')
        stable = self.root / 'stable'
        self.assertEqual(app.checkout(self.project, self.config, stable, io.StringIO(), 'stable'), original)

    def test_generic_module_paths_protect_runtime_and_settings(self):
        for paths in [['.'], ['../app'], ['.env'], ['storage'], ['src/.env'], ['compose.yaml'], ['Dockerfile'], ['src', 'src/app']]:
            with self.assertRaises(ValueError):
                app.validate_paths(paths)
        p = dict(self.project, kind='docker', paths=['assets'], main_service='web')
        app.validate_paths(p['paths'])
        (self.dest / 'assets/.env').write_text('keep this secret')
        with self.assertRaisesRegex(ValueError, 'данные'):
            app.copy_code(self.source, self.dest, p)
        self.assertEqual((self.dest / 'assets/.env').read_text(), 'keep this secret')

    def test_settings_atomic_persistence_and_overlap_rejection(self):
        config = dict(self.config, projects_root=str(self.root))
        config['projects'] = [dict(self.project, repo='https://github.com/user/sites.git')]
        path = self.root / 'config.json'
        path.write_text(json.dumps(config), encoding='utf-8')
        class Server:
            pass
        server = Server()
        server.config, server.config_path = config, str(path)
        old = config['projects'][0]
        form = dict(old, name='Renamed Pulse')
        prepared = app.project_from_form(form, old, config)
        for changes in ({'id': 'different-id'}, {'kind': 'marathon'}):
            with self.assertRaisesRegex(ValueError, 'Тип и идентификатор'):
                app.project_from_form(dict(form, **changes), old, config)
        app.save_config(server, [prepared], app.config_revision(config))
        self.assertEqual(app.load_config(path)['projects'][0]['name'], 'Renamed Pulse')
        with self.assertRaisesRegex(ValueError, 'изменились'):
            app.save_config(server, [prepared], app.config_revision(config))
        with self.assertRaises(ValueError):
            app.project_from_form(dict(form, directory=str(self.root.parent)), old, config)
        with self.assertRaises(ValueError):
            app.validate_config(dict(config, projects=[old, dict(old, id='other', directory=str(self.dest / 'assets'))]))

    def test_env_form_hides_secrets_and_preserves_unchanged_lines(self):
        text = "# keep comment\nDOMAIN=old.example.com\nTELEGRAM_BOT_TOKEN='private-token-123'\nEMPTY=\nOTHER=value # keep too\n"
        (self.dest / '.env').write_text(text, encoding='utf-8')
        info = app.env_settings(self.project)
        token = next(f for f in info['fields'] if f['key'] == 'TELEGRAM_BOT_TOKEN')
        self.assertTrue(token['configured'])
        self.assertEqual(token['value'], '')
        self.assertNotIn('private-token-123', json.dumps(info))
        values = {key: value for key, value, *_ in app.env_records(text)}
        self.assertEqual(values['EMPTY'], '')
        changed = app.patch_env(text, {'DOMAIN': 'new.example.com', 'NEW_SECRET': "some'$value"})
        self.assertIn("TELEGRAM_BOT_TOKEN='private-token-123'", changed)
        self.assertIn('OTHER=value # keep too', changed)
        self.assertEqual({k: v for k, v, *_ in app.env_records(changed)}['NEW_SECRET'], "some'$value")
        for changes in [{'DOMAIN': 'https://bad.com'}, {'APP_PORT': '70000'}, {'COMPOSE_FILE': '../bad.yaml'}, {'KEY': 'a\nb'}]:
            with self.assertRaises(ValueError):
                app.validate_env_changes(changes)

    def test_environment_failure_restores_env_and_redacts_logs(self):
        old = 'DOMAIN=old.example.com\nTELEGRAM_BOT_TOKEN=old-private-token\n'
        (self.dest / '.env').write_text(old, encoding='utf-8')
        folder = self.root / 'state/jobs' / self.job
        payload = {'env_revision': app.env_revision(old), 'changes': {'DOMAIN': 'new.example.com', 'TELEGRAM_BOT_TOKEN': 'new-private-token'}}
        (folder / 'environment.json').write_text(json.dumps(payload), encoding='utf-8')
        log = io.StringIO()
        calls = []
        def start(p, protected_log, build):
            calls.append(1)
            protected_log.write('old-private-token new-private-token')
            if len(calls) == 1:
                raise RuntimeError('failed startup')
        with patch.object(app, 'start_services', side_effect=start), patch.object(app, 'compose', return_value=b'web\n'):
            with self.assertRaisesRegex(RuntimeError, 'настроек'):
                app.apply_environment(self.config, self.project, self.job, log)
        self.assertEqual((self.dest / '.env').read_text(encoding='utf-8'), old)
        self.assertEqual(len(calls), 2)
        self.assertNotIn('private-token', log.getvalue())
        self.assertTrue((folder / 'previous.env').exists())

    def test_environment_success_updates_file_without_touching_code(self):
        old = 'DOMAIN=old.example.com\nTELEGRAM_BOT_TOKEN=keep-me-private\n'
        (self.dest / '.env').write_text(old, encoding='utf-8')
        folder = self.root / 'state/jobs' / self.job
        payload = {'env_revision': app.env_revision(old), 'changes': {'DOMAIN': 'new.example.com'}}
        (folder / 'environment.json').write_text(json.dumps(payload), encoding='utf-8')
        with patch.object(app, 'start_services') as start, patch.object(app, 'compose', return_value=b'web\nproxy\n') as docker:
            app.apply_environment(self.config, self.project, self.job, io.StringIO())
        values = {key: value for key, value, *_ in app.env_records(app.env_text(self.project))}
        self.assertEqual(values['DOMAIN'], 'new.example.com')
        self.assertEqual(values['TELEGRAM_BOT_TOKEN'], 'keep-me-private')
        self.assertEqual((self.dest / 'api.php').read_text(), 'old api')
        self.assertEqual(start.call_args.kwargs['build'], False)
        self.assertTrue(any(call.args[1] == ['up', '-d', '--no-deps', 'proxy'] for call in docker.call_args_list))
        with app.db_open(self.config) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'success')

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
        self.project['repo'] = 'https://github.com/user/sites.git'
        self.config['projects_root'] = str(self.root)
        salt = 'a' * 32
        with app.db_open(self.config) as db:
            db.execute('INSERT INTO credentials VALUES(1,?,?)', (salt, app.password_digest('test-password-2026', salt)))
        app.Panel.sessions, app.Panel.attempts = {}, []
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), app.Panel)
        server.config, server.demo, server.config_path = self.config, True, str(self.root / 'config.json')
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
        new_module = dict(self.project, id='another', name='Another', directory=str(self.root / 'another'))
        code, result = request('/api/project/save', {'project': new_module, 'config_revision': state['config_revision'], 'csrf': state['csrf']})
        self.assertEqual(code, 200, result)
        _, state = request('/api/state')
        self.assertEqual(len(state['projects']), 2)
        self.assertTrue(Path(server.config_path).is_file())
        self.assertEqual(request('/api/project/remove', {'project': 'another', 'config_revision': state['config_revision'], 'csrf': state['csrf']})[0], 200)
        _, state = request('/api/state')
        (self.dest / '.env').write_text('DOMAIN=old.example.com\nTELEGRAM_BOT_TOKEN=private-test-token\n', encoding='utf-8')
        code, environment = request('/api/environment?project=pulse')
        self.assertEqual(code, 200)
        self.assertNotIn('private-test-token', json.dumps(environment))
        with patch.object(app, 'run', return_value=b''):
            code, envjob = request('/api/environment/save', {'project': 'pulse', 'changes': {'DOMAIN': 'new.example.com'},
                                    'env_revision': environment['env_revision'], 'config_revision': state['config_revision'], 'csrf': state['csrf']})
        self.assertEqual(code, 202, envjob)
        with app.db_open(server.config) as db:
            self.assertEqual(db.execute('SELECT action FROM jobs').fetchone()[0], 'configure')
            db.execute('DELETE FROM jobs')
        with patch.object(app, 'run', return_value=b'') as launch:
            code, queued = request('/api/update', {'project': 'pulse', 'ref': 'stable', 'csrf': state['csrf']})
            self.assertEqual(code, 202)
            self.assertTrue((Path(self.config['state_dir']) / 'jobs' / queued['job'] / 'worker.py').is_file())
            self.assertEqual(launch.call_args.args[0][0], 'systemd-run')
            self.assertEqual(request('/api/update', {'project': 'pulse', 'csrf': state['csrf']})[0], 409)
            self.assertEqual(launch.call_count, 1)
            with app.db_open(server.config) as db:
                self.assertEqual(db.execute('SELECT target_ref FROM jobs').fetchone()[0], 'stable')
            self.assertEqual(request('/api/project/save', {'project': new_module, 'config_revision': state['config_revision'], 'csrf': state['csrf']})[0], 409)
        self.assertEqual(request('/api/logout', {'csrf': state['csrf']})[0], 200)
        self.assertEqual(request('/api/state')[0], 401)


class ChronoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.source = self.root / 'source'
        self.dest = self.root / 'installed'
        self.source.mkdir()
        self.p = dict(id='chrono-logos', name='Chrono Logos', kind='chrono',
                      repo='https://github.com/qboshenkiy/my_sites.git', branch='main', subdir='chrono_logos',
                      directory=str(self.dest), compose='compose.yaml', services=['web'], profiles=[])
        for name in app.REQUIRED['chrono'] + ['public/assets/app.css', '.dockerignore']:
            path = self.source / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('new code: ' + name)
        self.config = dict(state_dir=str(self.root / 'state'), projects=[self.p])
        app.db_open(self.config).close()
        self.job = 'c' * 24
        self.jobdir = self.root / 'state/jobs' / self.job
        self.jobdir.mkdir(parents=True)
        with app.db_open(self.config) as db:
            db.execute('INSERT INTO jobs (id,project,status,created,updated) VALUES (?,?,?,?,?)',
                       (self.job, self.p['id'], 'queued', time.time(), time.time()))
        self.calls = []

    def checkout(self, p, config, source, log):
        app.copy_code(self.source, source, p)
        return 'a' * 40

    def compose(self, p, args, log):
        self.calls.append(args)
        if args[0] == 'run' and 'pg_dump ' in args[-1]:
            (self.jobdir / 'database.dump').write_bytes(b'synthetic PostgreSQL dump')
        return b''

    def test_first_install_bootstraps_without_database_backup(self):
        app.validate_project(self.p)
        with patch.object(app, 'checkout', side_effect=self.checkout), patch.object(app, 'compose', side_effect=self.compose):
            app.deploy(self.config, self.p, self.job, io.StringIO())
        self.assertTrue((self.dest / 'ops/Dockerfile').exists())
        values = {k: v for k, v, *_ in app.env_records(app.env_text(self.p))}
        self.assertGreaterEqual(len(values['DB_PASSWORD']), 32)
        self.assertEqual(values['APP_URL'], 'https://vano.sbena.net/')
        self.assertNotEqual(values['DB_PASSWORD'], values['ADMIN_PASSWORD'])
        self.assertFalse(any(args[0] == 'run' for args in self.calls))
        self.assertTrue(any(args[:2] == ['up', '-d'] for args in self.calls))
        self.assertTrue(all(not app.allowed(n, self.p) for n in ('.env', 'writable/session/session1', 'public/uploads/test.jpg', 'vendor/autoload.php', 'compose.yaml')))

    def test_bootstrap_refuses_existing_files(self):
        self.dest.mkdir()
        (self.dest / '.env').write_text('original secret')
        with self.assertRaisesRegex(ValueError, 'пустой'):
            app.bootstrap_chrono(self.p, self.source)
        self.assertEqual((self.dest / '.env').read_text(), 'original secret')

    def test_checkout_chrono_from_monorepo_subdirectory(self):
        repository = self.root / 'monorepo'
        shutil_source = repository / 'chrono_logos'
        app.copy_code(self.source, shutil_source, self.p)
        (shutil_source / '.env').write_text('LOCAL_SECRET_MUST_NOT_DEPLOY')
        (repository / 'index.php').write_text('another application')
        for args in [['init', '-b', 'main'], ['add', '.'],
                     ['-c', 'user.name=Test', '-c', 'user.email=test@example.invalid', 'commit', '-m', 'monorepo']]:
            subprocess.run(['git'] + args, cwd=repository, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        p = dict(self.p, repo=str(repository))
        output = self.root / 'checkout'
        sha = app.checkout(p, self.config, output, io.StringIO())
        self.assertEqual(len(sha), 40)
        self.assertTrue((output / 'ops/Dockerfile').is_file())
        self.assertTrue((output / 'app/Config/Paths.php').is_file())
        self.assertFalse((output / '.env').exists())
        self.assertFalse((output / 'index.php').exists())

    def test_failed_update_restores_postgres_and_keeps_runtime(self):
        app.bootstrap_chrono(self.p, self.source)
        app.copy_code(self.source, self.dest, self.p)
        (self.dest / 'public/index.php').write_text('old application')
        for name in ('writable/session/session1', 'public/uploads/photo.jpg'):
            path = self.dest / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('persistent runtime')
        env = app.env_text(self.p)
        starts = []
        def start(*args, **kw):
            starts.append(1)
            if len(starts) == 1:
                raise RuntimeError('synthetic failed build')
        with patch.object(app, 'checkout', side_effect=self.checkout), patch.object(app, 'compose', side_effect=self.compose), patch.object(app, 'start_services', side_effect=start):
            with self.assertRaisesRegex(RuntimeError, 'synthetic'):
                app.deploy(self.config, self.p, self.job, io.StringIO())
        self.assertEqual((self.dest / 'public/index.php').read_text(), 'old application')
        self.assertEqual(app.env_text(self.p), env)
        self.assertEqual((self.dest / 'public/uploads/photo.jpg').read_text(), 'persistent runtime')
        self.assertEqual((self.dest / 'writable/session/session1').read_text(), 'persistent runtime')
        restore = next(args for args in self.calls if args[0] == 'run' and 'pg_restore ' in args[-1])
        self.assertIn('--create --clean', restore[-1])
        self.assertTrue((self.jobdir / 'database.dump').exists())
        self.assertEqual(len(starts), 2)

    def test_first_failure_keeps_candidate_for_retry(self):
        with patch.object(app, 'checkout', side_effect=self.checkout), patch.object(app, 'compose', side_effect=self.compose), patch.object(app, 'start_services', side_effect=RuntimeError('first build failed')):
            with self.assertRaisesRegex(RuntimeError, 'first build failed'):
                app.deploy(self.config, self.p, self.job, io.StringIO())
        self.assertTrue((self.dest / 'ops/Dockerfile').is_file())
        with patch.object(app, 'checkout', side_effect=self.checkout), patch.object(app, 'compose', side_effect=self.compose):
            app.deploy(self.config, self.p, self.job, io.StringIO())
        with app.db_open(self.config) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs').fetchone()[0], 'success')

    def test_database_identity_change_rejected_before_mutation(self):
        app.bootstrap_chrono(self.p, self.source)
        old = app.env_text(self.p)
        (self.jobdir / 'environment.json').write_text(json.dumps(dict(env_revision=app.env_revision(old), changes={'DB_PASSWORD': 'different-password'})))
        with self.assertRaisesRegex(ValueError, 'PostgreSQL'), patch.object(app, 'compose') as docker:
            app.apply_environment(self.config, self.p, self.job, io.StringIO())
        docker.assert_not_called()
        self.assertEqual(app.env_text(self.p), old)
        fields = {f['key']: f for f in app.env_settings(self.p)['fields']}
        self.assertEqual(fields['ADMIN_PASSWORD']['value'], '')
        self.assertTrue(fields['ADMIN_PASSWORD']['configured'])


if __name__ == '__main__':
    unittest.main(verbosity=2)
