"""Local interface preview; deploy commands are disabled and state is temporary."""
import json
from pathlib import Path
import tempfile
import app

with tempfile.TemporaryDirectory(prefix='gitdeck-preview-') as folder:
    config = json.loads(Path(__file__).with_name('config.example.json').read_text(encoding='utf-8'))
    config['state_dir'] = folder
    config['port'] = 8120
    salt = 'b' * 32
    with app.db_open(config) as db:
        db.execute('INSERT INTO credentials VALUES(1,?,?)', (salt, app.password_digest('gitdeck-demo-2026', salt)))
    print('DEMO login: gitdeck-demo-2026. All deployment actions disabled.', flush=True)
    app.serve(config, str(Path(folder) / 'config.json'), demo=True)
