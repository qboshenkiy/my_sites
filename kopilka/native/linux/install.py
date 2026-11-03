#!/usr/bin/env python3
from pathlib import Path
import shutil
root=Path(__file__).resolve().parent;target=Path.home()/'.local/share/kopilka';target.mkdir(parents=True,exist_ok=True)
shutil.copy2(root/'kopilka.py',target/'kopilka.py');(target/'kopilka.py').chmod(0o755)
shutil.copy2(root.parents[1]/'web/icon.svg',target/'icon.svg')
apps=Path.home()/'.local/share/applications';apps.mkdir(parents=True,exist_ok=True)
(apps/'kopilka.desktop').write_text(f'[Desktop Entry]\nType=Application\nName=Копилка\nComment=Личные финансы, цели и расходы\nExec=python3 "{target}/kopilka.py"\nIcon={target}/icon.svg\nTerminal=false\nCategories=Office;Finance;\n')
print('Копилка добавлена в меню приложений. Нужны python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1.')
