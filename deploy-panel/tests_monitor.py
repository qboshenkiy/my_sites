"""Monitoring uses fixtures, temporary SQLite files and read-only fake CLI responses."""
import http.server
import json
from pathlib import Path
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch
import app


class MonitorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = dict(id='marathon', kind='marathon', directory=str(self.root / 'marathon'),
                            compose='compose.yaml', profiles=['telegram'], services=['web', 'bot'])
        Path(self.project['directory']).mkdir()
        (Path(self.project['directory']) / '.env').write_text('APP_URL=https://example.org\nTELEGRAM_BOT_TOKEN=123456:abcdefghijklmnopqrstuvwxyz\nDB_PASSWORD=private-database-key\n')
        self.config = dict(state_dir=str(self.root / 'state'), projects=[self.project])

    def test_proc_counters_memory_cache_interfaces_and_physical_disks(self):
        proc = self.root / 'proc'; (proc / 'net').mkdir(parents=True)
        (proc / 'stat').write_text('cpu  100 0 200 600 100 0 0 0 50 0\n')
        (proc / 'meminfo').write_text('MemTotal: 1000 kB\nMemFree: 100 kB\nMemAvailable: 400 kB\nSwapTotal: 200 kB\nSwapFree: 150 kB\n')
        (proc / 'net/dev').write_text('eth0: 1000 1 0 0 0 0 0 0 2000 1 0 0 0 0 0 0\nlo: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0\nvethabcd: 999 1 0 0 0 0 0 0 999 1 0 0 0 0 0 0\n')
        (proc / 'diskstats').write_text('8 0 sda 1 0 20 0 1 0 40 0 0 0 0\n8 1 sda1 1 0 20 0 1 0 40 0 0 0 0\n')
        (proc / 'loadavg').write_text('0.5 0.4 0.3 1/100 123\n'); (proc / 'uptime').write_text('86400 100000\n')
        counters = app.host_counters(proc)
        self.assertEqual(counters['cpu_total'], 1000)  # guest is already included in user
        self.assertEqual(counters['cpu_idle'], 700)
        self.assertEqual(counters['network'], [1000, 2000])
        self.assertEqual(counters['disk_io'], [20 * 512, 40 * 512])
        sample = app.sample_metrics(counters, None, 0, [], 100)
        self.assertIsNone(sample['cpu']); self.assertIsNone(sample['rx'])
        self.assertEqual(sample['memory'], 60)
        self.assertEqual(sample['swap_used'], 50 * 1024)
        after = dict(counters, cpu_total=2000, cpu_idle=1400, network=[3000, 6000])
        sample = app.sample_metrics(after, counters, 10, [], 110)
        self.assertEqual(sample['cpu'], 30); self.assertEqual(sample['rx'], 200); self.assertEqual(sample['tx'], 400)
        self.assertIsNone(app.metric_delta(3000, 0, 10))
        missing = app.host_counters(self.root / 'absent-proc')
        sample = app.sample_metrics(missing, None, 0, [], 120)
        for key in ['cpu', 'memory', 'memory_used', 'swap_used', 'rx', 'read']:
            self.assertIsNone(sample[key])

    def test_history_persists_after_restart_is_bounded_and_expires(self):
        monitor = app.ServerMonitor(self.config)
        now = time.time()
        with app.db_open(self.config) as db:
            db.execute('INSERT INTO server_samples VALUES (?,?)', (int(now - 8 * 86400), json.dumps({'time': now - 8 * 86400, 'cpu': 1})))
            for i in range(3000):
                stamp = int(now - 86400 + i * 28)
                db.execute('INSERT OR REPLACE INTO server_samples VALUES (?,?)', (stamp, json.dumps({'time': stamp, 'cpu': 25})))
        with patch.object(app, 'host_counters', return_value=app.host_counters(self.root / 'absent')), patch.object(app, 'host_disks', return_value=[]):
            monitor.collect()
        result = monitor.view(86400)
        self.assertLessEqual(len(result['history']), 243)
        with app.db_open(self.config) as db:
            self.assertEqual(db.execute('SELECT count(*) FROM server_samples WHERE stamp<?', (now - 7 * 86400,)).fetchone()[0], 0)
        restarted = app.ServerMonitor(self.config)
        self.assertGreater(len(restarted.view(86400)['history']), 100)
        with self.assertRaises(ValueError): restarted.view(123)

    def test_docker_returns_only_selected_fields(self):
        rows = [dict(Names='marathon-web-1', Image='marathon-web', State='running', Status='Up 1 hour (healthy)',
                     Labels='com.docker.compose.project=marathon,com.docker.compose.service=web,private-label=SECRET', Command='SECRET')]
        def cli(command, **kwargs):
            if command[1] == 'ps': return json.dumps(rows[0]), False
            if command[1] == 'stats': return json.dumps(dict(Name='marathon-web-1', CPUPerc='5%', MemUsage='100MiB / 4GiB', NetIO='1MB / 2MB')), False
            return json.dumps(dict(Type='Images', Size='2GB', Active=2, TotalCount=3, Reclaimable='1GB')), False
        with patch.object(app, 'monitor_command', side_effect=cli): snapshot = app.docker_snapshot()
        self.assertEqual(snapshot['containers'][0]['service'], 'web')
        self.assertEqual(snapshot['containers'][0]['cpu'], '5%')
        self.assertNotIn('SECRET', json.dumps(snapshot))

    def test_read_only_logs_validate_and_redact(self):
        with patch.object(app, 'monitor_command', return_value=('token 123456:abcdefghijklmnopqrstuvwxyz password private-database-key\n\x1b[31mERROR\x1b[0m\n', False)) as command:
            result = app.runtime_log(self.config, 'marathon', 300)
            args = command.call_args.args[0]
            self.assertEqual(args[-5:], ['logs', '--no-color', '--timestamps', '--tail', '300'])
            self.assertIn('--profile', args); self.assertIn('logs', args)
            self.assertNotIn('private-database-key', result['log']); self.assertNotIn('abcdefghijklmnopqrstuvwxyz', result['log'])
            self.assertNotIn('\x1b', result['log'])
            app.runtime_log(self.config, '@panel', 100)
            self.assertEqual(command.call_args.args[0][:3], ['journalctl', '-u', 'gitdeck.service'])
        for project, tail in [('marathon;rm -rf /', 100), ('marathon', 99999)]:
            with patch.object(app, 'monitor_command') as command, self.assertRaises(ValueError):
                app.runtime_log(self.config, project, tail)
            command.assert_not_called()

    def test_bounded_command_output_and_timeout(self):
        result, truncated = app.monitor_command([sys.executable, '-c', 'print("a"*100)'], limit=20)
        self.assertEqual(len(result), 20); self.assertTrue(truncated)
        with self.assertRaises(RuntimeError):
            app.monitor_command([sys.executable, '-c', 'import time;time.sleep(5)'], timeout=.1)

    def test_api_authentication_period_validation_and_logs(self):
        server = http.server.ThreadingHTTPServer(('127.0.0.1', 0), app.Panel)
        server.config, server.demo, server.monitor = self.config, False, app.ServerMonitor(self.config)
        server.monitor.docker = {'containers': [], 'error': None}
        thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        self.addCleanup(server.server_close); self.addCleanup(server.shutdown)
        previous = app.Panel.sessions
        self.addCleanup(setattr, app.Panel, 'sessions', previous)
        app.Panel.sessions = {'test-session': {'csrf': 'test-csrf', 'expires': time.time() + 60}}
        def request(path, auth=True, host=None):
            headers = {'Cookie': 'gitdeck=test-session'} if auth else {}
            if host: headers['Host'] = host
            req = urllib.request.Request(f'http://127.0.0.1:{server.server_port}' + path, headers=headers)
            try: response = urllib.request.urlopen(req, timeout=5)
            except urllib.error.HTTPError as error: response = error
            with response:return response.status, json.load(response)
        for path in ['/api/server', '/api/containers', '/api/runtime-log']:
            self.assertEqual(request(path, False)[0], 401)
            self.assertEqual(request(path, host='evil.example')[0], 403)
        self.assertEqual(request('/api/server?period=123')[0], 400)
        self.assertEqual(request('/api/server?period=900')[0], 200)
        self.assertEqual(request('/api/containers')[0], 200)
        self.assertEqual(request('/api/runtime-log?project=not-configured')[0], 400)
        with patch.object(app, 'monitor_command', return_value=('private-database-key', False)):
            code, result = request('/api/runtime-log?project=marathon&tail=100')
        self.assertEqual(code, 200); self.assertNotIn('private-database-key', result['log'])


if __name__ == '__main__': unittest.main()
