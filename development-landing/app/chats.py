import time


def initialize(conn):
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY, bot_id TEXT NOT NULL, peer TEXT NOT NULL,
            name TEXT NOT NULL, contact TEXT NOT NULL, updated INTEGER NOT NULL,
            UNIQUE(bot_id, peer)
        );
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY, chat_id INTEGER NOT NULL, direction TEXT NOT NULL,
            body TEXT NOT NULL, created INTEGER NOT NULL, update_key TEXT UNIQUE,
            sent INTEGER NOT NULL DEFAULT 0, retry_at INTEGER NOT NULL DEFAULT 0
        );
        CREATE INDEX IF NOT EXISTS messages_chat ON messages(chat_id,id);
        CREATE TABLE IF NOT EXISTS lead_status (
            lead_id INTEGER PRIMARY KEY, status TEXT NOT NULL
        );
    """)


def receive(conn, bot_id, peer, name, contact, body, update_key):
    now = int(time.time())
    created = conn.execute(
        'INSERT OR IGNORE INTO chats (bot_id,peer,name,contact,updated) VALUES (?,?,?,?,?)',
        (bot_id, peer, name, contact, now)).rowcount
    chat = conn.execute('SELECT id FROM chats WHERE bot_id=? AND peer=?', (bot_id, peer)).fetchone()
    chat_id = chat['id']
    inserted = conn.execute(
        "INSERT OR IGNORE INTO messages (chat_id,direction,body,created,update_key,sent) VALUES (?,'in',?,?,?,1)",
        (chat_id, body, now, update_key)).rowcount
    if inserted:
        conn.execute('UPDATE chats SET name=?,contact=?,updated=? WHERE id=?', (name, contact, now, chat_id))
    return chat_id, bool(created and inserted)


def list_chats(conn, bot_id, limit=100):
    return conn.execute('SELECT * FROM chats WHERE bot_id=? ORDER BY updated DESC,id DESC LIMIT ?', (bot_id, limit)).fetchall()


def history(conn, bot_id, chat_id, limit=100):
    chat = conn.execute('SELECT * FROM chats WHERE id=? AND bot_id=?', (chat_id, bot_id)).fetchone()
    if not chat:
        raise ValueError('Диалог не найден для текущего бота.')
    rows = conn.execute('SELECT * FROM messages WHERE chat_id=? ORDER BY id DESC LIMIT ?', (chat_id, limit)).fetchall()
    return chat, list(reversed(rows))


def reply(conn, bot_id, chat_id, body):
    body = body.strip()
    if not 1 <= len(body) <= 2000:
        raise ValueError('Введите сообщение длиной до 2000 символов.')
    chat = conn.execute('SELECT id FROM chats WHERE id=? AND bot_id=?', (chat_id, bot_id)).fetchone()
    if not chat:
        raise ValueError('Диалог не найден для текущего бота.')
    now = int(time.time())
    conn.execute("INSERT INTO messages (chat_id,direction,body,created) VALUES (?,'out',?,?)", (chat_id, body, now))
    conn.execute('UPDATE chats SET updated=? WHERE id=?', (now, chat_id))


def pending(conn, bot_id):
    return conn.execute("""
        SELECT m.id,m.body,c.peer FROM messages m JOIN chats c ON c.id=m.chat_id
        WHERE m.direction='out' AND m.sent=0 AND m.retry_at<=? AND c.bot_id=?
        AND NOT EXISTS (SELECT 1 FROM messages prior WHERE prior.chat_id=m.chat_id
                        AND prior.direction='out' AND prior.sent=0 AND prior.id<m.id)
        ORDER BY m.id LIMIT 10
    """, (int(time.time()), bot_id)).fetchall()


def owner_command(conn, bot_id, body):
    command, *args = body.split(maxsplit=2)
    if command == '/leads':
        rows = conn.execute('SELECT * FROM leads ORDER BY id DESC LIMIT 5').fetchall()
        return '\n\n'.join(f"№{r['id']} · {r['source']}\n{r['name']} · {r['contact']}\n{r['body'][:380]}" for r in rows) or 'Заявок пока нет.'
    if command == '/chats':
        rows = list_chats(conn, bot_id, 15)
        return '\n'.join(f"/chat {r['id']} · {r['name']} · {r['contact']}" for r in rows) or 'Диалогов пока нет.'
    if command in ('/chat', '/reply'):
        try:
            chat_id = int(args[0])
            if command == '/reply' and len(args) == 2:
                reply(conn, bot_id, chat_id, args[1])
                return 'Ответ поставлен в очередь.'
            if command == '/chat' and len(args) == 1:
                chat, rows = history(conn, bot_id, chat_id, 8)
                lines = [f"Диалог №{chat_id} · {chat['name']}"]
                lines += [('Клиент: ' if row['direction'] == 'in' else 'Вы: ') + row['body'][:350] for row in rows]
                return '\n\n'.join(lines) + f'\n\n/reply {chat_id} текст ответа'
        except (IndexError, ValueError, OverflowError) as error:
            if isinstance(error, ValueError) and str(error).startswith(('Диалог', 'Введите')):
                return str(error)
    return '/leads — заявки\n/chats — диалоги\n/chat 12 — история\n/reply 12 текст — ответ клиенту'
