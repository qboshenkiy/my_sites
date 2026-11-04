"""Atomic SSH country allowlist using RIPE NCC's country resource data."""
import argparse
import ipaddress
import json
import os
from pathlib import Path
import subprocess
import time
import urllib.request
from firewall_agent import atomic_json

STATE=Path('/var/lib/guard-firewall/ssh-country.json')
URL='https://stat.ripe.net/data/country-resource-list/data.json?resource=kg&v4_format=prefix'
TABLE='guard_ssh_country'
ADMIN=Path('/etc/guard-ssh-admin.json')

def admin_ips():
    try:values=json.loads(ADMIN.read_text()).get('admin_ips',[])
    except FileNotFoundError:return []
    if not isinstance(values,list) or len(values)>64:raise ValueError('Некорректные адреса администратора')
    result=[]
    for value in values:
        ip=ipaddress.ip_address(value)
        if not ip.is_global:raise ValueError('Нужен публичный IP администратора')
        result.append(str(ip))
    return sorted(set(result))


def networks(resources):
    result={}
    for version,key in ((4,'ipv4'),(6,'ipv6')):
        values=resources.get(key,[])
        if not (1<=len(values)<=10000):raise ValueError('Пустой или слишком большой список адресов страны')
        ns=[ipaddress.ip_network(v) for v in values]
        if any(n.version!=version or n.prefixlen<(8 if version==4 else 16) or not n.is_global for n in ns):raise ValueError('Некорректные диапазоны страны')
        result[key]=[str(n) for n in ipaddress.collapse_addresses(ns)]
    if len(result['ipv4'])<20:raise ValueError('Неполный список IPv4 Кыргызстана')
    return result


def rules(data,replace=False):
    ns=networks(data['resources']);ports=data['ports']
    if not ports or any(type(p)!=int or not 1<=p<=65535 for p in ports):raise ValueError('Некорректные SSH-порты')
    lines=[f'delete table inet {TABLE}'] if replace else []
    lines += [f'table inet {TABLE} {{',' comment "Guard SSH: Kyrgyzstan addresses only"']
    for version,key in ((4,'ipv4'),(6,'ipv6')):
        lines += [f' set kg{version} {{',f' type ipv{version}_addr; flags interval;',' elements = { '+', '.join(ns[key])+' }',' }']
    admins=data.get('admin_ips',[])
    if len(admins)>64:raise ValueError('Слишком много исключений SSH')
    for version in (4,6):
        ips=[str(ipaddress.ip_address(ip)) for ip in admins if ipaddress.ip_address(ip).version==version]
        lines += [f' set admin{version} {{',f' type ipv{version}_addr;']
        if ips:lines.append(' elements = { '+', '.join(ips)+' }')
        lines.append(' }')
    dports='{ '+', '.join(map(str,sorted(set(ports))))+' }'
    lines += [' chain input {',' type filter hook input priority -190; policy accept;',' iifname "lo" return',f' tcp dport {dports} ip saddr @admin4 return',f' tcp dport {dports} ip6 saddr @admin6 return',f' tcp dport {dports} ip saddr != @kg4 counter drop',f' tcp dport {dports} ip6 saddr != @kg6 counter drop',' }','}']
    return '\n'.join(lines)+'\n'


def apply(data):
    exists=subprocess.run(['nft','list','table','inet',TABLE],capture_output=True).returncode==0
    script=rules(data,exists)
    subprocess.run(['nft','--check','-f','-'],input=script,text=True,check=True,capture_output=True)
    subprocess.run(['nft','-f','-'],input=script,text=True,check=True,capture_output=True)


def refresh():
    request=urllib.request.Request(URL,headers={'User-Agent':'Guard-SSH-Country/1.0'})
    with urllib.request.urlopen(request,timeout=25) as response:
        raw=response.read(2_000_001)
    if len(raw)>2_000_000:raise ValueError('Слишком большой ответ базы страны')
    payload=json.loads(raw)
    if payload.get('status')!='ok' or payload.get('data_call_name')!='country-resource-list':raise ValueError('Некорректная база страны')
    ns=networks(payload['data']['resources'])
    configured=subprocess.check_output(['/usr/sbin/sshd','-T'],text=True)
    ports=sorted({22,*[int(line.split()[1]) for line in configured.splitlines() if line.startswith('port ')]})
    data={'enabled':True,'country':'KG','source':URL,'updated_at':time.time(),'resources':ns,'admin_ips':admin_ips(),'ports':ports,'ipv4_prefixes':len(ns['ipv4']),'ipv6_prefixes':len(ns['ipv6'])}
    peer=os.getenv('SSH_CONNECTION','').split()
    if peer:
        address=ipaddress.ip_address(peer[0]);allowed=str(address) in data['admin_ips'] or any(address in ipaddress.ip_network(n) for n in ns['ipv4']+ns['ipv6'])
        if not allowed:raise ValueError('Текущий SSH-адрес не входит в Кыргызстан: правило не применено во избежание потери доступа')
    apply(data);atomic_json(STATE,data)
    print('SSH KG allowlist active:',len(ns['ipv4']),'IPv4,',len(ns['ipv6']),'IPv6 prefixes; ports',ports)


def install():
    source=Path(__file__).resolve()
    unit=f'''[Unit]
Description=Guard SSH Kyrgyzstan allowlist
After=nftables.service network-pre.target
Before=ssh.service ssh.socket
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {source} --restore
RemainAfterExit=yes
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=yes
[Install]
WantedBy=multi-user.target
'''
    Path('/etc/systemd/system/guard-ssh-country.service').write_text(unit)
    Path('/etc/systemd/system/guard-ssh-country-update.service').write_text(f'''[Unit]
Description=Refresh Guard Kyrgyzstan SSH address database
After=network-online.target
Wants=network-online.target
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {source} --refresh
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/guard-firewall
''')
    Path('/etc/systemd/system/guard-ssh-country-update.timer').write_text('''[Unit]
Description=Daily Kyrgyzstan SSH allowlist refresh
[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true
[Install]
WantedBy=timers.target
''')
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','guard-ssh-country.service','guard-ssh-country-update.timer'],check=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--restore',action='store_true');parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    if args.restore:
        data=json.loads(STATE.read_text());data['admin_ips']=admin_ips();apply(data)
    else:
        refresh()
        if not args.refresh:install()

if __name__=='__main__':main()
