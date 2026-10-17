from pathlib import Path
import tarfile
import zipfile

root=Path(__file__).resolve().parents[1]
files=['index.php','api.php','router.php','.htaccess','.dockerignore','.env.example','Dockerfile',
       'compose.yaml','compose.https.yaml','compose.shared.yaml','start.sh','start-local.ps1','README.md','UPDATE.md','MINIAPP.md','storage/.htaccess']
for folder in ['assets','lib','deploy','tools']:
    files.extend(p.relative_to(root).as_posix() for p in (root/folder).rglob('*') if p.is_file())
assert not any('.sqlite' in p or p=='.env' for p in files)
dest=root/'dist';dest.mkdir(exist_ok=True)
with zipfile.ZipFile(dest/'reading-marathon.zip','w',zipfile.ZIP_DEFLATED) as z:
    for file in files:z.write(root/file,file)
with tarfile.open(dest/'reading-marathon.tar.gz','w:gz') as t:
    for file in files:t.add(root/file,arcname=file)
update=[f for f in files if f in ['index.php','api.php','UPDATE.md'] or f.startswith('assets/') or f.startswith('lib/') or f.startswith('tools/') and f.endswith('.php')]
with tarfile.open(dest/'reading-marathon-update.tar.gz','w:gz') as t:
    for file in update:t.add(root/file,arcname=file)
print('Created full install archives and reading-marathon-update.tar.gz; update excludes data, token, compose and Caddy configuration.')
