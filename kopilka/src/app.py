"""Private single-household finance service for web, PWA and Telegram."""
import hashlib,hmac,json,os,secrets,sqlite3,time
from pathlib import Path
from contextlib import contextmanager
from datetime import date
from flask import Flask,request,jsonify,session,send_from_directory
from core import CATEGORIES,money,operation,overview,transfer,wallet_id
ROOT=Path(__file__).resolve().parents[1];DATA=Path(os.getenv('DATA_DIR',str(ROOT/'data')));DATA.mkdir(parents=True,exist_ok=True,mode=0o700)
@contextmanager
def database():
    db=sqlite3.connect(DATA/'finance.sqlite',timeout=15);db.row_factory=sqlite3.Row
    try:
        db.executescript('''CREATE TABLE IF NOT EXISTS transactions(id INTEGER PRIMARY KEY,kind TEXT,amount INTEGER,category TEXT,day TEXT,note TEXT,source TEXT,external TEXT UNIQUE);
CREATE TABLE IF NOT EXISTS wallets(id INTEGER PRIMARY KEY AUTOINCREMENT,name TEXT NOT NULL,opening INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS transfers(id INTEGER PRIMARY KEY,from_wallet INTEGER NOT NULL,to_wallet INTEGER NOT NULL,amount INTEGER NOT NULL,day TEXT NOT NULL,note TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS goals(id INTEGER PRIMARY KEY,name TEXT,target INTEGER,saved INTEGER DEFAULT 0,deadline TEXT);
CREATE TABLE IF NOT EXISTS contributions(id INTEGER PRIMARY KEY,goal INTEGER,amount INTEGER,created REAL);
CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT);
CREATE TABLE IF NOT EXISTS attempts(ip TEXT,created REAL);
CREATE TABLE IF NOT EXISTS links(code TEXT PRIMARY KEY,expires REAL);
CREATE TABLE IF NOT EXISTS telegram(chat TEXT PRIMARY KEY);
CREATE TABLE IF NOT EXISTS bot_updates(id INTEGER PRIMARY KEY);
''')
        # Both gunicorn workers and the bot may start together. Serialize migration.
        with db:
            db.execute('BEGIN IMMEDIATE')
            db.execute("INSERT OR IGNORE INTO wallets(id,name,opening) VALUES(1,'Основной',0)")
            if 'wallet_id' not in {r[1] for r in db.execute('PRAGMA table_info(transactions)')}:
                db.execute('ALTER TABLE transactions ADD COLUMN wallet_id INTEGER NOT NULL DEFAULT 1')
            db.execute('CREATE INDEX IF NOT EXISTS transactions_wallet ON transactions(wallet_id)')
            db.execute('CREATE INDEX IF NOT EXISTS transfers_source ON transfers(from_wallet)')
            db.execute('CREATE INDEX IF NOT EXISTS transfers_target ON transfers(to_wallet)')
        with db:yield db
    finally:db.close()
secret=DATA/'session-secret'
try:
    fd=os.open(secret,os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
    with os.fdopen(fd,'w') as f:f.write(secrets.token_hex(32))
except FileExistsError:pass
app=Flask(__name__,static_folder=None);app.secret_key=secret.read_text();app.config.update(MAX_CONTENT_LENGTH=16384,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Strict',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','1')=='1',PERMANENT_SESSION_LIFETIME=28800)

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
        if request.path!='/api/login':
            if not epoch() or session.get('epoch')!=epoch():return jsonify(error='Войдите в приложение'),401
            if request.method=='POST' and not hmac.compare_digest(str((request.get_json(silent=True) or {}).get('csrf','')),session.get('csrf','')):return jsonify(error='Обновите страницу и повторите'),403
@app.after_request
def headers(r):
    r.headers['Cache-Control']='no-store';r.headers['X-Content-Type-Options']='nosniff';r.headers['X-Frame-Options']='DENY';r.headers['Referrer-Policy']='no-referrer'
    r.headers['Content-Security-Policy']="default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
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
    if name not in ('app.js','style.css','icon.svg','icon-192.png','icon-512.png','manifest.webmanifest','sw.js'):return '',404
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
@app.get('/api/state')
def state():
    with database() as db:result=overview(db,request.args.get('month',date.today().strftime('%Y-%m')))
    return jsonify(**result,csrf=session['csrf'],categories_list=CATEGORIES)
@app.post('/api/transaction')
def transaction():
    with database() as db:operation(db,request.get_json())
    return jsonify(ok=True)
@app.post('/api/delete')
def delete():
    d=request.get_json();table={'transaction':'transactions','goal':'goals','transfer':'transfers'}.get(d.get('type'))
    if not table:raise ValueError('Неизвестный тип записи')
    with database() as db:db.execute(f'DELETE FROM {table} WHERE id=?',(int(d['id']),))
    return jsonify(ok=True)
