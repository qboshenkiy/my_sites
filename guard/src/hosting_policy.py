"""Inbound hosting/VPN policy; data only, with bounded and validated updates."""
import argparse
import bisect
import ipaddress
import json
from pathlib import Path
import subprocess
import time
import urllib.request
from firewall_agent import atomic_json, canonical

STATE=Path('/var/lib/guard-firewall/hosting-policy.json')
EXCEPTIONS=Path('/var/lib/guard-firewall/hosting-exceptions.json')
PROTECTED=Path('/etc/guard-firewall.json')
TABLE='guard_hosting'
BASE='https://raw.githubusercontent.com/X4BNet/lists_vpn/main/output/datacenter/'
GOOGLE='https://www.gstatic.com/ipranges/cloud.json'
TELEGRAM=('149.154.160.0/20','91.108.4.0/22')
ATTRIBUTION='X4B (Mathew Heard), lists_vpn, MIT; IP address data powered by IPLocate.io. https://github.com/X4BNet/lists_vpn'


def read(path,default):
    try:return json.loads(path.read_text())
    except FileNotFoundError:return default


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Guard-Hosting-Policy/1.0'})
    with urllib.request.urlopen(req,timeout=30) as response:raw=response.read(8_000_001)
    if len(raw)>8_000_000:raise ValueError('Слишком большая база сетей')
    return raw.decode('utf-8')


def validate(values,version):
    if not isinstance(values,list) or not 1<=len(values)<=200000:raise ValueError('Пустая или слишком большая база сетей')
    nets=[ipaddress.ip_network(v) for v in values]
    if any(n.version!=version or not n.is_global or n.prefixlen<(8 if version==4 else 16) for n in nets):raise ValueError('Небезопасный диапазон в базе сетей')
    result=[];minimum=8 if version==4 else 16
    for net in ipaddress.collapse_addresses(nets):
        result.extend(str(n) for n in net.subnets(new_prefix=minimum)) if net.prefixlen<minimum else result.append(str(net))
    return result


def allowed_ips():
    ips=read(PROTECTED,{}).get('protected_ips',[])+read(EXCEPTIONS,{}).get('allowed_ips',[])
    return sorted({canonical(ip) for ip in ips})


def intervals(values):
    ns=sorted((int(ipaddress.ip_network(v).network_address),int(ipaddress.ip_network(v).broadcast_address)) for v in values)
    merged=[]
    for start,end in ns:
        if merged and start<=merged[-1][1]+1:merged[-1]=(merged[-1][0],max(end,merged[-1][1]))
        else:merged.append((start,end))
    return [a for a,b in merged],[b for a,b in merged]


class Registry:
    def __init__(self,state=STATE,exceptions=EXCEPTIONS,protected=PROTECTED):
        self.paths=(Path(state),Path(exceptions),Path(protected));self.checked=-100;self.stamp=None
        self.enabled=False;self.index={};self.allowed=set();self.allowed_nets=[ipaddress.ip_network(v) for v in TELEGRAM];self.summary={}
    def reload(self):
        if time.monotonic()-self.checked<2:return
        self.checked=time.monotonic()
        stamp=tuple(p.stat().st_mtime_ns if p.exists() else None for p in self.paths)
        if stamp==self.stamp:return
        data=read(self.paths[0],{});enabled=data.get('enabled',False)
        index={}
        if enabled:
            for version,key in ((4,'ipv4'),(6,'ipv6')):index[version]=intervals(data['resources'][key])
        exceptions=read(self.paths[1],{}).get('allowed_ips',[])
        protected=read(self.paths[2],{}).get('protected_ips',[])
        allowed={canonical(ip) for ip in exceptions+protected}
        self.index=index;self.enabled=enabled;self.allowed=allowed;self.stamp=stamp
        self.summary={k:v for k,v in data.items() if k!='resources'}
        self.summary['allowed_ips']=exceptions
    def contains(self,raw):
        self.reload()
        if not self.enabled:return False
        ip=ipaddress.ip_address(canonical(raw));starts,ends=self.index.get(ip.version,([],[]));i=bisect.bisect_right(starts,int(ip))-1
        return i>=0 and int(ip)<=ends[i]
    def blocked(self,raw):
        ip=ipaddress.ip_address(canonical(raw))
        return self.contains(str(ip)) and str(ip) not in self.allowed and not any(ip in n for n in self.allowed_nets)
    def public(self,ip=None):
        self.reload();result=dict(self.summary,enabled=self.enabled)
        if ip:result['inspected']={'ip':canonical(ip),'listed':self.contains(ip),'denied':self.blocked(ip)}
        return result


