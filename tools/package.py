"""Build deployment archives from an explicit allowlist; never include live data."""
from pathlib import Path
import tarfile
import zipfile

root = Path(__file__).resolve().parents[1]
files = ['index.php', 'api.php', 'seed.php', 'router.php', '.htaccess', '.dockerignore',
         '.env.example', 'Dockerfile', 'compose.yaml', 'compose.https.yaml', 'start.sh',
         'README.md', 'DEPLOY.md', 'UPDATE.md', 'storage/.htaccess']
for directory in ['assets', 'deploy', 'tools']:
    files.extend(str(p.relative_to(root)).replace('\\', '/') for p in (root/directory).rglob('*') if p.is_file())
assert not any('.sqlite' in f or f == '.env' for f in files)
destination = root/'dist'
destination.mkdir(exist_ok=True)
with zipfile.ZipFile(destination/'pulse-server.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(root/name, name)
with tarfile.open(destination/'pulse-server.tar.gz', 'w:gz') as archive:
    for name in files:
        archive.add(root/name, arcname=name)
with zipfile.ZipFile(destination/'pulse-server.zip') as archive:
    assert 'storage/.htaccess' in archive.namelist()
    assert 'Dockerfile' in archive.namelist()
    assert not any(name.endswith('.sqlite') or name == '.env' for name in archive.namelist())
update=[f for f in files if f in ['index.php','api.php','seed.php','UPDATE.md'] or f.startswith('assets/') or f.startswith('tools/') and f.endswith('.php')]
with tarfile.open(destination/'pulse-update.tar.gz','w:gz') as archive:
    for name in update:archive.add(root/name,arcname=name)
print('Created full install archives and pulse-update.tar.gz. Update excludes data, .env, compose and Caddy configuration.')
