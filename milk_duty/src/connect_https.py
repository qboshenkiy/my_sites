"""Attach only this app to an existing GitDeck Caddy proxy; never recreate other websites."""
import argparse
import importlib.util
import json
from pathlib import Path
import re
import subprocess
import sys


def route(source, host):
    marker='# MilkDuty HTTPS'
    pattern=re.escape(marker+' BEGIN')+r'.*?'+re.escape(marker+' END')
    without=re.sub(pattern,'',source,flags=re.S)
    if re.search(r'(?m)^\s*(?:https://)?'+re.escape(host)+r'\s*\{',without):
        raise ValueError('Этот домен уже занят другим маршрутом.')
    if re.search(r'(?m)^\s*reverse_proxy\s+(?:http://)?web:80(?:\s|$)',source):
        raise ValueError('Основной сайт использует неоднозначный адрес web:80. Настройте его стабильный alias через актуальный GitDeck. Пока используйте SSH-туннель.')
    block=marker+' BEGIN\n'+host+' {\n    encode gzip zstd\n    reverse_proxy milk-duty-web:8130\n}\n'+marker+' END'
    return re.sub(pattern,lambda _:block,source,flags=re.S) if marker+' BEGIN' in source else source.rstrip()+'\n\n'+block+'\n'


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('host')
    parser.add_argument('--proxy')
    args=parser.parse_args()
    if not re.fullmatch(r'[a-z0-9](?:[a-z0-9.-]{0,250}[a-z0-9])?',args.host) or '..' in args.host:
        raise SystemExit('Укажите домен без https:// и пути.')
    config_path=Path('/etc/gitdeck/config.json')
    module_path=Path('/opt/gitdeck/app.py')
    spec=importlib.util.spec_from_file_location('gitdeck',module_path)
    panel=importlib.util.module_from_spec(spec);spec.loader.exec_module(panel)
    config=panel.load_config(config_path)
    proxies=[p for p in config['projects'] if p['kind'] in ('marathon','pulse') and p['compose']=='compose.https.yaml']
    proxy=next((p for p in proxies if p['id']==args.proxy),None) if args.proxy else next((p for p in proxies if p['kind']=='marathon'), proxies[0] if proxies else None)
    if proxy is None:
        raise SystemExit('Не найден HTTPS-прокси. Панель доступна через SSH-туннель.')
    details=json.loads(panel.compose(proxy,['config','--format','json'],None))
    network=details.get('networks',{}).get('default',{}).get('name','')
    if not re.fullmatch(r'[A-Za-z0-9_.-]+',network):
        raise SystemExit('Не найдена Docker-сеть HTTPS-прокси.')
    target=Path(__file__).resolve().parents[1]
    caddy=Path(proxy['directory'])/'deploy'/'Caddyfile'
    overlay=target/'compose.gitdeck-https.yaml'
    if caddy.is_symlink() or overlay.is_symlink():
        raise SystemExit('Отказ: файлы конфигурации не должны быть символическими ссылками.')
    original=caddy.read_text()
    updated=route(original,args.host)
    old_overlay=overlay.read_bytes() if overlay.exists() else None
    new_overlay='services:\n  web:\n    networks:\n      default: {}\n      gitdeck_https:\n        aliases: [milk-duty-web]\nnetworks:\n  gitdeck_https:\n    external: true\n    name: '+network+'\n'
    def run_app():
        files=['docker','compose','-f','compose.yaml']
        if overlay.exists():files+=['-f',overlay.name]
        subprocess.run(files+['up','-d','--no-deps','--wait','--wait-timeout','120','web'],cwd=target,check=True,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        # Preserve the inode of the bind-mounted Caddyfile.
        caddy.write_text(updated)
        panel.compose(proxy,['exec','-T','proxy','caddy','validate','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],None)
        overlay.write_text(new_overlay)
        run_app()
        panel.compose(proxy,['exec','-T','proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],None)
    except Exception:
        caddy.write_text(original)
        if old_overlay is None:overlay.unlink(missing_ok=True)
        else:overlay.write_bytes(old_overlay)
        try:
            run_app()
            panel.compose(proxy,['exec','-T','proxy','caddy','reload','--config','/etc/caddy/Caddyfile','--adapter','caddyfile'],None)
        except Exception:
            print('Проверьте состояние Caddy; прежние файлы восстановлены.',file=sys.stderr)
        raise SystemExit('Не удалось подключить HTTPS. Используйте SSH-туннель и проверьте DNS/прокси.')
    print('HTTPS-маршрут создан: https://'+args.host+' . DNS должен указывать на этот сервер.')

if __name__=='__main__':main()
