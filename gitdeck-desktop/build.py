from pathlib import Path
import shutil,subprocess,tempfile
root=Path(__file__).resolve().parent
out=root/'dist';out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    package=Path(temp);app=package/'usr/lib/gitdeck-desktop';app.mkdir(parents=True)
    for name in ('gitdeck-desktop.py','ssh-askpass.py','settings.py'):
        shutil.copy2(root/name,app/name);(app/name).chmod(0o755)
    control=package/'DEBIAN';control.mkdir()
    (control/'control').write_text('Package: gitdeck-desktop\nVersion: 1.1.0\nArchitecture: all\nMaintainer: GitDeck\nDepends: python3, python3-gi, gir1.2-gtk-3.0, gir1.2-webkit2-4.1, gir1.2-secret-1, openssh-client, zenity\nSection: utils\nPriority: optional\nDescription: Graphical SSH tunnel launcher for GitDeck\n')
    desktop=package/'usr/share/applications';desktop.mkdir(parents=True)
    (desktop/'gitdeck.desktop').write_text('[Desktop Entry]\nType=Application\nName=GitDeck\nComment=Подключиться к панели сервера\nExec=/usr/lib/gitdeck-desktop/gitdeck-desktop.py\nIcon=gitdeck\nTerminal=false\nCategories=Network;System;\n')
    icons=package/'usr/share/icons/hicolor/scalable/apps';icons.mkdir(parents=True)
    shutil.copy2(root.parent/'deploy-panel/icon.svg',icons/'gitdeck.svg')
    for directory in [package,*[p for p in package.rglob('*') if p.is_dir()]]:directory.chmod(0o755)
    for file in (control/'control',desktop/'gitdeck.desktop',icons/'gitdeck.svg'):file.chmod(0o644)
    subprocess.run(['dpkg-deb','--root-owner-group','--build',str(package),str(out/'gitdeck-desktop_1.1.0_all.deb')],check=True)
