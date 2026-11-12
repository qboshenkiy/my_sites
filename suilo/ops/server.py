"""Same-origin Telegram accounts and revisioned progress; no third-party service required."""
from contextlib import contextmanager, closing
import hashlib
import hmac
from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import secrets
import sys
import sqlite3
import time
from urllib.parse import parse_qsl, urlsplit

COOKIE = '__Host-suilo_session'
MAX_BODY = 2_000_000
SESSION_AGE = 30 * 86400


def verify_telegram(raw, token, now=None):
    now = int(time.time() if now is None else now)
    if not token or not isinstance(raw, str) or len(raw) > 16384:
        raise ValueError('Invalid Telegram data')
    pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True)
    fields = dict(pairs)
    if len(fields) != len(pairs):
        raise ValueError('Duplicate fields')
    received = fields.pop('hash', '')
    key = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    expected = hmac.new(key, '\n'.join(f'{k}={v}' for k, v in sorted(fields.items())).encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, received):
        raise ValueError('Invalid signature')
    stamp = int(fields.get('auth_date', '0'))
    if stamp < now - 3600 or stamp > now + 30:
        raise ValueError('Expired Telegram data')
    user = json.loads(fields.get('user', '{}'))
    if not isinstance(user, dict) or type(user.get('id')) is not int or not 0 < user['id'] < 2**53 or user.get('is_bot'):
        raise ValueError('Invalid user')
    return {'id': user['id'], 'name': str(user.get('first_name', ''))[:80], 'username': str(user.get('username', ''))[:40]}


def clean_progress(value):
    """Bound the document; strip device-only drafts, settings, and active learning queues."""
    if not isinstance(value, dict):
        raise ValueError('Progress must be an object')
    result = {}
    limits = {'completed': 1000, 'cards': 3000, 'personalWords': 500, 'activity': 50000, 'errors': 100}
    for field, limit in limits.items():
        default = [] if field in ('activity', 'errors') else {}
        data = value.get(field, default)
        if type(data) is not type(default) or len(data) > limit:
            raise ValueError('Invalid progress field')
        result[field] = data
    for field in ('completed', 'cards', 'personalWords'):
        for key, record in result[field].items():
            if not isinstance(key, str) or key in ('__proto__','constructor','prototype') or len(key)>200 or not isinstance(record, dict):
                raise ValueError('Invalid record')
            required = ('box','due','at') if field=='cards' else ('mistakes','xp','day','at') if field=='completed' else ('id','ru','ky','at')
            if any(k not in record for k in required):
                raise ValueError('Incomplete record')
            for k, v in record.items():
                if k in ('box','due','at','mistakes','xp') and (type(v) is not int or not 0 <= v <= 10**14):
                    raise ValueError('Invalid number')
                if k in ('id','ru','ky','day') and (not isinstance(v,str) or len(v)>1000):
                    raise ValueError('Invalid text')
    for field in ('activity','errors'):
        for record in result[field]:
            if not isinstance(record,dict) or not isinstance(record.get('id'),str) or len(record['id'])>200 or type(record.get('at')) is not int:
                raise ValueError('Invalid history')
            keys=('day','xp') if field=='activity' else ('prompt','given','expected')
            if any(k not in record for k in keys):
                raise ValueError('Incomplete history')
    vocabulary = value.get('vocabulary', {})
    if not isinstance(vocabulary, dict):
        raise ValueError('Invalid vocabulary')
    cards = vocabulary.get('cards', {})
    activity = vocabulary.get('activity', {})
    if not isinstance(cards, dict) or len(cards) > 1000 or not isinstance(activity, dict) or len(activity) > 36500:
        raise ValueError('Invalid vocabulary records')
    for word, card in cards.items():
        if not word.isdecimal() or not 1 <= int(word) <= 1000 or str(int(word)) != word or not isinstance(card, dict):
            raise ValueError('Invalid word')
        for key, maximum in (('box', 5), ('due', 10**14), ('at', 10**14), ('seen', 10**7), ('lapses', 10**7)):
            if type(card.get(key)) is not int or not 0 <= card[key] <= maximum:
                raise ValueError('Invalid card')
    if vocabulary and (vocabulary.get('dailyNew') not in (3,5,10,15) or not isinstance(vocabulary.get('topic'),str) or len(vocabulary['topic'])>200 or type(vocabulary.get('settingsAt')) is not int):
        raise ValueError('Invalid learning settings')
    for date, record in activity.items():
        if not isinstance(record,dict) or not isinstance(date,str) or len(date)!=10 or any(type(record.get(k)) is not int or not 0 <= record[k] <= 10**7 for k in ('introduced','answers')):
            raise ValueError('Invalid learning history')
    if vocabulary:
        result['vocabulary'] = {k: vocabulary[k] for k in ('cards', 'activity', 'dailyNew', 'topic', 'settingsAt') if k in vocabulary}
    return result


