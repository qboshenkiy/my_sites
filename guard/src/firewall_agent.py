"""Host-only bounded nftables controller. Exposes no shell or arbitrary command API."""
import argparse
import copy
import ipaddress
import json
import math
import os
from pathlib import Path
import socketserver
import subprocess
import tempfile
import threading
import time

TABLE='guard_protection'
DURATIONS=(900,3600,86400)


def canonical(value):
    if not isinstance(value,str) or '%' in value:raise ValueError('Укажите один корректный IP, без диапазона и порта')
    try:
        address=ipaddress.ip_address(value.strip())
        if isinstance(address,ipaddress.IPv6Address) and address.ipv4_mapped:address=address.ipv4_mapped
        return str(address)
    except ValueError:raise ValueError('Укажите один корректный IP, без диапазона и порта') from None


def atomic_json(path,data):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    with tempfile.NamedTemporaryFile(mode='w',dir=path.parent,delete=False,encoding='utf-8') as out:
        temporary=Path(out.name);os.chmod(temporary,0o600);json.dump(data,out);out.flush();os.fsync(out.fileno())
    try:os.replace(temporary,path)
    finally:temporary.unlink(missing_ok=True)


def rules(active,now,replace=False):
    lines=[f'delete table inet {TABLE}'] if replace else []
    lines += [f'table inet {TABLE} {{',' comment "Guard managed IP protection"']
    for version,name in [(4,'deny4'),(6,'deny6')]:
        elements=[]
        for ip,row in active.items():
            if ipaddress.ip_address(ip).version==version:
                remaining=max(1,math.ceil(row['expires']-now));elements.append(ip+' timeout '+str(remaining)+'s')
        lines += [f' set {name} {{',f'  type ipv{version}_addr','  flags timeout','  timeout 24h']
        if elements:lines.append('  elements = { '+', '.join(elements)+' }')
        lines.append(' }')
    for chain in ('input','forward'):
        lines += [f' chain {chain} {{',f'  type filter hook {chain} priority -200; policy accept;', '  ip saddr @deny4 counter drop','  ip6 saddr @deny6 counter drop',' }']
    lines.append('}')
    return '\n'.join(lines)+'\n'


