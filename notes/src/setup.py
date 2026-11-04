"""Provision Notes with GitDeck credentials and the existing HTTPS proxy."""
import importlib.util,json,sqlite3,subprocess,sys
from pathlib import Path
from runtime import ensure

def main():
    spec=importlib.util.spec_from_file_location('gitdeck','/opt/gitdeck/app.py');panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
    config=panel.load_config('/etc/gitdeck/config.json');root=Path(__file__).resolve().parents[1]
    with sqlite3.connect(Path(config['state_dir'])/'panel.sqlite') as db:row=db.execute('SELECT salt,digest FROM credentials WHERE id=1').fetchone()
    if not row:raise ValueError('Сначала задайте пароль GitDeck')
    p=next(p for p in config['projects'] if p['id']=='notes')
    ensure(root)
    panel.compose(p,['build','web','bot'],sys.stdout)
    panel.compose(p,['up','-d','--wait','--wait-timeout','120','web'],sys.stdout)
    panel.compose(p,['up','-d','--no-deps','bot'],sys.stdout)
    script="import sys,json,os;from pathlib import Path;p=Path('/data/password.json');v=sys.stdin.read();p.exists() or (p.write_text(v),os.chmod(p,0o600))"
    subprocess.run(panel.compose_command(p)+['exec','-T','web','python','-c',script],cwd=root,input=json.dumps({'salt':row[0],'digest':row[1]}).encode(),check=True,stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable,str(root/'src/connect_https.py'),'notes.vano.sbena.net'],check=True)
    print('Заметки готовы: https://notes.vano.sbena.net. Первоначальный пароль совпадает с паролем GitDeck.')
if __name__=='__main__':main()
