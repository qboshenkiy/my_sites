"""Persistent weekday rotation and reminder outbox; all dates use the configured zone."""
import contextlib
import datetime as dt
import json
import secrets
import sqlite3
import time
from pathlib import Path
from zoneinfo import ZoneInfo

DEFAULTS = {'timezone': 'Asia/Bishkek', 'weekdays': [0, 1, 2, 3, 4], 'morning_time': '08:00',
            'eve_enabled': True, 'eve_time': '19:00', 'enabled': False,
            'start_date': (dt.datetime.now(ZoneInfo('Asia/Bishkek')).date()+dt.timedelta(days=1)).isoformat(),
            'message': 'Сегодня, {date}, ваша очередь дежурить и купить молоко. Спасибо!',
            'eve_message': 'Напоминаем: завтра, {date}, ваша очередь дежурить и купить молоко.'}

class Invalid(ValueError):
    pass

class Store:
    def __init__(self, path):
        self.path = str(path)
        Path(path).parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        with self.db() as db:
            db.executescript('''
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS config(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS people(id INTEGER PRIMARY KEY,name TEXT NOT NULL,position INTEGER NOT NULL,
              active INTEGER NOT NULL DEFAULT 1,chat_id INTEGER UNIQUE,invite TEXT UNIQUE,invite_expires INTEGER);
            CREATE TABLE IF NOT EXISTS duties(day TEXT PRIMARY KEY,planned INTEGER NOT NULL,person INTEGER NOT NULL,
              revision INTEGER NOT NULL DEFAULT 0,manual INTEGER NOT NULL DEFAULT 0);
            CREATE TABLE IF NOT EXISTS outbox(id INTEGER PRIMARY KEY,day TEXT NOT NULL,kind TEXT NOT NULL,
              revision INTEGER NOT NULL,person INTEGER NOT NULL,text TEXT NOT NULL,expires REAL NOT NULL,
              status TEXT NOT NULL DEFAULT 'pending',attempts INTEGER NOT NULL DEFAULT 0,
              next_try REAL NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT '',sent_at REAL,
              UNIQUE(day,kind,revision,person));
            CREATE TABLE IF NOT EXISTS sessions(hash TEXT PRIMARY KEY,csrf TEXT NOT NULL,expires REAL NOT NULL);
            CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT PRIMARY KEY,count INTEGER NOT NULL,last REAL NOT NULL);
            ''')
            for key, value in DEFAULTS.items():
                db.execute('INSERT OR IGNORE INTO config VALUES (?,?)', (key, json.dumps(value)))

    @contextlib.contextmanager
    def db(self):
        db = sqlite3.connect(self.path, timeout=15)
        db.row_factory = sqlite3.Row
        try:
            with db:
                yield db
        finally:
            db.close()

    def settings(self, db):
        return {r['key']: json.loads(r['value']) for r in db.execute('SELECT * FROM config')}

    def put(self, db, key, value):
        db.execute('INSERT OR REPLACE INTO config VALUES (?,?)', (key, json.dumps(value)))

    def today(self, cfg):
        return dt.datetime.now(ZoneInfo(cfg['timezone'])).date()

    def roster(self, db):
        return list(db.execute('SELECT * FROM people WHERE active=1 AND chat_id IS NOT NULL ORDER BY position,id'))

    def nominal(self, db, day, cfg):
        start = dt.date.fromisoformat(cfg['start_date'])
        if day < start or day.weekday() not in cfg['weekdays']:
            return None
        people = self.roster(db)
        if not people:
            return None
        # Full weeks plus at most six days: no dependence on how often the scheduler runs.
        days = (day-start).days
        count = (days//7)*len(cfg['weekdays'])
        count += sum((start+dt.timedelta(days=(days//7)*7+i)).weekday() in cfg['weekdays'] for i in range(days % 7))
        return people[count % len(people)]['id']

    def duty(self, db, day, cfg, persist=False):
        if day < dt.date.fromisoformat(cfg['start_date']) or day.weekday() not in cfg['weekdays']:
            return None
        row = db.execute('SELECT * FROM duties WHERE day=?', (day.isoformat(),)).fetchone()
        if row:
            return {**dict(row), 'fixed': True}
        person = self.nominal(db, day, cfg)
        if person is None:
            return None
        row = {'day': day.isoformat(), 'planned': person, 'person': person, 'revision': 0, 'manual': 0, 'fixed': False}
        if persist:
            db.execute('INSERT INTO duties(day,planned,person) VALUES (?,?,?)', (row['day'], person, person))
        return row

    def validate_settings(self, values):
        result = {}
        for key in ('timezone',):
            value = values.get(key)
            if not isinstance(value, str):
                raise Invalid('Выберите часовой пояс.')
            try:
                ZoneInfo(value)
            except Exception:
                raise Invalid('Неизвестный часовой пояс.')
            result[key] = value
        for key in ('morning_time', 'eve_time'):
            value = values.get(key, '')
            try:
                parsed = dt.time.fromisoformat(value)
                if parsed.second or parsed.microsecond or parsed.tzinfo or len(value) != 5:
                    raise ValueError()
            except (ValueError, TypeError):
                raise Invalid('Время указывается в формате ЧЧ:ММ.')
            result[key] = value
        weekdays = values.get('weekdays')
        if not isinstance(weekdays, list) or not weekdays or any(type(x) is not int or not 0 <= x <= 6 for x in weekdays):
            raise Invalid('Выберите хотя бы один день недели.')
        result['weekdays'] = sorted(set(weekdays))
        try:
            result['start_date'] = dt.date.fromisoformat(values.get('start_date', '')).isoformat()
        except (ValueError, TypeError):
            raise Invalid('Укажите дату начала очереди.')
        for key in ('eve_enabled', 'enabled'):
            if type(values.get(key)) is not bool:
                raise Invalid('Некорректный переключатель.')
            result[key] = values[key]
        for key in ('message', 'eve_message'):
            value = values.get(key, '')
            if not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise Invalid('Текст сообщения: от 1 до 2000 символов.')
            # Only these two literal substitutions are supported, not arbitrary format expressions.
            if '{' in value.replace('{name}', '').replace('{date}', '') or '}' in value.replace('{name}', '').replace('{date}', ''):
                raise Invalid('В тексте доступны только {name} и {date}.')
            result[key] = value.strip()
        return result

    def save_settings(self, values):
        result = self.validate_settings(values)
        with self.db() as db:
            old = self.settings(db)
            if result['enabled'] and (not old.get('bot_token') or not self.roster(db)):
                raise Invalid('Сначала подключите бота и хотя бы одного участника.')
            for key, value in result.items():
                self.put(db, key, value)
            # Rebuild undelivered reminders with new times/text. Already sent messages remain in history.
            db.execute("DELETE FROM outbox WHERE status IN ('pending','retry') AND kind IN ('morning','eve')")
            for row in db.execute("SELECT id,day FROM outbox WHERE status IN ('pending','retry')").fetchall():
                day = dt.date.fromisoformat(row['day'])
                if day < dt.date.fromisoformat(result['start_date']) or day.weekday() not in result['weekdays']:
                    db.execute("UPDATE outbox SET status='cancelled' WHERE id=?", (row['id'],))
        return result

    def add_person(self, name):
        if not isinstance(name, str) or not 1 <= len(name.strip()) <= 80:
            raise Invalid('Имя: от 1 до 80 символов.')
        with self.db() as db:
            if db.execute('SELECT count(*) FROM people').fetchone()[0] >= 200:
                raise Invalid('Достигнут лимит 200 участников.')
            token = secrets.token_urlsafe(24)
            row = db.execute('INSERT INTO people(name,position,invite,invite_expires) VALUES (?,(SELECT COALESCE(max(position),0)+1 FROM people),?,?)',
                             (name.strip(), token, time.time()+7*86400))
            return row.lastrowid

    def join(self, token, chat_id):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            person = db.execute('SELECT * FROM people WHERE invite=? AND invite_expires>?', (token, time.time())).fetchone()
            if not person or person['chat_id'] is not None:
                raise Invalid('Ссылка истекла или уже использована. Попросите новую у организатора.')
            if db.execute('SELECT 1 FROM people WHERE chat_id=?', (chat_id,)).fetchone():
                raise Invalid('Этот Telegram уже подключён к очереди.')
            db.execute('UPDATE people SET chat_id=?,invite=NULL,invite_expires=NULL WHERE id=?', (chat_id, person['id']))
            return person['name']

    def enqueue(self, db, duty, kind, person, text, expires):
        db.execute('INSERT OR IGNORE INTO outbox(day,kind,revision,person,text,expires) VALUES (?,?,?,?,?,?)',
                   (duty['day'], kind, duty['revision'], person, text, expires))

    def replace(self, day_string, person_id):
        try:
            day = dt.date.fromisoformat(day_string)
        except (ValueError, TypeError):
            raise Invalid('Укажите дату замены.')
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            cfg = self.settings(db)
            if day < self.today(cfg) or day.weekday() not in cfg['weekdays']:
                raise Invalid('Выберите будущий рабочий день или сегодня.')
            person = db.execute('SELECT * FROM people WHERE id=? AND active=1 AND chat_id IS NOT NULL', (person_id,)).fetchone()
            duty = self.duty(db, day, cfg, True)
            if not person or not duty:
                raise Invalid('Выберите подключённого участника и день очереди.')
            if duty['person'] == person_id:
                return
            notified = set()
            for message in db.execute("SELECT kind,person FROM outbox WHERE day=? AND status='sent' ORDER BY id", (day_string,)):
                if message['kind'] == 'replacement-old':
                    notified.discard(message['person'])
                else:
                    notified.add(message['person'])
            duty['revision'] += 1
            duty['person'] = person_id
            db.execute('UPDATE duties SET person=?,revision=?,manual=1 WHERE day=?', (person_id, duty['revision'], day_string))
            db.execute("UPDATE outbox SET status='cancelled' WHERE day=? AND status IN ('pending','retry')", (day_string,))
            if notified:
                expires = dt.datetime.combine(day+dt.timedelta(days=1), dt.time(), ZoneInfo(cfg['timezone'])).timestamp()
                label = day.strftime('%d.%m.%Y')
                for old in notified - {person_id}:
                    self.enqueue(db, duty, 'replacement-old', old, f'На {label} вас заменили. Дежурить и покупать молоко в этот день не нужно.', expires)
                if person_id not in notified:
                    self.enqueue(db, duty, 'replacement-new', person_id, f'Замена в расписании: {label} вы дежурите и покупаете молоко.', expires)

    def schedule(self, now=None):
        with self.db() as db:
            db.execute('BEGIN IMMEDIATE')
            cfg = self.settings(db)
            if not cfg['enabled'] or not cfg.get('bot_token'):
                return
            zone = ZoneInfo(cfg['timezone'])
            now = (now or dt.datetime.now(zone)).astimezone(zone)
            today = now.date()
            for day, kind, clock in ((today, 'morning', cfg['morning_time']), (today+dt.timedelta(days=1), 'eve', cfg['eve_time'])):
                if kind == 'eve' and not cfg['eve_enabled']:
                    continue
                due = dt.datetime.combine(today, dt.time.fromisoformat(clock), zone)
                if now < due:
                    continue
                duty = self.duty(db, day, cfg, True)
                if not duty:
                    continue
                person = db.execute('SELECT * FROM people WHERE id=?', (duty['person'],)).fetchone()
                message = cfg['message' if kind == 'morning' else 'eve_message']
                message = message.replace('{name}', person['name']).replace('{date}', day.strftime('%d.%m.%Y'))
                end = dt.datetime.combine(today+dt.timedelta(days=1), dt.time(), zone).timestamp()
                if kind == 'eve':
                    end = dt.datetime.combine(day, dt.time.fromisoformat(cfg['morning_time']), zone).timestamp()
                self.enqueue(db, duty, kind, duty['person'], message, end)

    def snapshot(self):
        with self.db() as db:
            cfg = self.settings(db)
            today = self.today(cfg)
            people = [dict(p) for p in db.execute('SELECT * FROM people ORDER BY position,id')]
            for person in people:
                person.pop('chat_id', None)
                person['connected'] = bool(db.execute('SELECT chat_id FROM people WHERE id=?', (person['id'],)).fetchone()[0])
                person['invite_url'] = ('https://t.me/'+cfg.get('bot_username','')+'?start=join_'+person['invite']) if person['invite'] and cfg.get('bot_username') and person['invite_expires'] > time.time() else None
                person.pop('invite', None)
                person.pop('invite_expires', None)
            names = {p['id']: p['name'] for p in people}
            schedule = []
            for n in range(21):
                day = today+dt.timedelta(days=n)
                duty = self.duty(db, day, cfg)
                if duty:
                    schedule.append({**duty, 'name': names.get(duty['person'], 'Участник'), 'planned_name': names.get(duty['planned'], 'Участник')})
            logs = [dict(r) for r in db.execute('SELECT o.id,o.day,o.kind,o.status,o.error,o.sent_at,p.name FROM outbox o LEFT JOIN people p ON p.id=o.person ORDER BY o.id DESC LIMIT 40')]
            public = {key: cfg[key] for key in DEFAULTS}
            return {'settings': public, 'people': people, 'schedule': schedule, 'logs': logs,
                    'bot': {'configured': bool(cfg.get('bot_token')), 'username': cfg.get('bot_username',''), 'error': cfg.get('worker_error','')},
                    'today': today.isoformat()}
