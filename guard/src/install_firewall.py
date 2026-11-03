"""Install the bounded host firewall service; run only on the server as root."""
import json
import os
from pathlib import Path
import subprocess
import ipaddress


def main():
    if os.geteuid()!=0:raise SystemExit('Требуются права root на сервере')
    config=Path('/etc/guard-firewall.json')
    old=json.loads(config.read_text()) if config.exists() else {}
    protected=set(old.get('protected_ips',[]));ssh=os.getenv('SSH_CONNECTION','').split()
    if ssh:protected.add(ssh[0])
    interfaces=json.loads(subprocess.check_output(['ip','-j','address','show'],text=True))
    for interface in interfaces:
        for address in interface.get('addr_info',[]):
            if address.get('scope')=='global':protected.add(address['local'])
    candidates=[]
    try:
        candidates.extend(line.split()[1] for line in Path('/etc/resolv.conf').read_text().splitlines() if line.strip().startswith('nameserver ') and len(line.split())>1)
    except OSError:pass
    try:candidates.extend(subprocess.check_output(['resolvectl','dns','--no-pager'],text=True,timeout=3,stderr=subprocess.DEVNULL).split())
    except (OSError,subprocess.SubprocessError):pass
    for candidate in candidates:
        try:protected.add(str(ipaddress.ip_address(candidate)))
        except ValueError:pass
    protected={str(ipaddress.ip_address(ip)) for ip in protected}
    config.write_text(json.dumps({'protected_ips':sorted(protected)}));config.chmod(0o600)
    for directory in ('/run/guard-firewall','/var/lib/guard-firewall'):
        p=Path(directory);p.mkdir(parents=True,exist_ok=True,mode=0o700);p.chmod(0o700)
    source=Path(__file__).with_name('firewall_agent.py').resolve()
    unit=f'''[Unit]
Description=Guard bounded IP firewall controller
After=network-pre.target nftables.service
Before=docker.service
[Service]
Type=simple
ExecStart=/usr/bin/python3 {source}
Restart=on-failure
RestartSec=3
RuntimeDirectory=guard-firewall
RuntimeDirectoryMode=0700
RuntimeDirectoryPreserve=yes
StateDirectory=guard-firewall
StateDirectoryMode=0700
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes
ReadWritePaths=/run/guard-firewall /var/lib/guard-firewall
[Install]
WantedBy=multi-user.target
'''
    Path('/etc/systemd/system/guard-firewall.service').write_text(unit)
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','guard-firewall'],check=True)
    subprocess.run(['systemctl','restart','guard-firewall'],check=True)
    root=Path(__file__).resolve().parents[1]
    overlay=root/'compose.gitdeck-guard.yaml'
    if overlay.exists() and 'x-guard-firewall' not in overlay.read_text():raise ValueError('Неизвестный файл compose.gitdeck-guard.yaml; конфигурация сохранена без изменений')
    overlay.write_text(json.dumps({'x-guard-firewall':True,'services':{'web':{'volumes':['/run/guard-firewall:/run/guard-firewall:ro']}}},indent=2)+'\n')
    print('Guard firewall installed; HTTP/S, SSH and Docker ports covered.')
if __name__=='__main__':main()
