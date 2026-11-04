#!/usr/bin/env python3
from pathlib import Path
import shutil,subprocess
root=Path(__file__).resolve().parent;target=Path.home()/'.local/share/vano-notes';target.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'notes.py',target/'notes.py');(target/'notes.py').chmod(0o755)
shutil.copy2(root.parents[1]/'web/icon.svg',target/'icon.svg')
apps=Path.home()/'.local/share/applications';apps.mkdir(parents=True,exist_ok=True)
(apps/'vano-notes.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Заметки\nComment=Личные заметки, идеи и планы\nExec=/usr/bin/python3 "{target}/notes.py"\nIcon={target}/icon.svg\nTerminal=false\nCategories=Office;Utility;\nStartupWMClass=net.sbena.vano.notes\n')
subprocess.run(['update-desktop-database',str(apps)],check=False,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
print('Приложение «Заметки» добавлено в меню Ubuntu.')
