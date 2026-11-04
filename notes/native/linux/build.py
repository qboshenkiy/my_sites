"""Build an installable Ubuntu package from source, without credentials or user data."""
from pathlib import Path
import shutil,subprocess,tempfile
root=Path(__file__).resolve().parent;out=root.parents[1]/'web/notes-desktop_1.1.0_all.deb'
with tempfile.TemporaryDirectory() as temp:
    package=Path(temp);app=package/'usr/lib/vano-notes';app.mkdir(parents=True)
    shutil.copy2(root/'notes.py',app/'notes.py');shutil.copy2(root.parents[1]/'web/icon.svg',app/'icon.svg')
    control=package/'DEBIAN';control.mkdir()
    (control/'control').write_text('Package: vano-notes\nVersion: 1.1.0\nArchitecture: all\nMaintainer: Vano Apps\nDepends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1\nSection: utils\nPriority: optional\nDescription: Private synchronized notes for Ubuntu\n')
    binary=package/'usr/bin';binary.mkdir(parents=True)
    (binary/'vano-notes').write_text('#!/bin/sh\nexec /usr/bin/python3 /usr/lib/vano-notes/notes.py "$@"\n');(binary/'vano-notes').chmod(0o755)
    desktop=package/'usr/share/applications';desktop.mkdir(parents=True)
    (desktop/'net.sbena.vano.notes.desktop').write_text('[Desktop Entry]\nType=Application\nName=Заметки\nComment=Личные заметки, идеи и планы\nExec=vano-notes\nIcon=net.sbena.vano.notes\nTerminal=false\nCategories=Office;Utility;\nStartupWMClass=net.sbena.vano.notes\n')
    icons=package/'usr/share/icons/hicolor/scalable/apps';icons.mkdir(parents=True)
    shutil.copy2(root.parents[1]/'web/icon.svg',icons/'net.sbena.vano.notes.svg')
    for directory in [package,*[p for p in package.rglob('*') if p.is_dir()]]:directory.chmod(0o755)
    for file in [p for p in package.rglob('*') if p.is_file()]:file.chmod(0o755 if file==binary/'vano-notes' else 0o644)
    subprocess.run(['dpkg-deb','--root-owner-group','--build',str(package),str(out)],check=True)
print(out)
