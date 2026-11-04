"""Private synchronized notes service for web and Ubuntu."""
import hashlib,hmac,json,os,secrets,sqlite3,time
from pathlib import Path
from contextlib import contextmanager
from datetime import date
from flask import Flask,request,jsonify,session,send_from_directory
ROOT=Path(__file__).resolve().parents[1];DATA=Path(os.getenv('DATA_DIR',str(ROOT/'data')));DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
@contextmanager
def database():
    db=sqlite3.connect(DATA/'notes.sqlite',timeout=15);db.row_factory=sqlite3.Row
    try:
        db.create_function('fold',1,lambda text:str(text or '').casefold(),deterministic=True)
        db.executescript("CREATE TABLE IF NOT EXISTS notes(id TEXT PRIMARY KEY,title TEXT NOT NULL DEFAULT '',body TEXT NOT NULL DEFAULT '',folder_id INTEGER,pinned INTEGER NOT NULL DEFAULT 0,revision INTEGER NOT NULL DEFAULT 1,created REAL NOT NULL,updated REAL NOT NULL,deleted REAL);\nCREATE TABLE IF NOT EXISTS folders(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL);\nCREATE TABLE IF NOT EXISTS versions(id INTEGER PRIMARY KEY,note_id TEXT NOT NULL,title TEXT,body TEXT,revision INTEGER,created REAL);\nCREATE TABLE IF NOT EXISTS telegram(chat TEXT PRIMARY KEY);\nCREATE TABLE IF NOT EXISTS links(code TEXT PRIMARY KEY,expires REAL);\nCREATE TABLE IF NOT EXISTS bot_updates(id INTEGER PRIMARY KEY);\nCREATE TABLE IF NOT EXISTS bot_state(chat TEXT PRIMARY KEY,mode TEXT,argument TEXT);\nCREATE TABLE IF NOT EXISTS bot_info(key TEXT PRIMARY KEY,value TEXT);\nCREATE TABLE IF NOT EXISTS attempts(ip TEXT,created REAL);\nCREATE TABLE IF NOT EXISTS sync_mutations(id TEXT PRIMARY KEY,result TEXT NOT NULL,created REAL NOT NULL);\nCREATE INDEX IF NOT EXISTS notes_updated ON notes(deleted,pinned,updated);\nCREATE INDEX IF NOT EXISTS notes_folder ON notes(folder_id);\nCREATE INDEX IF NOT EXISTS versions_note ON versions(note_id,id);\n")
        with db:yield db
    finally:db.close()
