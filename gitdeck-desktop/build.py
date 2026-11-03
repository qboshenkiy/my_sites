from pathlib import Path
import shutil,subprocess,tempfile
root=Path(__file__).resolve().parent
out=root/'dist';out.mkdir(exist_ok=True)
with tempfile.TemporaryDirectory() as temp:
    package=Path(temp);app=package/'usr/lib/gitdeck-desktop';app.mkdir(parents=True)
    for name in ('gitdeck-desktop.py','ssh-askpass.py'):
        shutil.copy2(root/name,app/name);(app/name).chmod(0o755)
    control=package/'DEBIAN';control.mkdir()
    (control/'control').write_text('Package: gitdeck-desktop\nVersion: 1.0.0\nArchitecture: all\nMaintainer: GitDeck\nDepends: python3, openssh-client, zenity, xdg-utils\nSection: utils\nPriority: optional\nDescription: Graphical SSH tunnel launcher for GitDeck\n')
    desktop=package/'usr/share/applications';desktop.mkdir(parents=True)
    (desktop/'gitdeck.desktop').write_text('[Desktop Entry]\nType=Application\nName=GitDeck\nComment=Подключиться к панели сервера\nExec=/usr/lib/gitdeck-desktop/gitdeck-desktop.py\nIcon=gitdeck\nTerminal=false\nCategories=Network;System;\n')
    icons=package/'usr/share/icons/hicolor/scalable/apps';icons.mkdir(parents=True)
    shutil.copy2(root.parent/'deploy-panel/icon.svg',icons/'gitdeck.svg')
    subprocess.run(['dpkg-deb','--root-owner-group','--build',str(package),str(out/'gitdeck-desktop_1.0.0_all.deb')],check=True)
