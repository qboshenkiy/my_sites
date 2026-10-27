"""Milk Duty: private admin website and Telegram worker, Python standard library only."""
import argparse
import datetime as dt
import getpass
import hashlib
import hmac
import http.cookies
import http.server
import json
import os
from pathlib import Path
import secrets
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from core import Store, Invalid

ROOT = Path(__file__).resolve().parents[1]


def password_hash(password):
    if not isinstance(password, str) or not 12 <= len(password) <= 200:
        raise Invalid('Пароль должен содержать от 12 до 200 символов.')
    salt = secrets.token_hex(16)
    return salt+':'+hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex()


def password_ok(password, value):
    try:
        salt, expected = value.split(':')
        return hmac.compare_digest(expected, hashlib.scrypt(password.encode(), salt=salt.encode(), n=16384, r=8, p=1).hex())
    except (ValueError, AttributeError, TypeError):
        return False


class TelegramError(Exception):
    def __init__(self, code=0, retry_after=0):
        self.code, self.retry_after = code, retry_after
        super().__init__('Telegram временно недоступен.' if code != 403 else 'Участник заблокировал бота. Попросите его открыть бота и нажать Старт.')


def telegram(token, method, args=None):
    request = urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,
                                     data=json.dumps(args or {}).encode(), headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            result = json.load(response)
    except urllib.error.HTTPError as error:
        try:
            data = json.load(error)
        except Exception:
            data = {}
        raise TelegramError(error.code, data.get('parameters',{}).get('retry_after',0)) from None
    except (OSError, ValueError):
        raise TelegramError() from None
    if not result.get('ok'):
        raise TelegramError(result.get('error_code',0))
    return result['result']