secret=DATA/'session-secret'
try:
    fd=os.open(secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(secrets.token_hex(32))
except FileExistsError:pass
app=Flask(__name__,static_folder=None);app.secret_key=secret.read_text();app.config.update(MAX_CONTENT_LENGTH=1048576,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','1')=='1',PERMANENT_SESSION_LIFETIME=28800)

def epoch():
    try:return hashlib.sha256((DATA/'password.json').read_bytes()).hexdigest()
    except OSError:return ''
@app.before_request
def protect():
    if request.path.startswith('/api/'):
        if request.method=='POST':
            if not isinstance(request.get_json(silent=True),dict):return jsonify(error='Ожидается JSON-объект'),400
            origin=request.headers.get('Origin','');host=request.host
            if origin not in ('https://'+host,'http://'+host):return jsonify(error='Недопустимый источник'),403
        if request.path not in ('/api/login','/api/telegram/login'):
            if not epoch() or session.get('epoch')!=epoch():return jsonify(error='Войдите в приложение'),401
            if session.get('telegram_chat'):
                with database() as db:
                    if not db.execute('SELECT 1 FROM telegram WHERE chat=?',(session['telegram_chat'],)).fetchone():return jsonify(error='Telegram отключён. Войдите по паролю.'),401
            if request.method=='POST' and not hmac.compare_digest(str((request.get_json(silent=True) or {}).get('csrf','')),session.get('csrf','')):return jsonify(error='Обновите страницу и повторите'),403
@app.after_request
def headers(r):
    r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['Referrer-Policy']='no-referrer'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self' https://telegram.org; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'self' https://web.telegram.org https://*.telegram.org; form-action 'self'"
    return r
@app.errorhandler(ValueError)
def invalid(e):return jsonify(error=str(e)),400
@app.errorhandler(400)
def bad(e):return jsonify(error='Некорректный запрос'),400
@app.get('/health')
def health():return jsonify(ok=True)
@app.get('/')
def index():return send_from_directory(ROOT/'web','index.html')
@app.get('/<name>')
def assets(name):
    if name=='notes-desktop_1.0.0_all.deb':name='notes-desktop_1.1.0_all.deb'
    if name not in ('app.js','style.css','icon.svg','icon-192.png','icon-512.png','manifest.webmanifest','sw.js','offline.js','telegram.js','notes-desktop_1.0.0_all.deb','notes-desktop_1.1.0_all.deb'):return '',404
    return send_from_directory(ROOT/'web',name)
@app.post('/api/login')
def login():
    data=request.get_json();password=data.get('password','');ip=request.remote_addr
    with database() as db:
        db.execute('DELETE FROM attempts WHERE created<?',(time.time()-300,))
        if db.execute('SELECT COUNT(*) FROM attempts WHERE ip=?',(ip,)).fetchone()[0]>=5:return jsonify(error='Подождите 5 минут после неудачных попыток'),429
        db.execute('INSERT INTO attempts VALUES(?,?)',(ip,time.time()))
    try:
        c=json.loads((DATA/'password.json').read_text());valid=isinstance(password,str) and len(password)<=200 and hmac.compare_digest(hashlib.scrypt(password.encode(),salt=bytes.fromhex(c['salt']),n=16384,r=8,p=1).hex(),c['digest'])
    except (OSError,ValueError,KeyError):valid=False
    if not valid:return jsonify(error='Неверный пароль'),401
    session.clear();session.update(epoch=epoch(),csrf=secrets.token_hex(24));session.permanent=True
    with database() as db:db.execute('DELETE FROM attempts WHERE ip=?',(ip,))
    return jsonify(csrf=session['csrf'])
@app.post('/api/logout')
def logout():session.clear();return jsonify(ok=True)

def integer(value):
    if isinstance(value,bool):raise ValueError('Некорректный номер версии')
    try:return int(value)
    except (TypeError,ValueError):raise ValueError('Некорректный номер версии')

def folder(db,value):
    if value in (None,''):return None
    fid=integer(value)
    if not db.execute('SELECT 1 FROM folders WHERE id=?',(fid,)).fetchone():raise ValueError('Папка не найдена')
    return fid

def note(db,identifier):
    row=db.execute('SELECT * FROM notes WHERE id=?',(identifier,)).fetchone()
    return dict(row) if row else None

@app.get('/api/notes')
def listing():
    q=request.args.get('q','').strip()
    if len(q)>200:raise ValueError('Поиск — до 200 символов')
    view=request.args.get('view','all')
    if view not in ('all','pinned','trash'):raise ValueError('Неизвестный раздел')
    where=['deleted IS NOT NULL' if view=='trash' else 'deleted IS NULL'];args=[]
    if view=='pinned':where.append('pinned=1')
    with database() as db:
        fid=request.args.get('folder','')
        if fid:
            where.append('folder_id=?');args.append(folder(db,fid))
        if q:where.append('(instr(fold(title),fold(?))>0 OR instr(fold(body),fold(?))>0)');args.extend([q,q])
        sql=' FROM notes WHERE '+' AND '.join(where)
        total=db.execute('SELECT COUNT(*)'+sql,args).fetchone()[0]
        rows=[dict(r) for r in db.execute("SELECT id,title,substr(body,1,160) AS preview,folder_id,pinned,revision,updated,deleted"+sql+' ORDER BY pinned DESC,updated DESC,id LIMIT 200',args)]
        folders=[dict(r) for r in db.execute('SELECT f.*, (SELECT COUNT(*) FROM notes WHERE folder_id=f.id AND deleted IS NULL) AS count FROM folders f ORDER BY id')]
        counts={v:db.execute('SELECT COUNT(*) FROM notes WHERE '+w).fetchone()[0] for v,w in [('all','deleted IS NULL'),('pinned','deleted IS NULL AND pinned=1'),('trash','deleted IS NOT NULL')]}
    return jsonify(notes=rows,total=total,folders=folders,counts=counts,csrf=session['csrf'])

@app.get('/api/note/<identifier>')
def read_note(identifier):
    with database() as db:result=note(db,identifier)
    return (jsonify(result),200) if result else (jsonify(error='Заметка не найдена'),404)

@app.post('/api/note/create')
def create_note():
    d=request.get_json();identifier=secrets.token_hex(12);now=time.time()
    with database() as db:
        fid=folder(db,d.get('folder_id'))
        db.execute('INSERT INTO notes(id,folder_id,created,updated) VALUES(?,?,?,?)',(identifier,fid,now,now));result=note(db,identifier)
    return jsonify(result)

@app.post('/api/note/save')
def save_note():
    d=request.get_json();title=d.get('title','');body=d.get('body','');revision=integer(d.get('revision'))
    if not isinstance(title,str) or not isinstance(body,str):raise ValueError('Название и текст должны быть строками')
    if len(title)>200 or len(body)>200000:raise ValueError('Название — до 200 символов, текст — до 200 000')
    if d.get('pinned',False) not in (True,False,0,1):raise ValueError('Некорректный флаг закрепления')
    with database() as db:
        db.execute('BEGIN IMMEDIATE');old=note(db,d.get('id',''))
        if not old:return jsonify(error='Заметка не найдена'),404
        if old['revision']!=revision or old['deleted'] is not None:return jsonify(error='Заметка изменена в другом окне. Ваш текст остаётся в редакторе.',current=old),409
        fid=folder(db,d.get('folder_id'))
        db.execute('INSERT INTO versions(note_id,title,body,revision,created) VALUES(?,?,?,?,?)',(old['id'],old['title'],old['body'],revision,time.time()))
        db.execute('DELETE FROM versions WHERE note_id=? AND id NOT IN (SELECT id FROM versions WHERE note_id=? ORDER BY id DESC LIMIT 20)',(old['id'],old['id']))
        db.execute('UPDATE notes SET title=?,body=?,folder_id=?,pinned=?,revision=revision+1,updated=? WHERE id=?',(title,body,fid,int(bool(d.get('pinned'))),time.time(),old['id']))
        result=note(db,old['id'])
    return jsonify(result)

@app.post('/api/note/trash')
def trash_note():
    d=request.get_json();revision=integer(d.get('revision'));restore=d.get('restore') is True
    with database() as db:
        db.execute('BEGIN IMMEDIATE');old=note(db,d.get('id',''))
        if not old:return jsonify(error='Заметка не найдена'),404
        if old['revision']!=revision:return jsonify(error='Заметка изменена. Обновите список и повторите.',current=old),409
        db.execute('UPDATE notes SET deleted=?,revision=revision+1,updated=? WHERE id=?',(None if restore else time.time(),time.time(),old['id']))
        result=note(db,old['id'])
    return jsonify(result)

@app.post('/api/folder')
def save_folder():
    d=request.get_json();name=str(d.get('name','')).strip()
    if not name or len(name)>60:raise ValueError('Название папки — от 1 до 60 символов')
    with database() as db:
        db.execute('BEGIN IMMEDIATE');fid=folder(db,d.get('id'))
        if db.execute('SELECT 1 FROM folders WHERE fold(name)=fold(?) AND id!=?',(name,fid or 0)).fetchone():raise ValueError('Папка с таким названием уже есть')
        if fid:db.execute('UPDATE folders SET name=? WHERE id=?',(name,fid))
        else:fid=db.execute('INSERT INTO folders(name) VALUES(?)',(name,)).lastrowid
    return jsonify(id=fid,name=name)

@app.post('/api/folder/delete')
def delete_folder():
    d=request.get_json()
    with database() as db:
        db.execute('BEGIN IMMEDIATE');fid=folder(db,d.get('id'))
        if fid is None:raise ValueError('Выберите папку')
        db.execute('UPDATE notes SET folder_id=NULL,revision=revision+1 WHERE folder_id=?',(fid,));db.execute('DELETE FROM folders WHERE id=?',(fid,))
    return jsonify(ok=True)

@app.post('/api/telegram/login')
def telegram_login():
    from telegram_auth import validate
    try:uid=validate(request.get_json().get('init_data',''),os.getenv('TELEGRAM_BOT_TOKEN',''))
    except ValueError as e:return jsonify(error=str(e)),401
    with database() as db:
        if not db.execute('SELECT 1 FROM telegram WHERE chat=?',(uid,)).fetchone():return jsonify(error='Сначала привяжите Telegram через настройки приложения'),403
    session.clear();session.update(epoch=epoch(),csrf=secrets.token_hex(24),telegram_chat=uid);session.permanent=True
    return jsonify(csrf=session['csrf'])

@app.post('/api/telegram/link')
def telegram_link():
    code=secrets.token_hex(12)
    with database() as db:
        db.execute('DELETE FROM links');db.execute('INSERT INTO links VALUES(?,?)',(code,time.time()+600))
    return jsonify(code=code)

@app.post('/api/telegram/unlink')
def telegram_unlink():
    with database() as db:
        db.execute('DELETE FROM telegram');db.execute('DELETE FROM links');db.execute('DELETE FROM bot_state')
    return jsonify(ok=True)

@app.get('/api/telegram/status')
def telegram_status():
    with database() as db:
        linked=bool(db.execute('SELECT 1 FROM telegram').fetchone())
        info=dict(db.execute('SELECT key,value FROM bot_info'))
    return jsonify(linked=linked,configured=bool(os.getenv('TELEGRAM_BOT_TOKEN')),username=os.getenv('TELEGRAM_BOT_USERNAME','') or info.get('username',''))

@app.get('/api/offline')
def offline_snapshot():
    with database() as db:
        notes=[dict(r) for r in db.execute('SELECT * FROM notes')]
        folders=[dict(r) for r in db.execute('SELECT * FROM folders')]
    return jsonify(notes=notes,folders=folders,csrf=session['csrf'])

@app.post('/api/sync')
def sync_note():
    import re
    d=request.get_json();mid=d.get('mutation_id','');data=d.get('entity',{})
    if not isinstance(mid,str) or not re.fullmatch('[a-f0-9]{32}',mid):raise ValueError('Некорректный номер изменения')
    if not isinstance(data,dict):raise ValueError('Некорректная заметка')
    identifier=data.get('id','');title=data.get('title','');body=data.get('body','')
    if not isinstance(identifier,str) or not re.fullmatch('[a-f0-9]{24,64}',identifier):raise ValueError('Некорректный номер заметки')
    if not isinstance(title,str) or not isinstance(body,str) or len(title)>200 or len(body)>200000:raise ValueError('Превышен размер заметки')
    base=integer(d.get('base_revision',0));after=d.get('after');deleted=data.get('deleted') is not None
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        applied=db.execute('SELECT result FROM sync_mutations WHERE id=?',(mid,)).fetchone()
        if applied:return jsonify(json.loads(applied[0]))
        if after:
            previous=db.execute('SELECT result FROM sync_mutations WHERE id=?',(str(after),)).fetchone()
            if not previous:raise ValueError('Сначала синхронизируйте предыдущее изменение')
            previous=json.loads(previous[0]);identifier=previous['id'];base=previous['revision']
        old=note(db,identifier);conflict=bool(old and old['revision']!=base)
        # A divergent edit becomes a separate note; the other device's text stays intact.
        if conflict:identifier=secrets.token_hex(12);title=title[:180]+' (конфликт)';deleted=False;old=None
        fid=data.get('folder_id')
        try:fid=folder(db,fid)
        except ValueError:fid=None
        now=time.time()
        if old:
            db.execute('INSERT INTO versions(note_id,title,body,revision,created) VALUES(?,?,?,?,?)',(old['id'],old['title'],old['body'],old['revision'],now))
            db.execute('DELETE FROM versions WHERE note_id=? AND id NOT IN (SELECT id FROM versions WHERE note_id=? ORDER BY id DESC LIMIT 20)',(identifier,identifier))
            revision=old['revision']+1
            db.execute('UPDATE notes SET title=?,body=?,folder_id=?,pinned=?,deleted=?,revision=?,updated=? WHERE id=?',(title,body,fid,int(bool(data.get('pinned'))),now if deleted else None,revision,now,identifier))
        else:
            revision=1
            db.execute('INSERT INTO notes(id,title,body,folder_id,pinned,revision,created,updated,deleted) VALUES(?,?,?,?,?,?,?,?,?)',(identifier,title,body,fid,int(bool(data.get('pinned'))),revision,now,now,now if deleted else None))
        result={'id':identifier,'revision':revision,'conflict':conflict}
        db.execute('INSERT INTO sync_mutations VALUES(?,?,?)',(mid,json.dumps(result),now))
    return jsonify(result)

@app.get('/api/export')
def export():
    with database() as db:result={t:[dict(r) for r in db.execute('SELECT * FROM '+t)] for t in ('notes','folders')}
    r=jsonify(version=1,**result);r.headers['Content-Disposition']='attachment; filename=notes-backup.json';return r

@app.get('/api/note/<identifier>/export')
def export_note(identifier):
    with database() as db:result=note(db,identifier)
    if not result:return jsonify(error='Заметка не найдена'),404
    from flask import Response
    r=Response(result['title']+'\n\n'+result['body'],content_type='text/plain; charset=utf-8');r.headers['Content-Disposition']='attachment; filename=note-'+result['id']+'.txt';return r

if __name__=='__main__':app.run(host='127.0.0.1',port=8170)
