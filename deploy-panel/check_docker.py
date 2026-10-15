"""Opt-in integration check on disposable containers/volumes, never existing projects."""
import io
import json
from pathlib import Path
import subprocess
import tempfile
import uuid
import app

for kind, image, env_name, directory, filename in [
    ('pulse', 'pulse-web', 'QUIZ_DATA_DIR', '/var/lib/pulse', 'quiz.sqlite'),
    ('marathon', 'glava-marathon-web', 'MARATHON_DATA_DIR', '/var/lib/marathon', 'marathon.sqlite'),
]:
    with tempfile.TemporaryDirectory(prefix='gitdeck-docker-check-') as folder:
        root = Path(folder)
        project = 'gitdeck-check-' + uuid.uuid4().hex[:10]
        config = {'name': project, 'services': {'web': {'image': image,
                  'environment': {env_name: directory}, 'volumes': ['test_data:' + directory],
                  'healthcheck': {'interval': '1s', 'start_period': '1s', 'timeout': '5s', 'retries': 20}}},
                  'volumes': {'test_data': {}}}
        if kind == 'marathon':
            config['services']['bot'] = {'image': image, 'command': ['php', '-r', 'while(true){sleep(30);}'],
                                         'healthcheck': {'disable': True}}
        (root / 'compose.yaml').write_text(json.dumps(config), encoding='utf-8')
        p = {'kind': kind, 'directory': folder, 'compose': 'compose.yaml', 'profiles': []}
        p['services'] = ['web', 'bot'] if kind == 'marathon' else ['web']
        backup = root / 'backup'
        backup.mkdir()
        log = io.StringIO()
        dbpath = directory + '/' + filename
        try:
            app.start_services(p, log, build=False)
            php = '$d=new PDO("sqlite:".$argv[1]);$d->exec("CREATE TABLE gitdeck_test(value TEXT)");$d->exec("INSERT INTO gitdeck_test VALUES (\'before\')");'
            app.compose(p, ['exec', '-T', 'web', 'php', '-r', php, dbpath], log)
            app.compose(p, ['stop', 'web'], log)
            app.database_backup(p, backup, log)
            php = '$d=new PDO("sqlite:".$argv[1]);$d->exec("UPDATE gitdeck_test SET value=\'after\'");'
            app.compose(p, ['run', '--rm', '--no-deps', '--entrypoint', 'php', 'web', '-r', php, dbpath], log)
            app.database_restore(p, backup, log)
            php = '$d=new PDO("sqlite:".$argv[1]);echo $d->query("SELECT value FROM gitdeck_test")->fetchColumn();'
            result = app.compose(p, ['run', '--rm', '--no-deps', '--entrypoint', 'php', 'web', '-r', php, dbpath], log)
            assert result.decode().strip().endswith('before'), result.decode()
            print('PASS real Docker SQLite backup/restore: ' + kind)
            if kind == 'marathon':
                print('PASS real Docker startup: healthy web + running bot with healthcheck disabled')
        except Exception:
            print(log.getvalue())
            raise
        finally:
            # This compose file has a unique generated name and only our disposable test volume.
            app.compose(p, ['down', '-v'], log)