class Application:
    def __init__(self, store, transport=telegram):
        self.store, self.transport = store, transport
        self.lock = threading.RLock()
        self.stop = threading.Event()

    def configure_bot(self, token):
        if not isinstance(token, str) or len(token) > 200 or ':' not in token or any(c.isspace() for c in token):
            raise Invalid('Введите токен из BotFather.')
        bot = self.transport(token, 'getMe')
        if not bot.get('is_bot') or not bot.get('username'):
            raise Invalid('Telegram не подтвердил бота.')
        if self.transport(token, 'getWebhookInfo').get('url'):
            raise Invalid('У бота уже подключён webhook. Используйте отдельного бота без webhook.')
        with self.store.db() as db:
            self.store.put(db, 'bot_token', token)
            self.store.put(db, 'bot_username', bot['username'])
            self.store.put(db, 'bot_id', str(bot['id']))
            self.store.put(db, 'worker_error', '')

    def handle_update(self, token, update):
        message = update.get('message', {})
        chat, sender = message.get('chat', {}), message.get('from', {})
        if chat.get('type') != 'private' or chat.get('id') != sender.get('id') or sender.get('is_bot'):
            return
        text = message.get('text','').strip()
        if text.startswith('/start join_'):
            try:
                name = self.store.join(text[len('/start join_'):], chat['id'])
                reply = f'{name}, вы подключены! Здесь будут личные напоминания о дежурстве и покупке молока. Расписание и замены настраивает организатор.'
            except Invalid as error:
                reply = str(error)
        elif text in ('/start', '/help'):
            reply = 'Это бот дежурств и покупки молока. Для подключения попросите у организатора вашу личную ссылку из веб-панели.'
        else:
            return
        self.transport(token, 'sendMessage', {'chat_id': chat['id'], 'text': reply})

    def deliver(self, now=None):
        now = time.time() if now is None else now
        with self.lock, self.store.db() as db:
            cfg = self.store.settings(db)
            db.execute("UPDATE outbox SET status='expired',error='Время напоминания истекло' WHERE status IN ('pending','retry') AND expires<=?", (now,))
            if not cfg['enabled'] or not cfg.get('bot_token'):
                return
            rows = list(db.execute("SELECT o.*,p.chat_id FROM outbox o JOIN people p ON p.id=o.person WHERE o.status IN ('pending','retry') AND next_try<=? AND expires>? ORDER BY id LIMIT 10", (now,now)))
            for row in rows:
                try:
                    if not row['chat_id']:
                        raise TelegramError(403)
                    self.transport(cfg['bot_token'], 'sendMessage', {'chat_id':row['chat_id'], 'text':row['text']})
                    db.execute("UPDATE outbox SET status='sent',sent_at=?,error='' WHERE id=?", (now,row['id']))
                except TelegramError as error:
                    status = 'failed' if error.code in (400,401,403) else 'retry'
                    delay = max(30,min(900,30*2**min(row['attempts'],5)), min(3600,error.retry_after))
                    db.execute('UPDATE outbox SET status=?,attempts=attempts+1,next_try=?,error=? WHERE id=?', (status,now+delay,str(error),row['id']))
                    if error.code in (0,401,409,429):
                        break

    def worker(self):
        while not self.stop.is_set():
            try:
                with self.lock:
                    self.store.schedule()
                    self.deliver()
                    with self.store.db() as db:
                        cfg = self.store.settings(db)
                token = cfg.get('bot_token')
                if not token:
                    self.stop.wait(3)
                    continue
                offset_key = 'offset_'+cfg['bot_id']
                updates = self.transport(token, 'getUpdates', {'offset':cfg.get(offset_key,0), 'timeout':5, 'allowed_updates':['message']})
                with self.lock:
                    with self.store.db() as db:
                        if self.store.settings(db).get('bot_token') != token:
                            continue
                    for update in updates:
                        self.handle_update(token, update)
                        with self.store.db() as db:
                            self.store.put(db, offset_key, update['update_id']+1)
                    with self.store.db() as db:
                        self.store.put(db, 'worker_error', '')
            except Exception:
                # Never log Telegram request URLs: they contain the token.
                with self.store.db() as db:
                    self.store.put(db, 'worker_error', 'Нет связи с Telegram. Проверьте токен, интернет и отсутствие второго запущенного экземпляра бота.')
                self.stop.wait(5)

    def update_person(self, data):
        person_id = int(data['id'])
        with self.store.db() as db:
            person = db.execute('SELECT * FROM people WHERE id=?', (person_id,)).fetchone()
            if not person:
                raise Invalid('Участник не найден.')
            action = data.get('action')
            if action == 'invite':
                if person['chat_id']:
                    raise Invalid('Участник уже подключён.')
                db.execute('UPDATE people SET invite=?,invite_expires=? WHERE id=?', (secrets.token_urlsafe(24),time.time()+7*86400,person_id))
            elif action == 'rename':
                name = data.get('name','').strip()
                if not 1 <= len(name) <= 80:
                    raise Invalid('Имя: от 1 до 80 символов.')
                db.execute('UPDATE people SET name=? WHERE id=?', (name,person_id))
            elif action == 'active':
                active = bool(data.get('active'))
                cfg = self.store.settings(db)
                if not active and db.execute('SELECT 1 FROM duties WHERE person=? AND day>=? LIMIT 1', (person_id,self.store.today(cfg).isoformat())).fetchone():
                    raise Invalid('Сначала замените участника в уже закреплённых дежурствах. Они отмечены в расписании.')
                db.execute('UPDATE people SET active=? WHERE id=?', (active,person_id))
            else:
                raise Invalid('Неизвестное действие.')


