"""Local interface preview; deploy commands are disabled and state is temporary."""
import json
from pathlib import Path
import tempfile
import app

with tempfile.TemporaryDirectory(prefix='gitdeck-preview-') as folder:
    config = json.loads(Path(__file__).with_name('config.example.json').read_text(encoding='utf-8'))
    config['state_dir'] = str(Path(folder) / 'state')
    config['port'] = 8121
    config['projects_root'] = str(Path(folder) / 'projects')
    for project in config['projects']:
        project['directory'] = str(Path(config['projects_root']) / project['id'])
        Path(project['directory']).mkdir(parents=True)
        if project['kind'] != 'self':
            (Path(project['directory']) / '.env').write_text('DOMAIN=example.com\nAPP_URL=https://example.com\nAPP_PORT=8081\nAPP_BIND=0.0.0.0\nTELEGRAM_BOT_TOKEN=demo-not-a-real-token\n', encoding='utf-8')
    config_path = Path(folder) / 'config.json'
    config_path.write_text(json.dumps(config), encoding='utf-8')
    salt = 'b' * 32
    with app.db_open(config) as db:
        db.execute('INSERT INTO credentials VALUES(1,?,?)', (salt, app.password_digest('gitdeck-demo-2026', salt)))
    print('DEMO login: gitdeck-demo-2026. All deployment actions disabled.', flush=True)
    app.serve(config, str(config_path), demo=True)
