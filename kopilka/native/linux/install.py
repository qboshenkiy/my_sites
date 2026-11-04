#!/usr/bin/env python3
from pathlib import Path
import shutil,subprocess
root=Path(__file__).resolve().parent;target=Path.home()/'.local/share/kopilka';target.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'kopilka.py',target/'kopilka.py');(target/'kopilka.py').chmod(0o755)
shutil.copy2(root.parents[1]/'web/icon.svg',target/'icon.svg')
icons=Path.home()/'.local/share/icons/hicolor/scalable/apps';icons.mkdir(parents=True,exist_ok=True)
shutil.copy2(target/'icon.svg',icons/'net.sbena.vano.kopilka.svg')
apps=Path.home()/'.local/share/applications';apps.mkdir(parents=True,exist_ok=True)
(apps/'net.sbena.vano.kopilka.desktop').write_text('[Desktop Entry]\nType=Application\nName=Копилка\nComment=Личное приложение Vano\nExec=/usr/bin/python3 "'+str(target/'kopilka.py')+'"\nIcon=net.sbena.vano.kopilka\nTerminal=false\nCategories=Office;Utility;\nStartupNotify=true\nStartupWMClass=net.sbena.vano.kopilka\n')
old=apps/'kopilka.desktop'
if old.exists() and str(target) in old.read_text():old.unlink()
for command in [['update-desktop-database',str(apps)],['gtk-update-icon-cache','--force','--ignore-theme-index',str(icons.parents[1])]]:
    if shutil.which(command[0]):subprocess.run(command,check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print('Иконка и ярлык «Копилка» установлены. Открытое окно нужно закрыть и запустить заново.')
