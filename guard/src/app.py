"""Guard: authenticated security and first-party Telegram bot console."""
import argparse
import collections
import contextlib
import getpass
import hashlib
import hmac
import http.cookies
import http.server
import json
import os
from pathlib import Path
import secrets
import sqlite3
import threading
import time
import urllib.parse
import monitor
import alerts as notifications

ROOT=Path(__file__).resolve().parents[1]
DATA=Path(os.getenv('DATA_DIR','/data'))
HOST=os.getenv('GUARD_DOMAIN','guard.vano.sbena.net')


@contextlib.contextmanager
def database():
    DATA.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA/'guard.sqlite',timeout=10)
    db.row_factory=sqlite3.Row
    try:
        db.executescript('CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,csrf TEXT,expires REAL); CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY,ip TEXT,action TEXT,target TEXT,created REAL); CREATE TABLE IF NOT EXISTS attempts(ip TEXT,created REAL);')
        with db:yield db
    finally:db.close()


def digest(password,salt):
    return hashlib.scrypt(password.encode(),salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()


def set_password(value):
    if not 12<=len(value)<=200:raise ValueError('Пароль должен содержать 12–200 символов')
    DATA.mkdir(parents=True,exist_ok=True)
    salt=secrets.token_hex(16);p=DATA/'password.json'
    p.write_text(json.dumps({'salt':salt,'digest':digest(value,salt)}));p.chmod(0o600)
    with database() as db:db.execute('DELETE FROM sessions')


class Cache:
    def __init__(self):self.lock=threading.Lock();self.data={}
    def get(self,key,fn):
        with self.lock:
            value=self.data.get(key)
            if value and value[0]>time.monotonic()-20:return value[1]
            result=fn();self.data[key]=(time.monotonic(),result);return result
CACHE=Cache()


class Handler(http.server.BaseHTTPRequestHandler):
    server_version='Guard'
    alerts_lock=threading.Lock()
    def alerts(self):
        with self.alerts_lock:
            if not hasattr(self.server,'alerts'):self.server.alerts=notifications.Service(database)
            return self.server.alerts
    def log_message(self,*args):pass
    def host_valid(self):
        host=self.headers.get('Host','')
        return host==HOST or host in ('127.0.0.1:8150','localhost:8150')
    def ip(self):
        # Caddy overwrites X-Forwarded-For; direct port is bound to host loopback only.
        return monitor.valid_ip(self.headers.get('X-Forwarded-For','').split(',')[0].strip()) or self.client_address[0]
    def send(self,status,value,cookie=None,content_type='application/json; charset=utf-8'):
        body=value if isinstance(value,bytes) else json.dumps(value,ensure_ascii=False).encode()
        self.send_response(status);self.send_header('Content-Type',content_type)
        self.send_header('Content-Length',str(len(body)));self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff');self.send_header('X-Frame-Options','DENY')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy',"default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'self'")
        if cookie:self.send_header('Set-Cookie',cookie)
        self.end_headers();self.wfile.write(body)
    def session(self):
        try:
            c=http.cookies.SimpleCookie(self.headers.get('Cookie',''));token=c['guard'].value
            with database() as db:
                db.execute('DELETE FROM sessions WHERE expires<?',(time.time(),))
                return db.execute('SELECT * FROM sessions WHERE hash=?',(hashlib.sha256(token.encode()).hexdigest(),)).fetchone()
        except (KeyError,http.cookies.CookieError):return None
    def audit(self,action,target=''):
        with database() as db:
            db.execute('INSERT INTO audit(ip,action,target,created) VALUES(?,?,?,?)',(self.ip(),action,str(target)[:120],time.time()))
            db.execute('DELETE FROM audit WHERE created<?',(time.time()-90*86400,))
    def do_GET(self):
        if not self.host_valid():return self.send(403,{'error':'Недопустимый адрес'})
        url=urllib.parse.urlsplit(self.path)
        files={'/favicon.svg':('favicon.svg','image/svg+xml'),'/favicon.ico':('favicon.svg','image/svg+xml'),'/':('index.html','text/html; charset=utf-8'),'/app.js':('app.js','text/javascript; charset=utf-8'),'/style.css':('style.css','text/css; charset=utf-8')}
        if url.path in files:
            file,kind=files[url.path];return self.send(200,(ROOT/'web'/file).read_bytes(),content_type=kind)
        if url.path=='/health':return self.send(200,{'ok':True,'version':'1.0.0'})
        session=self.session()
        if not session:return self.send(401,{'error':'Войдите как администратор'})
        query=urllib.parse.parse_qs(url.query)
        try:
            if url.path=='/api/alerts':return self.send(200,self.alerts().listing())
            if url.path=='/api/alerts/config':return self.send(200,self.alerts().public())
            if url.path=='/api/session':return self.send(200,{'csrf':session['csrf'],'domain':HOST})
            if url.path=='/api/security':
                period=int(query.get('period',['3600'])[0])
                if period not in (3600,86400):raise ValueError('Выберите час или сутки')
                def collect():
                    since=time.time()-period;result={'updated_at':time.time(),'period':period,'errors':{}}
                    try:result['ssh']=monitor.ssh(since)
                    except (OSError,ValueError,TimeoutError) as error:result['ssh']=[];result['errors']['ssh']=str(error)
                    try:result['http']=monitor.traffic(monitor.docker_api.logs(monitor.PROXY,since),since)
                    except (OSError,ValueError,TimeoutError) as error:result['http']={};result['errors']['http']=str(error)
                    return result
                return self.send(200,CACHE.get(('security',period),collect))
            if url.path=='/api/bots':return self.send(200,{'bots':monitor.bots()})
            if url.path=='/api/people':return self.send(200,monitor.bot_action(query.get('bot',[''])[0],'people'))
            if url.path=='/api/history':return self.send(200,monitor.bot_action(query.get('bot',[''])[0],'history',{'person':query.get('person',[''])[0]}))
            if url.path=='/api/audit':
                with database() as db:rows=[dict(r) for r in db.execute('SELECT ip,action,target,created FROM audit ORDER BY id DESC LIMIT 100')]
                return self.send(200,{'events':rows})
            return self.send(404,{'error':'Не найдено'})
        except (ValueError,OSError,TimeoutError):return self.send(503,{'error':'Не удалось загрузить данные. Проверьте состояние сервиса или обновление бота.'})
    def do_POST(self):
        if not self.host_valid():return self.send(403,{'error':'Недопустимый адрес'})
        scheme='https' if self.headers.get('X-Forwarded-Proto')=='https' else 'http'
        if self.headers.get('Origin')!=scheme+'://'+self.headers.get('Host',''):return self.send(403,{'error':'Недопустимый источник запроса'})
        try:
            length=int(self.headers.get('Content-Length','0'))
            if not 0<length<=16384:raise ValueError()
            data=json.loads(self.rfile.read(length))
            if not isinstance(data,dict):raise ValueError()
        except (ValueError,TypeError):return self.send(400,{'error':'Некорректный запрос'})
        if self.path=='/api/login':
            with database() as db:
                db.execute('DELETE FROM attempts WHERE created<?',(time.time()-300,))
                own=db.execute('SELECT count(*) FROM attempts WHERE ip=?',(self.ip(),)).fetchone()[0]
                total=db.execute('SELECT count(*) FROM attempts').fetchone()[0]
                if own>=5 or total>=30:return self.send(429,{'error':'Слишком много попыток. Подождите 5 минут.'})
                db.execute('INSERT INTO attempts VALUES(?,?)',(self.ip(),time.time()))
            password=data.get('password','')
            try:
                credentials=json.loads((DATA/'password.json').read_text())
                valid=isinstance(password,str) and len(password)<=200 and hmac.compare_digest(digest(password,credentials['salt']),credentials['digest'])
            except (OSError,ValueError,KeyError):valid=False
            if not valid:self.audit('login_failed');return self.send(401,{'error':'Неверный пароль'})
            sid=secrets.token_urlsafe(32);csrf=secrets.token_hex(24)
            with database() as db:db.execute('INSERT INTO sessions VALUES(?,?,?)',(hashlib.sha256(sid.encode()).hexdigest(),csrf,time.time()+28800))
            self.audit('login_success')
            return self.send(200,{'csrf':csrf},cookie='guard='+sid+'; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'+('; Secure' if scheme=='https' else ''))
        session=self.session()
        if not session or not hmac.compare_digest(str(data.get('csrf','')),session['csrf']):return self.send(403,{'error':'Сессия истекла. Войдите снова.'})
        try:
            if self.path=='/api/alerts/config':
                result=self.alerts().save(data);self.audit('alerts_config');return self.send(200,result)
            if self.path=='/api/alerts/pair':
                result=self.alerts().pair();self.audit('alerts_pair');return self.send(200,result)
            if self.path=='/api/alerts/test':
                self.alerts().deliver(test=True);self.audit('alerts_test');return self.send(200,{'ok':True})
            if self.path=='/api/alerts/read':
                self.alerts().acknowledge(data.get('id',0));return self.send(200,{'ok':True})
            if self.path=='/api/logout':
                with database() as db:db.execute('DELETE FROM sessions WHERE hash=?',(session['hash'],))
                return self.send(200,{'ok':True},cookie='guard=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0')
            if self.path=='/api/bot/action':
                bot=data.get('bot');action=data.get('action');person=str(data.get('person',''))
                if action in ('start','stop','restart'):result=monitor.bot_control(bot,action)
                elif action in ('block','unblock','send'):result=monitor.bot_action(bot,action,{'person':person,'text':data.get('text','')})
                else:raise ValueError('Выберите действие')
                self.audit('bot_'+action,str(bot)+':'+person)
                return self.send(200,result)
            return self.send(404,{'error':'Не найдено'})
        except ValueError as error:return self.send(400,{'error':str(error)})
        except (OSError,TimeoutError):return self.send(503,{'error':'Сервис временно недоступен'})


def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['serve','password'],default='serve',nargs='?');args=parser.parse_args()
    if args.command=='password':
        password=getpass.getpass('Новый пароль Guard (от 12 символов): ')
        if password!=getpass.getpass('Повторите пароль: '):raise SystemExit('Пароли не совпадают')
        set_password(password);print('Пароль сохранён.');return
    server=http.server.ThreadingHTTPServer(('0.0.0.0',8150),Handler)
    server.alerts=notifications.Service(database);server.alerts.start()
    (DATA/'guard.sqlite').chmod(0o600)
    try:server.serve_forever()
    finally:server.alerts.stop.set();server.server_close()
if __name__=='__main__':main()