class Handler(http.server.BaseHTTPRequestHandler):
    server_version = 'MilkDuty'
    def log_message(self, *_):
        pass

    @property
    def app(self):
        return self.server.app

    def send(self, status, value, content_type='application/json; charset=utf-8', cookie=None):
        raw = json.dumps(value,ensure_ascii=False).encode() if content_type.startswith('application/json') else value
        self.send_response(status)
        self.send_header('Content-Type', content_type)
        self.send_header('Content-Length', str(len(raw)))
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        self.send_header('Referrer-Policy','no-referrer')
        self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'")
        if cookie:
            self.send_header('Set-Cookie',cookie)
        self.end_headers()
        self.wfile.write(raw)

    def cookie(self, token='', clear=False):
        secure = os.environ.get('TRUST_PROXY')=='1' and self.headers.get('X-Forwarded-Proto')=='https'
        return f'duty_session={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={0 if clear else 604800}'+('; Secure' if secure else '')

    def session(self):
        try:
            cookies = http.cookies.SimpleCookie(self.headers.get('Cookie',''))
            value = cookies['duty_session'].value
        except (KeyError,http.cookies.CookieError):
            return None
        with self.app.store.db() as db:
            row = db.execute('SELECT * FROM sessions WHERE hash=? AND expires>?', (hashlib.sha256(value.encode()).hexdigest(),time.time())).fetchone()
            return dict(row) if row else None

    def do_GET(self):
        path = urllib.parse.urlsplit(self.path).path
        if path == '/health':
            return self.send(200,{'ok':True})
        if path in ('/','/app.js','/style.css','/icon.svg'):
            file = {'/':'index.html'}.get(path,path[1:])
            mime = {'index.html':'text/html; charset=utf-8','app.js':'text/javascript; charset=utf-8','style.css':'text/css; charset=utf-8','icon.svg':'image/svg+xml'}[file]
            return self.send(200,(ROOT/'web'/file).read_bytes(),mime)
        session = self.session()
        if path == '/api/session':
            with self.app.store.db() as db:
                configured = bool(self.app.store.settings(db).get('password_hash'))
            return self.send(200,{'authenticated':bool(session),'csrf':session['csrf'] if session else '', 'configured':configured})
        if not session:
            return self.send(401,{'error':'Войдите в панель.'})
        if path == '/api/state':
            return self.send(200,self.app.store.snapshot())
        return self.send(404,{'error':'Не найдено.'})

    def do_POST(self):
        path = urllib.parse.urlsplit(self.path).path
        origin = urllib.parse.urlsplit(self.headers.get('Origin',''))
        if origin.scheme not in ('http','https') or origin.netloc != self.headers.get('Host'):
            return self.send(403,{'error':'Откройте панель по её адресу и повторите.'})
        try:
            length = int(self.headers.get('Content-Length','0'))
            if not 0 < length <= 16384 or self.headers.get_content_type() != 'application/json':
                raise Invalid('Некорректный запрос.')
            data = json.loads(self.rfile.read(length))
            if not isinstance(data,dict):
                raise Invalid('Некорректный запрос.')
            if path == '/api/login':
                return self.login(data)
            session = self.session()
            if not session:
                return self.send(401,{'error':'Войдите в панель.'})
            if not hmac.compare_digest(session['csrf'],self.headers.get('X-CSRF-Token','')):
                return self.send(403,{'error':'Обновите страницу и повторите.'})
            with self.app.lock:
                return self.mutate(path,data,session)
        except (Invalid,ValueError,TypeError,KeyError):
            import sys
            error = sys.exception()
            return self.send(400,{'error':str(error) if isinstance(error,Invalid) else 'Проверьте заполненные поля.'})
        except TelegramError as error:
            return self.send(502,{'error':str(error)})
        except Exception:
            return self.send(500,{'error':'Не удалось сохранить. Повторите попытку.'})

    def login(self,data):
        ip, now = self.client_address[0], time.time()
        with self.app.store.db() as db:
            db.execute('BEGIN IMMEDIATE')
            attempt = db.execute('SELECT * FROM login_attempts WHERE ip=?',(ip,)).fetchone()
            if attempt and attempt['count'] >= 10 and now-attempt['last'] < 600:
                return self.send(429,{'error':'Слишком много попыток. Повторите через 10 минут.'})
            cfg = self.app.store.settings(db)
            if not password_ok(data.get('password'),cfg.get('password_hash','')):
                count = attempt['count']+1 if attempt and now-attempt['last'] < 600 else 1
                db.execute('INSERT OR REPLACE INTO login_attempts VALUES (?,?,?)',(ip,count,now))
                return self.send(401,{'error':'Неверный пароль.'})
            db.execute('DELETE FROM login_attempts WHERE ip=?',(ip,))
            db.execute('DELETE FROM sessions WHERE expires<=?',(now,))
            token, csrf = secrets.token_urlsafe(32),secrets.token_urlsafe(24)
            db.execute('INSERT INTO sessions VALUES (?,?,?)',(hashlib.sha256(token.encode()).hexdigest(),csrf,now+604800))
        return self.send(200,{'ok':True,'csrf':csrf},cookie=self.cookie(token))

    def mutate(self,path,data,session):
        store = self.app.store
        if path == '/api/settings':
            store.save_settings(data)
        elif path == '/api/people/add':
            store.add_person(data.get('name'))
        elif path == '/api/people/update':
            self.app.update_person(data)
        elif path == '/api/people/order':
            ids = data.get('ids')
            with store.db() as db:
                existing = [p[0] for p in db.execute('SELECT id FROM people')]
                if not isinstance(ids,list) or len(ids)!=len(existing) or set(ids)!=set(existing):
                    raise Invalid('Список участников изменился. Обновите страницу.')
                for pos, person_id in enumerate(ids):
                    db.execute('UPDATE people SET position=? WHERE id=?',(pos,person_id))
        elif path == '/api/replace':
            store.replace(data.get('day'),int(data['person']))
        elif path == '/api/bot':
            self.app.configure_bot(data.get('token'))
        elif path == '/api/test':
            with store.db() as db:
                cfg = store.settings(db)
                person = db.execute('SELECT * FROM people WHERE id=? AND chat_id IS NOT NULL',(data.get('person'),)).fetchone()
            if not person or not cfg.get('bot_token'):
                raise Invalid('Выберите подключённого участника.')
            self.app.transport(cfg['bot_token'],'sendMessage',{'chat_id':person['chat_id'],'text':'Тестовое сообщение: личные напоминания о дежурстве и молоке подключены.'})
        elif path == '/api/password':
            with store.db() as db:
                cfg = store.settings(db)
                if not password_ok(data.get('current'),cfg.get('password_hash','')):
                    raise Invalid('Текущий пароль неверен.')
                store.put(db,'password_hash',password_hash(data.get('password')))
                db.execute('DELETE FROM sessions')
            return self.send(200,{'ok':True},cookie=self.cookie(clear=True))
        elif path == '/api/logout':
            with store.db() as db:
                db.execute('DELETE FROM sessions WHERE hash=?',(session['hash'],))
            return self.send(200,{'ok':True},cookie=self.cookie(clear=True))
        else:
            return self.send(404,{'error':'Не найдено.'})
        return self.send(200,{'ok':True})


