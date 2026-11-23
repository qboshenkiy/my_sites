"""Install only KirkomKargo, then connect its route to the existing proxy."""
import importlib.util, subprocess, sys
from pathlib import Path

def main():
    spec=importlib.util.spec_from_file_location('gitdeck','/opt/gitdeck/app.py')
    panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
    config=panel.load_config('/etc/gitdeck/config.json')
    p=next(p for p in config['projects'] if p['id']=='kirkom-kargo')
    panel.compose(p,['build','web'],sys.stdout)
    panel.compose(p,['up','-d','--wait','--wait-timeout','120','web'],sys.stdout)
    subprocess.run([sys.executable,str(Path(__file__).with_name('connect_https.py')),'kirkom.vano.sbena.net'],check=True)
    print('KirkomKargo: https://kirkom.vano.sbena.net — демонстрация, API не подключены.')
if __name__=='__main__':main()
