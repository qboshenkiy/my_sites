"""Provision Kirkom Cargo and initialise staff access from the existing GitDeck hash."""
import importlib.util, json, sqlite3, subprocess, sys
from pathlib import Path

def main():
    spec=importlib.util.spec_from_file_location('gitdeck','/opt/gitdeck/app.py')
    panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
    config=panel.load_config('/etc/gitdeck/config.json')
    p=next(p for p in config['projects'] if p['id']=='kirkom-kargo')
    with sqlite3.connect(Path(config['state_dir'])/'panel.sqlite') as db:
        row=db.execute('SELECT salt,digest FROM credentials WHERE id=1').fetchone()
    if not row:raise ValueError('Сначала задайте пароль GitDeck')
    panel.compose(p,['build','web'],sys.stdout)
    panel.compose(p,['up','-d','--wait','--wait-timeout','120','web'],sys.stdout)
    script="const fs=require('fs');let s='';process.stdin.on('data',c=>s+=c);process.stdin.on('end',()=>{if(!fs.existsSync('/data/password.json'))fs.writeFileSync('/data/password.json',s,{mode:0o600})})"
    subprocess.run(panel.compose_command(p)+['exec','-T','web','node','-e',script],cwd=p['directory'],input=json.dumps({'algorithm':'gitdeck-scrypt','salt':row[0],'digest':row[1]}).encode(),check=True,stdout=subprocess.DEVNULL)
    subprocess.run([sys.executable,str(Path(__file__).with_name('connect_https.py')),'kirkom.vano.sbena.net'],check=True)
    print('Kirkom Cargo: https://kirkom.vano.sbena.net. Первоначальный пароль совпадает с паролем GitDeck.')
if __name__=='__main__':main()