class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as db:
            db.executescript('''
                PRAGMA journal_mode=WAL;
                CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, username TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY, user_id INTEGER NOT NULL, expires INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS progress(user_id INTEGER PRIMARY KEY, revision INTEGER NOT NULL, document TEXT NOT NULL);
            ''')
        os.chmod(path, 0o600)

    @contextmanager
    def connect(self):
        connection = sqlite3.connect(self.path, timeout=10)
        connection.row_factory = sqlite3.Row
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def login(self, user):
        token = secrets.token_urlsafe(32)
        with self.connect() as db:
            db.execute('INSERT INTO users VALUES(?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,username=excluded.username',
                       (user['id'], user['name'], user['username']))
            db.execute('DELETE FROM sessions WHERE expires<=?', (int(time.time()),))
            db.execute('INSERT INTO sessions VALUES(?,?,?)', (self.digest(token), user['id'], int(time.time()) + SESSION_AGE))
            # Cap sessions per account without exposing other account identifiers.
            db.execute('DELETE FROM sessions WHERE user_id=? AND hash NOT IN (SELECT hash FROM sessions WHERE user_id=? ORDER BY expires DESC LIMIT 20)', (user['id'], user['id']))
        return token

    @staticmethod
    def digest(token):
        return hashlib.sha256(token.encode()).hexdigest()

    def user(self, token):
        with self.connect() as db:
            row = db.execute('SELECT users.* FROM sessions JOIN users ON users.id=sessions.user_id WHERE hash=? AND expires>?', (self.digest(token), int(time.time()))).fetchone()
        return dict(row) if row else None

    def get(self, user_id):
        with self.connect() as db:
            row = db.execute('SELECT revision,document FROM progress WHERE user_id=?', (user_id,)).fetchone()
        return {'revision': row['revision'], 'progress': json.loads(row['document'])} if row else {'revision': 0, 'progress': None}

    def put(self, user_id, revision, progress):
        document = json.dumps(clean_progress(progress), ensure_ascii=False, separators=(',', ':'), allow_nan=False)
        if len(document.encode()) > MAX_BODY:
            raise ValueError('Too much progress')
        with self.connect() as db:
            if revision == 0:
                changed = db.execute('INSERT OR IGNORE INTO progress VALUES(?,1,?)', (user_id, document)).rowcount
            else:
                changed = db.execute('UPDATE progress SET revision=revision+1,document=? WHERE user_id=? AND revision=?', (document, user_id, revision)).rowcount
        return bool(changed)