class Controller:
    def __init__(self,state='/var/lib/guard-firewall/state.json',config='/etc/guard-firewall.json',runner=None):
        self.state=Path(state);self.config=Path(config);self.lock=threading.RLock();self.runner=runner or self.run
        try:self.entries=json.loads(self.state.read_text())
        except FileNotFoundError:self.entries={}
        if not isinstance(self.entries,dict):raise ValueError('Некорректное состояние сетевой защиты')
    def run(self,args,script=None):
        result=subprocess.run(['/usr/sbin/nft',*args],input=script,text=True,capture_output=True,timeout=8)
        if result.returncode:raise ValueError('Не удалось применить сетевое правило nftables')
        return result.stdout
    def protected(self):
        try:values=json.loads(self.config.read_text()).get('protected_ips',[])
        except (FileNotFoundError,ValueError):values=[]
        result=set()
        for value in values:
            try:result.add(canonical(value))
            except ValueError:continue
        return result
    def active(self):
        now=time.time();protected=self.protected();result={}
        for raw,row in self.entries.items():
            ip=canonical(raw)
            if ip in protected:continue
            if not ipaddress.ip_address(ip).is_global:continue
            if row.get('expires',0)>now:result[ip]=row
        return result
    def table(self):
        try:return json.loads(self.runner(['-j','list','table','inet',TABLE]))
        except ValueError:return None
    def members(self,data):
        result=set()
        def extract(value):
            if isinstance(value,str):
                try:result.add(canonical(value))
                except ValueError:pass
            elif isinstance(value,dict):
                if 'elem' in value:extract(value['elem'])
                elif 'val' in value:extract(value['val'])
        for row in (data or {}).get('nftables',[]):
            item=row.get('set',{})
            if item.get('name') in ('deny4','deny6'):
                for value in item.get('elem',[]):extract(value)
            item=row.get('element',{})
            if item.get('name') in ('deny4','deny6'):
                for value in item.get('elem',[]):extract(value)
        return result
    def apply(self,active,reset=False):
        current=self.table()
        if reset or current is None:
            self.runner(['-f','-'],rules(active,time.time(),replace=current is not None));return
        lines=[f'flush set inet {TABLE} deny4',f'flush set inet {TABLE} deny6']
        now=time.time()
        for ip,row in active.items():
            name='deny4' if ipaddress.ip_address(ip).version==4 else 'deny6'
            lines.append(f'add element inet {TABLE} {name} {{ {ip} timeout {max(1,math.ceil(row["expires"]-now))}s }}')
        self.runner(['-f','-'],'\n'.join(lines)+'\n')
    def status(self):
        with self.lock:
            active=self.active();data=self.table()
            if data is None or self.members(data)!=set(active):
                self.apply(active,reset=data is None);data=self.table()
            packets=bytes_=0
            for item in (data or {}).get('nftables',[]):
                for expr in item.get('rule',{}).get('expr',[]):
                    counter=expr.get('counter',{});packets+=counter.get('packets',0);bytes_+=counter.get('bytes',0)
            return {'ready':data is not None,'scope':'all_ports','blocked':[dict(ip=ip,**row) for ip,row in active.items()],'protected_ips':sorted(self.protected()),'dropped_packets':packets,'dropped_bytes':bytes_}
    def change(self,action,raw,requester,duration=3600):
        ip=canonical(raw);requester=canonical(requester)
        if action not in ('block','unblock'):raise ValueError('Неизвестное действие')
        with self.lock:
            if action=='block':
                if not ipaddress.ip_address(ip).is_global:raise ValueError('Внутренние, служебные и локальные адреса блокировать нельзя')
                if ip in self.protected() or ip==requester:raise ValueError('Этот адрес защищён: текущий администратор или сам сервер')
                if isinstance(duration,bool) or not isinstance(duration,int) or duration not in DURATIONS:raise ValueError('Выберите 15 минут, 1 час или 24 часа')
            old=copy.deepcopy(self.entries);updated=self.active()
            if action=='block':
                if ip not in updated and len(updated)>=256:raise ValueError('Достигнут предел 256 активных блокировок')
                updated[ip]={'created':time.time(),'expires':time.time()+duration}
            else:updated.pop(ip,None)
            try:
                self.apply(updated);atomic_json(self.state,updated);self.entries=updated
            except Exception:
                try:self.apply({k:v for k,v in old.items() if v.get('expires',0)>time.time()})
                except Exception:pass
                raise
            return self.status()


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(10)
        try:
            line=self.rfile.readline(4097)
            if len(line)>4096:raise ValueError('Слишком большой запрос')
            data=json.loads(line)
            if not isinstance(data,dict):raise ValueError('Некорректный запрос')
            action=data.get('action')
            if action=='status':result=self.server.controller.status()
            elif action in ('block','unblock'):result=self.server.controller.change(action,data.get('ip'),data.get('requester'),data.get('duration',3600))
            else:raise ValueError('Неизвестное действие')
            response={'ok':True,'result':result}
        except (ValueError,TypeError):response={'ok':False,'error':'Неверный адрес, защищённый IP, срок или параметры блокировки'}
        except Exception:response={'ok':False,'error':'Не удалось применить сетевое правило. Проверьте службу защиты.'}
        self.wfile.write(json.dumps(response).encode()+b'\n')


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--socket',default='/run/guard-firewall/api.sock');args=parser.parse_args()
    path=Path(args.socket);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    controller=Controller();controller.apply(controller.active(),reset=True)
    path.unlink(missing_ok=True)
    server=socketserver.ThreadingUnixStreamServer(str(path),Handler);server.daemon_threads=True;server.controller=controller;os.chmod(path,0o600)
    def reconcile():
        while True:
            time.sleep(30)
            try:controller.status()
            except Exception:print('Guard firewall reconciliation failed',flush=True)
    threading.Thread(target=reconcile,daemon=True).start()
    server.serve_forever()
if __name__=='__main__':main()
