"""Shared sliding HTTP window and bounded scanner bans before any application."""
import collections
import http.server
import ipaddress
import json
import math
import os
from pathlib import Path
import queue
import socketserver
import threading
import time
from urllib.parse import urlsplit, unquote
from firewall_agent import canonical
from ip_activity import PROBE
import network_control

LIMIT = 30
WINDOW = 10
MAX_IPS = 50000


class Gate:
    def __init__(self, ban=None, protected=None, clock=time.monotonic):
        self.clock=clock;self.ban=ban or (lambda ip: None)
        self.protected=protected or (lambda: set())
        self.clients=collections.OrderedDict();self.lock=threading.Lock()

    def check(self, raw_ip, uri='/'):
        ip=canonical(raw_ip)
        if not ipaddress.ip_address(ip).is_global:return 204,0
        now=self.clock();should_ban=False
        with self.lock:
            row=self.clients.pop(ip,None)
            if row is None:row={'times':collections.deque(maxlen=31),'probes':{},'blocked_until':0}
            self.clients[ip]=row
            if len(self.clients)>MAX_IPS:self.clients.popitem(last=False)
            if row['blocked_until']>now:return 429,math.ceil(row['blocked_until']-now)
            stamps=row['times']
            while stamps and stamps[0]<=now-WINDOW:stamps.popleft()
            stamps.append(now)
            probes=row['probes'];path=unquote(unquote(urlsplit(uri).path))[:800]
            for p,t in list(probes.items()):
                if t<=now-60:del probes[p]
            if PROBE.search(path) and len(probes)<10:probes[path]=now
            if (len(probes)>=5 or len(stamps)>LIMIT) and ip not in self.protected():
                row['blocked_until']=now+300;should_ban=True;status,retry=429,300
            elif len(stamps)>LIMIT:status,retry=429,max(1,math.ceil(stamps[0]+WINDOW-now))
            else:status,retry=204,0
        if should_ban:self.ban(ip)
        return status,retry


class Handler(http.server.BaseHTTPRequestHandler):
    protocol_version='HTTP/1.1'
    def log_message(self,*args):pass
    def do_GET(self):
        self.connection.settimeout(3)
        try:
            if urlsplit(self.path).path!='/check':raise ValueError('Invalid endpoint')
            status,retry=self.server.gate.check(self.headers.get('X-Guard-IP',''),self.headers.get('X-Forwarded-Uri','/'))
        except (ValueError,TypeError):status,retry=400,0
        body=b'' if status==204 else json.dumps({'error':'Too many requests. Please wait.' if status==429 else 'Request blocked by server protection.'}).encode()
        self.send_response(status);self.send_header('Content-Length',str(len(body)))
        self.send_header('Cache-Control','no-store');self.send_header('Content-Type','application/json')
        if retry:self.send_header('Retry-After',str(retry))
        self.send_header('Connection','close');self.close_connection=True
        self.end_headers()
        if body:self.wfile.write(body)


class Server(socketserver.UnixStreamServer):
    request_queue_size=128
    def get_request(self):
        connection,address=super().get_request();connection.settimeout(3);return connection,address


def main():
    config=json.loads(Path('/etc/guard-request-gate.json').read_text())
    path=Path(config['socket']);path.unlink(missing_ok=True)
    pending=queue.Queue(maxsize=256)
    protected=set();last_refresh=0
    def protect():
        nonlocal protected,last_refresh
        if time.monotonic()-last_refresh>30:
            try:protected=set(json.loads(Path('/etc/guard-firewall.json').read_text()).get('protected_ips',[]));last_refresh=time.monotonic()
            except (OSError,ValueError):pass
        return protected
    def ban(ip):
        try:pending.put_nowait(ip)
        except queue.Full:print('Guard automatic block queue full; HTTP denial remains active',flush=True)
    def worker():
        while True:
            ip=pending.get()
            for attempt in range(3):
                try:
                    network_control.request('block',ip=ip,requester='127.0.0.1',duration=300)
                    print(json.dumps({'event':'automatic_ip_block','ip':ip,'duration':300}),flush=True);break
                except (ValueError,OSError):
                    if attempt==2:print(json.dumps({'event':'automatic_ip_block_failed','ip':ip}),flush=True)
                    else:time.sleep(1)
            pending.task_done()
    threading.Thread(target=worker,daemon=True).start()
    with Server(str(path),Handler) as server:
        os.chmod(path,0o600);server.gate=Gate(ban,protect)
        print('Guard HTTP protection ready: 30 requests / 10 seconds / IP across all sites',flush=True)
        server.serve_forever()

if __name__=='__main__':main()
