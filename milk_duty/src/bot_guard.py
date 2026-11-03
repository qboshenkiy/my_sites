"""Audit and moderation for this application's Telegram bot, retained for 30 days."""
import contextlib
import json
import os
from pathlib import Path
import re
import sqlite3
import sys
import time
import urllib.request


def clean(text):
    text = re.sub(r'https?://\S+', '[ссылка]', str(text))
    text = re.sub(r'\b\d{6,12}:[A-Za-z0-9_-]{20,}\b|\b[a-fA-F0-9]{32,}\b', '[код скрыт]', text)
    if re.match(r'^/(start|login|password)\b', text):
        return '[команда входа: параметры скрыты]'
    return text[:4000]


@contextlib.contextmanager
def database():
    folder = Path(os.getenv('DATA_DIR', str(Path(__file__).resolve().parents[1]/'data')))
    folder.mkdir(parents=True, exist_ok=True)
    db = sqlite3.connect(folder/'bot-guard.sqlite', timeout=3)
    (folder/'bot-guard.sqlite').chmod(0o600)
    db.row_factory = sqlite3.Row
    try:
        db.executescript('CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY,name TEXT,username TEXT,blocked INTEGER NOT NULL DEFAULT 0,last_seen REAL); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,person TEXT,direction TEXT,text TEXT,created REAL); CREATE INDEX IF NOT EXISTS events_person ON events(person,id);')
        with db:
            yield db
    finally:
        db.close()


def event(db, person, direction, text):
    db.execute('INSERT INTO events(person,direction,text,created) VALUES(?,?,?,?)', (str(person), direction, clean(text), time.time()))
    db.execute('DELETE FROM events WHERE created<? OR id<(SELECT COALESCE(MAX(id),0)-50000 FROM events)', (time.time()-30*86400,))


def incoming(update):
    try:
        message = update.get('message', {})
        sender = message.get('from', {})
        person = str(sender.get('id', ''))
        if not person.isdecimal() or sender.get('is_bot'):
            return True
        with database() as db:
            db.execute('INSERT INTO people(id,name,username,last_seen) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,username=excluded.username,last_seen=excluded.last_seen', (person, (sender.get('first_name','')+' '+sender.get('last_name','')).strip(), sender.get('username',''), time.time()))
            blocked = db.execute('SELECT blocked FROM people WHERE id=?', (person,)).fetchone()[0]
            if message.get('chat', {}).get('type') == 'private':
                event(db, person, 'blocked' if blocked else 'in', message.get('text','[вложение]'))
            return not blocked
    except (OSError, sqlite3.Error):
        print('Guard audit unavailable', file=sys.stderr)
        return True


def outgoing(method, args):
    if method not in ('sendMessage','editMessageText','sendPoll') or not str(args.get('chat_id','')).isdecimal():
        return
    try:
        with database() as db:
            event(db, args['chat_id'], 'out', args.get('text',args.get('question','')))
    except (OSError, sqlite3.Error):
        print('Guard audit unavailable', file=sys.stderr)


def cli(action, data):
    with database() as db:
        if action == 'people':
            return {'people': [dict(r) for r in db.execute('SELECT * FROM people ORDER BY last_seen DESC LIMIT 500')]}
        person = str(data.get('person',''))
        if not re.fullmatch(r'[0-9]{1,20}', person) or not db.execute('SELECT 1 FROM people WHERE id=?', (person,)).fetchone():
            raise ValueError('Участник ещё не писал этому боту')
        if action == 'history':
            return {'events': [dict(r) for r in db.execute('SELECT direction,text,created FROM (SELECT * FROM events WHERE person=? ORDER BY id DESC LIMIT 100) ORDER BY id', (person,))]}
        if action in ('block','unblock'):
            db.execute('UPDATE people SET blocked=? WHERE id=?', (int(action=='block'),person))
            return {'ok':True}
        if action == 'send':
            text = str(data.get('text','')).strip()
            if not 1 <= len(text) <= 3500:
                raise ValueError('Введите сообщение до 3500 символов')
            # Token stays inside the bot's container and is never returned to Guard.
            source = sqlite3.connect('file:'+str(Path(os.getenv('DATA_DIR','/data'))/'duty.sqlite')+'?mode=ro',uri=True)
            try:
                row=source.execute("SELECT value FROM config WHERE key='bot_token'").fetchone()
                token=json.loads(row[0]) if row else ''
            finally:
                source.close()
            if not token:
                raise ValueError('Токен бота не настроен')
            req=urllib.request.Request('https://api.telegram.org/bot'+token+'/sendMessage',data=json.dumps({'chat_id':person,'text':text}).encode(),headers={'Content-Type':'application/json'})
            try:
                with urllib.request.urlopen(req,timeout=15) as response:
                    if not json.load(response).get('ok'):
                        raise ValueError()
            except Exception:
                raise ValueError('Telegram не принял сообщение') from None
            event(db,person,'out',text)
            return {'ok':True}
        raise ValueError('Неизвестное действие')


if __name__ == '__main__':
    try:
        print(json.dumps(cli(sys.argv[1],json.loads(sys.argv[2])),ensure_ascii=False))
    except Exception as error:
        print(json.dumps({'error':str(error)},ensure_ascii=False))
        sys.exit(1)
