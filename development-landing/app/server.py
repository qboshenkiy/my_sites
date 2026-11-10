import hashlib
import hmac
import html
import json
import os
import re
import secrets
import sqlite3
import sys
import time
from contextlib import contextmanager
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit
from urllib.request import Request, urlopen

import admin_ui
import chats
import content

DATA = Path(os.environ.get('JOB_DATA', '/data'))
DIST = Path(__file__).resolve().parents[1] / 'dist'
ORIGIN = os.environ.get('JOB_ORIGIN', 'https://job.vano.sbena.net')
SECURE = '; Secure' if ORIGIN.startswith('https:') else ''
PHONE = re.compile(r'\+[1-9][0-9]{6,14}')
HANDLE = re.compile(r'[A-Za-z0-9_]{5,32}')
TOKEN = re.compile(r'[0-9]{5,20}:[A-Za-z0-9_-]{20,100}')
MIME = {'.html': 'text/html', '.css': 'text/css', '.js': 'text/javascript',
        '.svg': 'image/svg+xml', '.xml': 'application/xml', '.txt': 'text/plain'}
esc = html.escape


@contextmanager
def db():
    connection = sqlite3.connect(DATA / 'job.sqlite', timeout=10)
    connection.row_factory = sqlite3.Row
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def setting(conn, key):
    row = conn.execute('SELECT value FROM settings WHERE key=?', (key,)).fetchone()
    return row[0] if row else ''


def put(conn, key, value):
    conn.execute('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value', (key, str(value)))


def digest(password, salt):
    return hashlib.scrypt(password.encode(), salt=salt, n=16384, r=8, p=1).hex()


def password_hash(password):
    salt = secrets.token_bytes(16)
    return salt.hex() + ':' + digest(password, salt)


