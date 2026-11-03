#!/usr/bin/python3
"""Install a launcher for the current user without replacing system packages."""
from pathlib import Path
import shutil,subprocess,datetime
root=Path(__file__).resolve().parent
target=Path.home()/'.local/share/gitdeck-desktop';target.mkdir(parents=True,exist_ok=True)
desktop=Path.home()/'.local/share/applications/gitdeck.desktop';desktop.parent.mkdir(parents=True,exist_ok=True)
backup=target/'backups'/datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
for name in ('gitdeck-desktop.py','settings.py','ssh-askpass.py'):
    path=target/name
    if path.exists():backup.mkdir(parents=True,exist_ok=True);shutil.copy2(path,backup/name)
    shutil.copy2(root/name,path);path.chmod(0o755)
shutil.copy2(root.parent/'deploy-panel/icon.svg',target/'icon.svg')
if desktop.exists():backup.mkdir(parents=True,exist_ok=True);shutil.copy2(desktop,backup/'gitdeck.desktop')
desktop.write_text('[Desktop Entry]\nType=Application\nName=GitDeck\nComment=GitDeck 1.1.1 — панель сервера внутри приложения\nExec=/usr/bin/python3 "'+str(target/'gitdeck-desktop.py')+'"\nIcon='+str(target/'icon.svg')+'\nTerminal=false\nCategories=Network;System;\n')
desktop.chmod(0o755)
if shutil.which('update-desktop-database'):subprocess.run(['update-desktop-database',str(desktop.parent)],check=False,capture_output=True)
print('Installed user launcher:',desktop)
print('Application version: 1.1.1; existing connection settings preserved')