def main():
    os.umask(0o077)
    parser = argparse.ArgumentParser()
    parser.add_argument('command',choices=['serve','password'],nargs='?',default='serve')
    parser.add_argument('--bind',default=os.getenv('BIND','127.0.0.1'))
    parser.add_argument('--port',type=int,default=int(os.getenv('PORT','8130')))
    parser.add_argument('--data',default=os.getenv('DATA_DIR',str(ROOT/'data')))
    args = parser.parse_args()
    store = Store(Path(args.data)/'duty.sqlite')
    if args.command == 'password':
        password = getpass.getpass('Новый пароль панели (минимум 12 символов): ')
        if password != getpass.getpass('Повторите пароль: '):
            raise SystemExit('Пароли не совпадают.')
        with store.db() as db:
            store.put(db,'password_hash',password_hash(password))
            db.execute('DELETE FROM sessions')
        print('Пароль сохранён.')
        return
    initial = os.getenv('DUTY_ADMIN_PASSWORD')
    with store.db() as db:
        if initial and not store.settings(db).get('password_hash'):
            store.put(db,'password_hash',password_hash(initial))
    import fcntl
    worker_lock = (Path(args.data)/'worker.lock').open('a')
    try:
        fcntl.flock(worker_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        raise SystemExit('Для этой базы уже запущен бот. Остановите второй экземпляр.')
    app = Application(store)
    server = http.server.ThreadingHTTPServer((args.bind,args.port),Handler)
    server.app = app
    worker = threading.Thread(target=app.worker,daemon=True)
    worker.start()
    print(f'Milk Duty: http://{args.bind}:{args.port}',flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        app.stop.set()
        server.server_close()

if __name__ == '__main__':
    main()