def initialize():
    DATA.mkdir(parents=True, exist_ok=True)
    with db() as conn:
        conn.execute('PRAGMA journal_mode=WAL')
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS leads (
                id INTEGER PRIMARY KEY, source TEXT, name TEXT, contact TEXT,
                body TEXT, created INTEGER, delivered INTEGER DEFAULT 0,
                update_id TEXT UNIQUE
            );
            CREATE TABLE IF NOT EXISTS sessions (id TEXT PRIMARY KEY, expires INTEGER);
            CREATE TABLE IF NOT EXISTS limits (bucket TEXT PRIMARY KEY, count INTEGER, until INTEGER);
        """)
        chats.initialize(conn)
        content.initialize(conn)
        if not setting(conn, 'password'):
            bootstrap = DATA / 'bootstrap'
            if bootstrap.exists():
                put(conn, 'password', password_hash(bootstrap.read_text().strip()))
                bootstrap.unlink()


def rate_limit(bucket, limit, seconds, connection=None):
    if connection is None:
        with db() as conn:
            return rate_limit(bucket, limit, seconds, conn)
    now = int(time.time())
    connection.execute('DELETE FROM limits WHERE until <= ?', (now,))
    connection.execute('INSERT INTO limits VALUES (?,1,?) ON CONFLICT(bucket) DO UPDATE SET count=count+1', (bucket, now+seconds))
    return connection.execute('SELECT count FROM limits WHERE bucket=?', (bucket,)).fetchone()[0] <= limit


def telegram(token, method, **payload):
    try:
        req = Request('https://api.telegram.org/bot' + token + '/' + method,
                      json.dumps(payload).encode(), {'Content-Type': 'application/json'})
        with urlopen(req, timeout=30) as response:
            result = json.load(response)
        if result.get('ok'):
            return result['result']
    except (OSError, ValueError, KeyError):
        pass
    raise ValueError('Telegram не ответил или отклонил запрос. Проверьте токен и настройки бота.')


def add_lead(conn, source, name, contact, body, update_id=None):
    cur = conn.execute('INSERT OR IGNORE INTO leads (source,name,contact,body,created,update_id) VALUES (?,?,?,?,?,?)',
                       (source, name, contact, body, int(time.time()), update_id))
    return cur.lastrowid if cur.rowcount else None


def process_update(conn, token, update):
    msg = update.get('message', {})
    chat = msg.get('chat', {})
    body = msg.get('text', '').strip()
    if chat.get('type') != 'private' or not body:
        return None
    chat_id = str(chat['id'])
    command = body.split(maxsplit=1)
    if command[0] == '/bind':
        claim = setting(conn, 'claim').split(':', 1)
        if len(command) == 2 and len(claim) == 2 and int(claim[1]) > time.time() and hmac.compare_digest(command[1], claim[0]):
            put(conn, 'owner', chat_id)
            put(conn, 'claim', '')
            return chat_id, 'Готово. Откройте /leads для заявок или /chats для диалогов.'
        return chat_id, 'Код не подошёл. Получите новый в админке.'
    bot_id = token.split(':', 1)[0]
    if chat_id == setting(conn, 'owner'):
        return chat_id, chats.owner_command(conn, bot_id, body)
    if command[0] == '/start':
        return chat_id, 'Привет! Напишите одним сообщением, что хотите сделать. Укажите, как с вами связаться, если удобнее ответить вне Telegram.'
    if body.startswith('/'):
        return chat_id, 'Опишите задачу обычным сообщением.'
    if not rate_limit('bot:' + chat_id, 20, 600, conn):
        return None
    person = msg.get('from', {})
    username = person.get('username')
    name = ' '.join(person.get(key, '') for key in ('first_name', 'last_name')).strip()[:100]
    contact = '@' + username if username else 'tg://user?id=' + chat_id
    update_key = bot_id + ':' + str(update['update_id'])
    _, first_message = chats.receive(conn, bot_id, chat_id, name or 'Клиент', contact, body[:2000], update_key)
    if first_message:
        lead_id = add_lead(conn, 'Telegram', name, contact, body[:2000], update_key)
        if lead_id:
            return chat_id, f'Заявка №{lead_id} принята. Ответ придёт в этот чат.'
    return None


def bot_loop():
    while True:
        try:
            with db() as conn:
                token = setting(conn, 'token')
                owner = setting(conn, 'owner')
                offset = int(setting(conn, 'offset') or 0)
                queue = conn.execute('SELECT * FROM leads WHERE delivered=0 ORDER BY id LIMIT 10').fetchall() if owner and setting(conn, 'push_leads') == '1' else []
                outgoing = chats.pending(conn, token.split(':', 1)[0]) if token else []
            if not token:
                time.sleep(3)
                continue
            for message in outgoing:
                try:
                    telegram(token, 'sendMessage', chat_id=message['peer'], text=message['body'])
                except ValueError:
                    with db() as conn:
                        conn.execute('UPDATE messages SET retry_at=? WHERE id=?', (int(time.time()) + 60, message['id']))
                else:
                    with db() as conn:
                        conn.execute('UPDATE messages SET sent=1 WHERE id=?', (message['id'],))
            for lead in queue:
                try:
                    telegram(token, 'sendMessage', chat_id=owner,
                             text=f"Заявка №{lead['id']} · {lead['source']}\n{lead['name']}\n{lead['contact']}\n\n{lead['body']}",
                             link_preview_options={'is_disabled': True})
                except ValueError:
                    break
                with db() as conn:
                    conn.execute('UPDATE leads SET delivered=1 WHERE id=?', (lead['id'],))
            for update in telegram(token, 'getUpdates', offset=offset, timeout=5, allowed_updates=['message']):
                with db() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    if setting(conn, 'token') != token:
                        break
                    reply = process_update(conn, token, update)
                    put(conn, 'offset', update['update_id']+1)
                if reply:
                    try:
                        telegram(token, 'sendMessage', chat_id=reply[0], text=reply[1])
                    except ValueError:
                        pass
        except (ValueError, OSError, sqlite3.Error):
            time.sleep(5)


def document(title, content):
    return ('<!doctype html><html lang="ru"><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            '<meta name="robots" content="noindex"><title>' + esc(title) +
            '</title><link rel="icon" href="/signal.svg" type="image/svg+xml"><link rel="stylesheet" href="/style.css"><main class="shell admin">' + content + '</main></html>')


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *_):
        pass

    def respond(self, status, body='', mime='text/html', headers=None):
        if isinstance(body, str):
            body = body.encode()
        self.send_response(status)
        self.send_header('Content-Type', mime + '; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'same-origin')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Cache-Control', 'no-store' if urlsplit(self.path).path.startswith(('/admin', '/api/')) else 'no-cache')
        for key, value in (headers or {}).items():
            self.send_header(key, value)
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(body)

    def json(self, status, data):
        self.respond(status, json.dumps(data, ensure_ascii=False), 'application/json')

    def session(self):
        cookie = SimpleCookie(self.headers.get('Cookie', ''))
        value = cookie.get('job_session')
        if value:
            with db() as conn:
                row = conn.execute('SELECT id FROM sessions WHERE id=? AND expires>?', (value.value, int(time.time()))).fetchone()
            return row[0] if row else ''

    def redirect(self, target, **headers):
        self.respond(303, headers={'Location': target, **headers})

    def admin(self, session, message='', status=200, tab=None):
        if not session:
            return self.respond(status, document('Вход', '<h1>Вход</h1>' + (f'<p role="alert">{esc(message)}</p>' if message else '') +
                '<form method="post" action="/admin/login"><label>Пароль<input name="password" type="password" autocomplete="current-password" required></label><button class="button primary">Войти</button></form>'))
        query = parse_qs(urlsplit(self.path).query)
        tab = tab or query.get('tab', ['leads'])[0]
        if tab not in admin_ui.TABS:
            tab = 'leads'
        if query.get('saved') == ['1'] and not message:
            message = 'Изменения сохранены.'
        hidden = f'<input type="hidden" name="csrf" value="{esc(session)}">'
        with db() as conn:
            if tab == 'site':
                panel = admin_ui.site(conn, hidden)
            elif tab in ('service', 'example'):
                panel = admin_ui.catalog(conn, tab, hidden)
            elif tab == 'chats':
                chat = query.get('chat', [''])[0]
                panel = admin_ui.conversations(conn, setting(conn, 'token').split(':', 1)[0], hidden, chat)
            elif tab == 'settings':
                panel = self.settings_panel(conn, hidden)
            else:
                panel = admin_ui.leads(conn, hidden, query)
        self.respond(status, document('Админка · Разработка на заказ',
                                      admin_ui.shell(tab, hidden, message) + panel))

    def settings_panel(self, conn, hidden):
        values = {key: setting(conn, key) for key in ('whatsapp', 'personal', 'bot', 'owner', 'claim', 'token')}
        claim = values['claim'].split(':', 1)
        binding = 'Telegram подключён. Команды /leads и /chats открывают заявки и диалоги.' if values['owner'] else 'Привяжите Telegram, чтобы открыть заявки и диалоги в боте.'
        if len(claim) == 2 and int(claim[1]) > time.time():
            binding += f' Откройте бота @{values["bot"]} и отправьте /bind {claim[0]}. Код действует 15 минут.'
        token_status = 'Токен сохранён. Заполните поле только для замены.' if values['token'] else 'Вставьте токен отдельного бота из BotFather.'
        push_checked = ' checked' if setting(conn, 'push_leads') == '1' else ''
        return f"""
            <div class="admin-grid"><section class="card"><h2>Контакты</h2>
            <form method="post" action="/admin/settings">{hidden}
            <label>WhatsApp<input name="whatsapp" value="{esc(values['whatsapp'])}" placeholder="+996…" type="tel"></label>
            <label>Личный Telegram<input name="personal" value="{esc(values['personal'])}" placeholder="@username или +996…"></label>
            <label>Токен Telegram-бота<input name="token" type="password" autocomplete="new-password"></label><small>{token_status}</small>
            <label class="admin-check"><input type="checkbox" name="push_leads" value="1"{push_checked}> Присылать новые заявки автоматически</label>
            <button class="button primary">Сохранить</button></form>
            <p>{esc(binding)}</p><form method="post" action="/admin/bind">{hidden}<button class="button outline small">Получить код подключения</button></form></section>
            <section class="card"><h2>Пароль</h2><form method="post" action="/admin/password">{hidden}
            <label>Текущий пароль<input name="current" type="password" autocomplete="current-password" required></label>
            <label>Новый пароль<input name="password" type="password" autocomplete="new-password" minlength="14" maxlength="128" required></label>
            <button class="button outline">Сменить пароль</button></form></section></div>
        """

    def do_HEAD(self):
        self.do_GET()

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/health':
            return self.json(200, {'ok': True})
        if path == '/admin':
            return self.admin(self.session())
        if path in ('/', '/index.html'):
            with db() as conn:
                page = content.render((DIST / 'index.html').read_text(), conn, ORIGIN)
            return self.respond(200, page)
        if path == '/api/contacts':
            with db() as conn:
                wa, personal, bot = (setting(conn, k) for k in ('whatsapp', 'personal', 'bot'))
            return self.json(200, {'whatsapp': 'https://wa.me/' + wa[1:] if wa else '',
                                   'personal': 'https://t.me/' + personal if personal else '',
                                   'bot': 'https://t.me/' + bot if bot else ''})
        path = '/index.html' if path == '/' else path
        if not re.fullmatch(r'/(?:examples/)?[a-z0-9-]+\.(?:html|css|js|svg|xml|txt)', path):
            return self.respond(404, 'Страница не найдена.')
        file = DIST / path[1:]
        if not file.is_file():
            return self.respond(404, 'Страница не найдена.')
        self.respond(200, file.read_bytes(), MIME[file.suffix])

    def do_POST(self):
        path = urlsplit(self.path).path
        if self.headers.get('Origin') != ORIGIN:
            return self.json(403, {'error': 'Откройте форму на сайте.'})
        try:
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= 48000:
                raise ValueError()
            raw = self.rfile.read(length).decode()
            if path == '/api/leads':
                data = json.loads(raw)
                if not isinstance(data, dict):
                    raise ValueError()
                return self.submit(data)
            data = {k: v[0] for k, v in parse_qs(raw, keep_blank_values=True, max_num_fields=32).items()}
        except (ValueError, UnicodeError):
            return self.json(400, {'error': 'Некорректные данные.'})
        if path == '/admin/login':
            if not rate_limit('login:' + self.client_ip(), 7, 900):
                return self.admin('', 'Слишком много попыток. Попробуйте позже.', 429)
            if not self.check_password(data.get('password', '')):
                return self.admin('', 'Неверный пароль.', 401)
            key = secrets.token_urlsafe(32)
            with db() as conn:
                conn.execute('DELETE FROM sessions WHERE expires<=?', (int(time.time()),))
                conn.execute('INSERT INTO sessions VALUES (?,?)', (key, int(time.time())+28800))
            return self.redirect('/admin', **{'Set-Cookie': f'job_session={key}; Path=/admin; HttpOnly; SameSite=Strict; Max-Age=28800{SECURE}'})
        session = self.session()
        if not session or not hmac.compare_digest(session, data.get('csrf', '')):
            return self.respond(403, 'Войдите в админку заново.')
        tab = 'settings'
        try:
            if path == '/admin/site':
                tab = 'site'
                with db() as conn:
                    content.save_site(conn, data)
                return self.redirect('/admin?tab=site&saved=1')
            if path == '/admin/card':
                kind = data.get('kind', '')
                tab = kind if kind in ('service', 'example') else 'service'
                with db() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    content.save_record(conn, kind, data)
                return self.redirect('/admin?tab=' + tab + '&saved=1')
            if path == '/admin/lead':
                tab = 'leads'
                stage, lead_id = data.get('stage'), data.get('id')
                with db() as conn:
                    if stage not in admin_ui.STATUSES or not conn.execute('SELECT 1 FROM leads WHERE id=?', (lead_id,)).fetchone():
                        raise ValueError('Заявка или статус не найдены.')
                    conn.execute('INSERT INTO lead_status VALUES (?,?) ON CONFLICT(lead_id) DO UPDATE SET status=excluded.status',
                                 (lead_id, stage))
                return self.redirect('/admin?tab=leads&saved=1')
            if path == '/admin/reply':
                tab = 'chats'
                chat_id = data.get('chat', '')
                if not re.fullmatch(r'[0-9]{1,18}', chat_id):
                    raise ValueError('Диалог не найден.')
                with db() as conn:
                    conn.execute('BEGIN IMMEDIATE')
                    chats.reply(conn, setting(conn, 'token').split(':', 1)[0], chat_id, data.get('body', ''))
                return self.redirect('/admin?tab=chats&chat=' + chat_id)
            if path == '/admin/settings':
                return self.save_settings(session, data)
            if path == '/admin/bind':
                with db() as conn:
                    if not setting(conn, 'token'):
                        raise ValueError('Сначала сохраните токен бота.')
                    put(conn, 'claim', secrets.token_urlsafe(12) + ':' + str(int(time.time())+900))
                return self.admin(session, 'Код готов.', tab='settings')
            if path == '/admin/password':
                password = data.get('password', '')
                if not self.check_password(data.get('current', '')) or not 14 <= len(password) <= 128:
                    raise ValueError('Проверьте текущий пароль. Новый пароль должен содержать от 14 до 128 символов.')
                with db() as conn:
                    put(conn, 'password', password_hash(password))
                    conn.execute('DELETE FROM sessions')
                return self.redirect('/admin')
            if path == '/admin/logout':
                with db() as conn:
                    conn.execute('DELETE FROM sessions WHERE id=?', (session,))
                return self.redirect('/admin', **{'Set-Cookie': f'job_session=; Path=/admin; HttpOnly; SameSite=Strict; Max-Age=0{SECURE}'})
        except ValueError as error:
            return self.admin(session, str(error), 400, tab=tab)
        self.respond(404, 'Страница не найдена.')

    def client_ip(self):
        return self.headers.get('X-Real-IP', self.client_address[0])[:64]

    def check_password(self, password):
        if len(password) > 128:
            return False
        with db() as conn:
            saved = setting(conn, 'password')
        if not saved:
            return False
        salt, expected = saved.split(':')
        return hmac.compare_digest(digest(password, bytes.fromhex(salt)), expected)

    def submit(self, data):
        if not rate_limit('lead:' + self.client_ip(), 6, 900):
            return self.json(429, {'error': 'Слишком много заявок. Попробуйте позже.'})
        fields = [data.get(key, '') for key in ('name', 'contact', 'body')]
        if any(not isinstance(value, str) for value in fields):
            return self.json(400, {'error': 'Проверьте заполнение формы.'})
        name, contact, body = [value.strip() for value in fields]
        if not (0 < len(name) <= 100 and 3 <= len(contact) <= 120 and 5 <= len(body) <= 2400):
            return self.json(400, {'error': 'Укажите имя, контакт и опишите задачу.'})
        with db() as conn:
            lead_id = add_lead(conn, 'Сайт', name, contact, body)
        return self.json(201, {'id': lead_id})

    def save_settings(self, session, data):
        wa = re.sub(r'[ ()-]', '', data.get('whatsapp', '').strip())
        personal = data.get('personal', '').strip().removeprefix('@')
        token = data.get('token', '').strip()
        if wa and not PHONE.fullmatch(wa):
            raise ValueError('Укажите WhatsApp в международном формате, например +996…')
        if personal and not (PHONE.fullmatch(personal) or HANDLE.fullmatch(personal)):
            raise ValueError('Укажите личный Telegram как @username или номер с +.')
        bot = None
        if token:
            if not TOKEN.fullmatch(token):
                raise ValueError('Проверьте формат токена.')
            bot = telegram(token, 'getMe')
            if telegram(token, 'getWebhookInfo').get('url'):
                raise ValueError('У этого бота настроен webhook. Используйте отдельного бота для заявок.')
        with db() as conn:
            put(conn, 'push_leads', '1' if data.get('push_leads') == '1' else '0')
            put(conn, 'whatsapp', wa)
            put(conn, 'personal', personal)
            if bot and token != setting(conn, 'token'):
                for key, value in {'token': token, 'bot': bot['username'], 'owner': '', 'offset': 0, 'claim': ''}.items():
                    put(conn, key, value)
        return self.redirect('/admin?tab=settings&saved=1')


if __name__ == '__main__':
    if sys.argv[1:] == ['bot']:
        while not (DATA / 'job.sqlite').exists():
            time.sleep(1)
        bot_loop()
    else:
        initialize()
        ThreadingHTTPServer(('0.0.0.0', int(os.environ.get('PORT', '8080'))), Handler).serve_forever()