class Handler(BaseHTTPRequestHandler):
    protocol_version = 'HTTP/1.1'
    server_version = 'Suilo'
    sys_version = ''

    def setup(self):
        super().setup()
        self.connection.settimeout(15)

    def log_message(self, *_):
        # Caddy/Guard record metadata; never log signed initData, bodies, cookies or user names.
        pass

    def reply(self, code, data, cookie=None):
        body = json.dumps(data, ensure_ascii=False, separators=(',', ':')).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(body)))
        self.send_header('Cache-Control', 'no-store')
        self.send_header('X-Content-Type-Options', 'nosniff')
        if cookie:
            self.send_header('Set-Cookie', f'{COOKIE}={cookie}; Path=/; Max-Age={SESSION_AGE}; HttpOnly; Secure; SameSite=Lax')
        self.end_headers()
        self.wfile.write(body)

    def current_user(self):
        authorization = self.headers.get('Authorization', '')
        if authorization.startswith('Bearer '):
            token = authorization[7:]
            return self.server.store.user(token) if 20 <= len(token) <= 100 else None
        try:
            cookie = SimpleCookie(self.headers.get('Cookie', ''))
            token = cookie[COOKIE].value if COOKIE in cookie else ''
        except Exception:
            return None
        return self.server.store.user(token) if token else None

    def do_GET(self):
        path = urlsplit(self.path).path
        if path == '/healthz':
            return self.reply(200, {'ok': True})
        if path not in ('/api/me', '/api/progress'):
            return self.reply(404, {'error': 'not_found'})
        user = self.current_user()
        if not user:
            return self.reply(401, {'error': 'unauthorized'})
        return self.reply(200, {'user': user} if path == '/api/me' else self.server.store.get(user['id']))

    def do_POST(self):
        self.mutate()

    def do_PUT(self):
        self.mutate()

    def mutate(self):
        if self.headers.get('Origin') != self.server.origin or self.headers.get('X-Suilo-Request') != '1':
            self.close_connection = True
            return self.reply(403, {'error': 'origin'})
        try:
            if self.headers.get('Transfer-Encoding') or self.headers.get_content_type() != 'application/json':
                raise ValueError('Invalid request type')
            length = int(self.headers.get('Content-Length', '0'))
            if not 0 < length <= MAX_BODY:
                raise ValueError('Invalid size')
            body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError('Invalid number')))
            if not isinstance(body, dict):
                raise ValueError('Invalid object')
        except (ValueError, UnicodeError, OSError):
            self.close_connection = True
            return self.reply(400, {'error': 'invalid_request'})
        path = urlsplit(self.path).path
        if path == '/api/auth/telegram' and self.command == 'POST':
            if not self.server.token:
                return self.reply(503, {'error': 'telegram_not_configured'})
            try:
                user = verify_telegram(body.get('initData'), self.server.token)
            except (ValueError, TypeError, KeyError):
                return self.reply(401, {'error': 'invalid_telegram_data'})
            token = self.server.store.login(user)
            return self.reply(200, {'user': user, 'session': token}, token)
        user = self.current_user()
        if not user:
            return self.reply(401, {'error': 'unauthorized'})
        if path != '/api/progress' or self.command != 'PUT':
            return self.reply(404, {'error': 'not_found'})
        revision = body.get('revision')
        if type(revision) is not int or not 0 <= revision < 2**53:
            return self.reply(400, {'error': 'invalid_revision'})
        try:
            changed = self.server.store.put(user['id'], revision, body.get('progress'))
        except (ValueError, TypeError):
            return self.reply(400, {'error': 'invalid_progress'})
        return self.reply(200 if changed else 409, {'revision': revision + 1} if changed else {'error': 'conflict'})


def make_server(address, database, token, origin):
    server = ThreadingHTTPServer(address, Handler)
    server.daemon_threads = True
    server.store = Store(database)
    server.token = token
    server.origin = origin.rstrip('/')
    return server


def main():
    os.umask(0o077)
    origin = os.environ.get('APP_URL', 'https://suilo.vano.sbena.net').rstrip('/')
    target = urlsplit(origin)
    if target.scheme != 'https' or not target.hostname or target.path or target.username or target.query or target.fragment:
        raise SystemExit('APP_URL must be an HTTPS origin')
    if len(sys.argv)==2 and sys.argv[1]=='backup':
        destination=Path('/data/backups') / ('learning-'+time.strftime('%Y%m%d-%H%M%S')+'.sqlite')
        destination.parent.mkdir(mode=0o700,exist_ok=True)
        with closing(sqlite3.connect('file:/data/learning.sqlite?mode=ro',uri=True)) as source, closing(sqlite3.connect(destination)) as target:
            source.backup(target)
        destination.chmod(0o600)
        print('Резервная копия создана:',destination)
        return
    server = make_server(('0.0.0.0', 8081), os.environ.get('SUILO_DATABASE', '/data/learning.sqlite'), os.environ.get('TELEGRAM_BOT_TOKEN', ''), origin)
    print('Telegram accounts API is ready.', flush=True)
    server.serve_forever()


if __name__ == '__main__':
    main()