@app.post('/api/wallet')
def save_wallet():
    d=request.get_json();name=str(d.get('name','')).strip()
    if not name or len(name)>60:raise ValueError('Название кошелька — от 1 до 60 символов')
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        wid=wallet_id(db,d['id']) if d.get('id') else None
        if db.execute('SELECT 1 FROM wallets WHERE lower(name)=lower(?) AND id!=?',(name,wid or 0)).fetchone():raise ValueError('Кошелёк с таким названием уже есть')
        if wid:
            db.execute('UPDATE wallets SET name=? WHERE id=?',(name,wid))
            if 'opening' in d:
                opening=money(d['opening']) if str(d['opening']) not in ('','0','0.00') else 0
                db.execute('UPDATE wallets SET opening=? WHERE id=?',(opening,wid))
        else:
            opening=money(d['opening']) if str(d.get('opening','0')) not in ('','0','0.00') else 0
            db.execute('INSERT INTO wallets(name,opening) VALUES(?,?)',(name,opening))
    return jsonify(ok=True)
@app.post('/api/wallet/delete')
def delete_wallet():
    d=request.get_json()
    with database() as db:
        db.execute('BEGIN IMMEDIATE');wid=wallet_id(db,d.get('id'))
        if wid==1:raise ValueError('Основной кошелёк удалить нельзя')
        used=db.execute('SELECT 1 FROM transactions WHERE wallet_id=? UNION ALL SELECT 1 FROM transfers WHERE from_wallet=? OR to_wallet=? LIMIT 1',(wid,wid,wid)).fetchone()
        if used or db.execute('SELECT opening FROM wallets WHERE id=?',(wid,)).fetchone()[0]:raise ValueError('Можно удалить только пустой кошелёк без операций и начального остатка')
        db.execute('DELETE FROM wallets WHERE id=?',(wid,))
    return jsonify(ok=True)
@app.post('/api/transfer')
def make_transfer():
    with database() as db:
        db.execute('BEGIN IMMEDIATE');transfer(db,request.get_json())
    return jsonify(ok=True)
@app.post('/api/goal')
def goal():
    d=request.get_json();name=str(d.get('name','')).strip();deadline=date.fromisoformat(d.get('deadline',''))
    if not name or len(name)>100:raise ValueError('Название цели — от 1 до 100 символов')
    if deadline<date.today():raise ValueError('Выберите сегодняшний или будущий срок')
    target=money(d.get('target',''))
    with database() as db:db.execute('INSERT INTO goals(name,target,deadline) VALUES(?,?,?)',(name,target,str(deadline)))
    return jsonify(ok=True)
@app.post('/api/contribute')
def contribute():
    d=request.get_json();amount=money(d.get('amount',''));gid=int(d.get('id',0))
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        row=db.execute('SELECT * FROM goals WHERE id=?',(gid,)).fetchone()
        if not row:raise ValueError('Цель не найдена')
        if row['saved']+amount>row['target']:raise ValueError('Сумма превышает остаток цели')
        db.execute('UPDATE goals SET saved=saved+? WHERE id=?',(amount,gid));db.execute('INSERT INTO contributions(goal,amount,created) VALUES(?,?,?)',(gid,amount,time.time()))
    return jsonify(ok=True)
@app.post('/api/settings')
def settings():
    d=request.get_json();currency=d.get('currency','KGS')
    if currency not in ('KGS','RUB','USD','EUR'):raise ValueError('Выберите валюту')
    budget=money(d['budget']) if str(d.get('budget','0')) not in ('','0') else 0
    with database() as db:
        old=dict(db.execute('SELECT key,value FROM settings'))
        if old.get('currency','KGS')!=currency and (db.execute('SELECT COUNT(*) FROM transactions').fetchone()[0] or db.execute('SELECT COUNT(*) FROM goals').fetchone()[0] or db.execute('SELECT COUNT(*) FROM transfers').fetchone()[0] or db.execute('SELECT COALESCE(SUM(opening),0) FROM wallets').fetchone()[0]):raise ValueError('Для смены валюты нужны пустая история и отсутствие целей. Конвертация не выполняется.')
        for k,v in [('currency',currency),('budget',str(budget))]:db.execute('INSERT OR REPLACE INTO settings VALUES(?,?)',(k,v))
    return jsonify(ok=True)
@app.get('/api/export')
def export():
    with database() as db:result={t:[dict(r) for r in db.execute('SELECT * FROM '+t)] for t in ('transactions','goals','contributions','settings','wallets','transfers')}
    r=jsonify(version=2,**result);r.headers['Content-Disposition']='attachment; filename=kopilka-backup.json';return r
@app.post('/api/telegram/link')
def link():
    code=secrets.token_hex(12)
    with database() as db:
        db.execute('DELETE FROM links');db.execute('INSERT INTO links VALUES(?,?)',(code,time.time()+600))
    return jsonify(code=code)
@app.post('/api/telegram/unlink')
def unlink():
    with database() as db:db.execute('DELETE FROM telegram');db.execute('DELETE FROM links')
    return jsonify(ok=True)
@app.get('/api/telegram/status')
def telegram_status():
    with database() as db:count=db.execute('SELECT COUNT(*) FROM telegram').fetchone()[0]
    return jsonify(linked=bool(count),configured=bool(os.getenv('TELEGRAM_BOT_TOKEN')))
if __name__=='__main__':app.run(host='0.0.0.0',port=8160)