def rules(data,replace=False):
    lines=[f'delete table inet {TABLE}'] if replace else []
    lines += [f'table inet {TABLE} {{',' comment "Guard inbound hosting and VPN policy"']
    allowed=allowed_ips()
    for version,key in ((4,'ipv4'),(6,'ipv6')):
        ns=validate(data['resources'][key],version)
        lines += [f' set hosting{version} {{',f' type ipv{version}_addr; flags interval;',' elements = { '+', '.join(ns)+' }',' }']
        exceptions=[ip+'/'+str(ipaddress.ip_address(ip).max_prefixlen) for ip in allowed if ipaddress.ip_address(ip).version==version]+[n for n in TELEGRAM if ipaddress.ip_network(n).version==version]
        exceptions=[str(n) for n in ipaddress.collapse_addresses(ipaddress.ip_network(v) for v in exceptions)]
        lines += [f' set allow{version} {{',f' type ipv{version}_addr; flags interval;']
        if exceptions:lines.append(' elements = { '+', '.join(exceptions)+' }')
        lines.append(' }')
    for chain in ('input','forward'):
        lines += [f' chain {chain} {{',f' type filter hook {chain} priority -180; policy accept;',
                  ' ct direction reply return',' ct state related return',' ip saddr @allow4 return',' ip6 saddr @allow6 return',
                  ' tcp dport { 80, 443 } return',' udp dport 443 return',
                  ' ip saddr @hosting4 counter drop',' ip6 saddr @hosting6 counter drop',' }']
    return '\n'.join(lines+['}'])+'\n'


def apply(data):
    exists=subprocess.run(['nft','list','table','inet',TABLE],capture_output=True).returncode==0
    script=rules(data,exists)
    subprocess.run(['nft','--check','-f','-'],input=script,text=True,check=True,capture_output=True,timeout=30)
    subprocess.run(['nft','-f','-'],input=script,text=True,check=True,capture_output=True,timeout=30)


def allow_ip(raw):
    ip=canonical(raw)
    if not Registry().contains(ip):return
    data=read(EXCEPTIONS,{'allowed_ips':[]});old=list(data['allowed_ips'])
    if ip in old:return
    if len(old)>=4096:raise ValueError('Слишком много разрешённых адресов')
    data['allowed_ips']=sorted(set(old+[ip]));atomic_json(EXCEPTIONS,data)
    try:apply(read(STATE,{}))
    except Exception:
        atomic_json(EXCEPTIONS,{'allowed_ips':old});raise ValueError('Не удалось разрешить IP в правилах облачных сетей') from None


def refresh():
    resources={};sources=[]
    for version,key in ((4,'ipv4'),(6,'ipv6')):
        url=BASE+key+'.txt';text=fetch(url)
        resources[key]=validate([line.strip() for line in text.splitlines() if line.strip() and not line.startswith('#')],version);sources.append(url)
    google=json.loads(fetch(GOOGLE));prefixes=google.get('prefixes',[])
    if len(prefixes)<100:raise ValueError('Неполная база Google Cloud')
    for version,key,field in ((4,'ipv4','ipv4Prefix'),(6,'ipv6','ipv6Prefix')):
        resources[key]=validate(resources[key]+[p[field] for p in prefixes if field in p],version)
    if len(resources['ipv4'])<1000 or len(resources['ipv6'])<100:raise ValueError('Неполная база датацентров')
    old=read(STATE,{})
    for key in ('ipv4','ipv6'):
        if old.get('enabled') and len(resources[key])<len(old.get('resources',{}).get(key,[]))*.7:raise ValueError('База сетей резко уменьшилась; старое правило сохранено')
    data={'enabled':True,'mode':'datacenters_vpn','updated_at':time.time(),'sources':sources+[GOOGLE],
          'attribution':ATTRIBUTION,'ipv4_prefixes':len(resources['ipv4']),'ipv6_prefixes':len(resources['ipv6']),'resources':resources}
    apply(data);atomic_json(STATE,data)
    print('Hosting policy active:',data['ipv4_prefixes'],'IPv4 and',data['ipv6_prefixes'],'IPv6 prefixes')


def install():
    source=Path(__file__).resolve()
    for suffix,description,option in [('','Restore Guard hosting policy','--restore'),('-update','Refresh Guard hosting policy','--refresh')]:
        Path('/etc/systemd/system/guard-hosting'+suffix+'.service').write_text(f'''[Unit]
Description={description}
After=nftables.service network-online.target guard-firewall.service
{'Before=docker.service' if not suffix else ''}
[Service]
Type=oneshot
ExecStart=/usr/bin/python3 {source} {option}
RemainAfterExit={'yes' if not suffix else 'no'}
NoNewPrivileges=yes
CapabilityBoundingSet=CAP_NET_ADMIN
ProtectSystem=strict
ProtectHome=yes
ReadWritePaths=/var/lib/guard-firewall
[Install]
WantedBy=multi-user.target
''')
    Path('/etc/systemd/system/guard-hosting-update.timer').write_text('''[Unit]
Description=Daily Guard hosting database refresh
[Timer]
OnCalendar=daily
RandomizedDelaySec=1h
Persistent=true
[Install]
WantedBy=timers.target
''')
    subprocess.run(['systemctl','daemon-reload'],check=True)
    subprocess.run(['systemctl','enable','--now','guard-hosting','guard-hosting-update.timer'],check=True)


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--restore',action='store_true');parser.add_argument('--refresh',action='store_true');args=parser.parse_args()
    if args.restore:apply(read(STATE,{}))
    else:
        refresh()
        if not args.refresh:install()

if __name__=='__main__':main()
