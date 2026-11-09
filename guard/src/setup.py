"""Provision Guard through GitDeck, preserving existing data and Caddy inode."""
import importlib.util
import json
from pathlib import Path
import re
import sqlite3
import subprocess
import types

DOMAIN='guard.vano.sbena.net'


def route(text):
    marker='# Guard HTTPS'
    pattern=re.escape(marker+' BEGIN')+r'.*?'+re.escape(marker+' END')
    rest=re.sub(pattern,'',text,flags=re.S)
    if re.search(r'(?m)^\s*(?:https://)?'+re.escape(DOMAIN)+r'\s*\{',rest):raise ValueError('Домен Guard уже занят')
    # Access logging goes to Caddy stdout. Docker rotation is configured below.
    lines=[];block_lines=[];depth=0
    for line in rest.splitlines():
        if depth==0 and not block_lines and not (line.strip().endswith('{') and not line.lstrip().startswith('#')):
            lines.append(line);continue
        block_lines.append(line);depth+=line.count('{')-line.count('}')
        if depth==0:
            # An empty first line denotes Caddy's global options block.
            if block_lines[0].strip()!='{' and not any(re.match(r'^\s*log(?:\s|$)',l) for l in block_lines[1:]):
                block_lines.insert(1,'    log {\n        output stdout\n        format json\n    }')
            lines.extend(block_lines);block_lines=[]
    lines.extend(block_lines)
    return '\n'.join(lines).rstrip()+'\n'


def main():
    spec=importlib.util.spec_from_file_location('gitdeck','/opt/gitdeck/app.py');panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
    config=panel.load_config('/etc/gitdeck/config.json')
    proxy=next(p for p in config['projects'] if p['kind']=='marathon' and p['compose']=='compose.https.yaml')
    root=Path(__file__).resolve().parents[1]
    subprocess.run(['python3',str(root/'src/install_firewall.py')],check=True)
    subprocess.run(['python3',str(root/'src/install_docker_bridge.py')],check=True)
    command=['docker','compose','-f','compose.yaml','-f','compose.gitdeck-guard.yaml']
    subprocess.run(command+['up','-d','--build','--wait','web'],cwd=root,check=True)
    with sqlite3.connect(Path(config['state_dir'])/'panel.sqlite') as db:
        row=db.execute('SELECT salt,digest FROM credentials WHERE id=1').fetchone()
    if not row:raise ValueError('Сначала задайте пароль GitDeck')
    # Existing password remains untouched on subsequent provisioning runs.
    script="import sys,json,os;from pathlib import Path;p=Path('/data/password.json');v=sys.stdin.read();p.exists() or (p.write_text(v),os.chmod(p,0o600))"
    subprocess.run(command+['exec','-T','web','python','-c',script],cwd=root,input=json.dumps({'salt':row[0],'digest':row[1]}).encode(),check=True,stdout=subprocess.DEVNULL)
    caddy=Path(proxy['directory'])/'deploy/Caddyfile'
    if caddy.is_symlink():raise ValueError('Ссылка вместо Caddyfile')
    original=caddy.read_text();backup=caddy.with_name('Caddyfile.before-guard')
    if not backup.exists():backup.write_text(original)
    try:
        updated=route(original)
        caddy.write_text(updated)
        panel.compose(proxy,['exec','-T','proxy','caddy','validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],None)
        panel.compose(proxy,['exec','-T','proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],None)
    except Exception:
        caddy.write_text(original)
        panel.compose(proxy,['exec','-T','proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],None)
        raise
    (root/'compose.gitdeck-https.yaml').unlink(missing_ok=True)
    # Keep proxy log disk usage bounded. Compose preserves all existing overlays.
    rotation=Path(proxy['directory'])/'compose.gitdeck-guard.yaml'
    rotation.write_text('services:\n  proxy:\n    logging:\n      driver: json-file\n      options:\n        max-size: "10m"\n        max-file: "3"\n')
    args=panel.compose_command(proxy)
    subprocess.run(args+['up','-d','--no-deps','proxy'],cwd=proxy['directory'],check=True)
    server=types.SimpleNamespace(config=config,config_path='/etc/gitdeck/config.json')
    panel.register_guard(server)
    subprocess.run(['python3',str(root/'src/proxy_protection.py')],check=True)
    print('Guard готов: http://localhost:8150 через SSH-туннель. Первоначальный пароль совпадает с паролем GitDeck.')

if __name__=='__main__':main()
