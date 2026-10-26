from pathlib import Path
import tarfile
import zipfile

root = Path(__file__).resolve().parent
files = ['app.py', 'index.html', 'VERSION', 'manifest.webmanifest', 'service-worker.js', 'pwa.js', 'icon.svg', 'README.md', 'install.sh', 'config.example.json', '.gitignore', 'tests.py', 'tests_monitor.py', 'tests_remote.py', 'tests_ui.js', 'tests_dashboard_ui.cjs', 'check_docker.py', 'package.py']
(root / 'dist').mkdir(exist_ok=True)
with tarfile.open(root / 'dist/gitdeck.tar.gz', 'w:gz') as archive:
    for name in files:
        archive.add(root / name, arcname=name)
with zipfile.ZipFile(root / 'dist/gitdeck.zip', 'w', zipfile.ZIP_DEFLATED) as archive:
    for name in files:
        archive.write(root / name, name)
print('Created deploy-panel/dist/gitdeck.tar.gz and gitdeck.zip (code only).')
