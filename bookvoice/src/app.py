"""Private book-to-audio library. Single CPU worker, durable queue, no paid API."""
import argparse,fcntl,getpass,json,os,re,secrets,shutil,sqlite3,threading,time
from contextlib import contextmanager
from functools import wraps
from pathlib import Path
from flask import Flask,request,jsonify,session,send_file,send_from_directory
from werkzeug.security import generate_password_hash,check_password_hash
from werkzeug.exceptions import HTTPException
import elevenlabs
from engine import Narrator,VOICES,MAX_TEXT,extract,chunks

class Service:
    def __init__(self,root,models=None):
        self.root=Path(root);self.root.mkdir(parents=True,exist_ok=True);self.books=self.root/'books';self.books.mkdir(exist_ok=True)
        self.engine=Narrator(models or os.getenv('MODEL_DIR','/models'));self.working=None;self.stop=threading.Event()
        with self.db() as db:
            db.execute('CREATE TABLE IF NOT EXISTS books(id TEXT PRIMARY KEY,title TEXT NOT NULL,source TEXT NOT NULL,text TEXT NOT NULL DEFAULT \'\',state TEXT NOT NULL,voice TEXT NOT NULL DEFAULT \'denis\',speed REAL NOT NULL DEFAULT 1,pause REAL NOT NULL DEFAULT .35,total INTEGER NOT NULL DEFAULT 0,done INTEGER NOT NULL DEFAULT 0,error TEXT NOT NULL DEFAULT \'\',created REAL NOT NULL)')
            columns={r[1] for r in db.execute('PRAGMA table_info(books)')}
            for name,definition in [('provider',"TEXT NOT NULL DEFAULT 'local'"),('eleven_voice_id',"TEXT NOT NULL DEFAULT ''")]:
                if name not in columns:db.execute('ALTER TABLE books ADD COLUMN '+name+' '+definition)
            db.execute("UPDATE books SET state=CASE WHEN state='extracting' THEN 'uploaded' WHEN provider='elevenlabs' THEN 'paused' ELSE 'queued' END WHERE state IN ('extracting','rendering')")
        self.attempts={};self.auth_lock=threading.Lock()
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.root/'library.sqlite',timeout=10);db.row_factory=sqlite3.Row
        try:yield db;db.commit()
        finally:db.close()
    def update(self,id,**values):
        with self.db() as db:db.execute('UPDATE books SET '+','.join(k+'=?' for k in values)+' WHERE id=?',[*values.values(),id])
    def get(self,id):
        with self.db() as db:row=db.execute('SELECT * FROM books WHERE id=?',[id]).fetchone()
        return dict(row) if row else None
    def has_cloud_queue(self):
        with self.db() as db:return db.execute("SELECT 1 FROM books WHERE provider='elevenlabs' AND state IN ('queued','rendering') LIMIT 1").fetchone() is not None
    def settings(self):
        p=self.root/'elevenlabs.json'
        return json.loads(p.read_text()) if p.exists() else {'key':'','voices':[]}
    def save_settings(self,settings):
        p=self.root/'elevenlabs.json';temp=p.with_name('elevenlabs.'+secrets.token_hex(8)+'.tmp');temp.write_text(json.dumps(settings));temp.chmod(0o600);temp.replace(p)
    def provider_ready(self,book):
        if book['provider']=='elevenlabs':
            config=self.settings()
            if not config.get('key') or book['eleven_voice_id'] not in {v['id'] for v in config.get('voices',[])}:raise ValueError('Подключите ElevenLabs и выберите доступный голос в настройках книги.')
        elif not self.engine.available(book['voice']):raise ValueError('Голос пока не установлен на сервере. Выполните загрузку моделей из инструкции.')
    def space(self,extra=0):
        maximum=int(os.getenv('MAX_STORAGE_MB','4096'))*1024**2
        used=sum(p.stat().st_size for p in self.books.rglob('*') if p.is_file())
        if used+extra>=maximum or shutil.disk_usage(self.root).free<extra+150*1024**2:raise ValueError('Мало места для аудио. Скачайте и удалите готовые книги.')
    def tick(self):
        with self.db() as db:row=db.execute("SELECT * FROM books WHERE state IN ('uploaded','queued') ORDER BY created LIMIT 1").fetchone()
        if not row:return False
        book=dict(row);id=book['id'];folder=self.books/id
        with self.db() as db:
            changed=db.execute('UPDATE books SET state=? WHERE id=? AND state=?',['extracting' if book['state']=='uploaded' else 'rendering',id,book['state']]).rowcount
        if not changed:return True
        self.working=id
        try:
            if book['state']=='uploaded':
                text=extract(folder/book['source']);self.update(id,text=text,state='draft',error='');return True
            self.update(id,error='');parts=chunks(book['text']);self.update(id,total=len(parts));done=0
            for i,text in enumerate(parts):
                current=self.get(id)
                if self.stop.is_set() or current['state']!='rendering':return True
                self.space();out=folder/(f'{i:05d}.mp3')
                if not out.exists():
                    temp=folder/(f'{i:05d}.tmp.mp3')
                    if book['provider']=='elevenlabs':elevenlabs.render(self.settings().get('key',''),text,temp,book['eleven_voice_id'],book['speed'])
                    else:self.engine.render(text,temp,book['voice'],book['speed'],book['pause'])
                    temp.replace(out)
                done+=1;self.update(id,done=done)
            if self.get(id)['state']!='rendering':return True
            self.space(sum((folder/f'{i:05d}.mp3').stat().st_size for i in range(len(parts))))
            import subprocess
            listing=folder/'concat.txt';listing.write_text(''.join(f"file '{i:05d}.mp3'\n" for i in range(len(parts))))
            subprocess.run(['ffmpeg','-v','error','-y','-f','concat','-safe','1','-i',str(listing),'-codec:a','libmp3lame','-b:a','128k' if book['provider']=='elevenlabs' else '64k',str(folder/'book.tmp.mp3')],check=True,timeout=900)
            (folder/'book.tmp.mp3').replace(folder/'book.mp3');self.update(id,state='ready',error='')
        except Exception as e:
            message=str(e) if isinstance(e,ValueError) else 'Не удалось обработать книгу. Проверьте файл, свободное место и журнал модуля в GitDeck.'
            self.update(id,state='error',error=message)
        finally:self.working=None
        return True
    def run(self):
        while not self.stop.is_set():
            try:
                if not self.tick():self.stop.wait(1)
            except Exception:
                import logging
                logging.exception('Book worker failed; retrying')
                self.stop.wait(5)


def create_app(root=None,models=None,start_worker=False):
    root=Path(root or os.getenv('DATA_DIR','/data'));root.mkdir(parents=True,exist_ok=True)
    worker_lock=None
    if start_worker:
        worker_lock=(root/'worker.lock').open('a');fcntl.flock(worker_lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    service=Service(root,models)
    secret=root/'session.key'
    if not secret.exists():secret.write_text(secrets.token_hex(32));secret.chmod(0o600)
    web=Path(__file__).resolve().parents[1]/'web';app=Flask(__name__,static_folder=None);app.secret_key=secret.read_text()
    app.config.update(MAX_CONTENT_LENGTH=32*1024**2,SESSION_COOKIE_HTTPONLY=True,SESSION_COOKIE_SAMESITE='Lax',SESSION_COOKIE_SECURE=os.getenv('COOKIE_SECURE','0')=='1',PERMANENT_SESSION_LIFETIME=86400)
    app.service=service
    def password():
        p=root/'password.json';return json.loads(p.read_text()) if p.exists() else None
    def valid_session():
        auth=password();return auth and session.get('epoch')==auth['epoch']
    @app.before_request
    def guard():
        if request.path.startswith('/api/') and request.path not in ['/api/session','/api/login']:
            if not valid_session():return jsonify(error='Войдите в библиотеку.'),401
            if request.method!='GET' and not secrets.compare_digest(request.headers.get('X-CSRF-Token',''),session.get('csrf','!')):return jsonify(error='Обновите страницу и повторите.'),403
    @app.after_request
    def headers(response):
        response.headers.update({'X-Content-Type-Options':'nosniff','Referrer-Policy':'no-referrer','X-Frame-Options':'DENY','Content-Security-Policy':"default-src 'self'; style-src 'self'; script-src 'self'; media-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'"})
        if request.path.startswith('/api/'):response.headers['Cache-Control']='no-store'
        return response
    @app.errorhandler(Exception)
    def error(e):
        if isinstance(e,HTTPException):return jsonify(error='Файл слишком большой (максимум 30 МБ).' if e.code==413 else e.description),e.code
        if isinstance(e,ValueError):return jsonify(error=str(e)),400
        app.logger.exception('Request failed');return jsonify(error='Не удалось выполнить действие. Подробности в журнале модуля.'),500
    @app.get('/')
    def index():return send_from_directory(web,'index.html')
    @app.get('/assets/<path:name>')
    def assets(name):return send_from_directory(web,name)
    @app.get('/health')
    def health():return {'ok':True}
    @app.get('/api/session')
    def status():return {'authenticated':bool(valid_session()),'configured':password() is not None}
    @app.post('/api/login')
    def login():
        # Strict Origin matching also protects login from cross-site form submission.
        if request.headers.get('Origin') and request.headers['Origin'].rstrip('/')!=request.host_url.rstrip('/') and request.headers['Origin'].split('://')[-1]!=request.host:return {'error':'Недопустимый источник запроса.'},403
        key=request.remote_addr;now=time.time()
        with service.auth_lock:
            failures=[t for t in service.attempts.get(key,[]) if now-t<300]
            if len(failures)>=10:return {'error':'Слишком много попыток. Подождите 5 минут.'},429
            auth=password();candidate=(request.get_json(silent=True) or {}).get('password','')
            if not auth or not isinstance(candidate,str) or len(candidate)>200 or not check_password_hash(auth['hash'],candidate):
                service.attempts[key]=failures+[now];return {'error':'Неверный пароль.'},401
            service.attempts.pop(key,None)
        session.clear();session['epoch']=auth['epoch'];session['csrf']=secrets.token_hex(24);session.permanent=True
        return {'csrf':session['csrf']}
    @app.get('/api/bootstrap')
    def bootstrap():
        with service.db() as db:books=[dict(r) for r in db.execute('SELECT id,title,source,state,voice,speed,pause,total,done,error,created,provider,eleven_voice_id FROM books ORDER BY created DESC')]
        return {'elevenlabs':{'configured':bool(service.settings().get('key')),'voices':service.settings().get('voices',[]),'model':elevenlabs.MODEL},'csrf':session['csrf'],'books':books,'working':service.working,'voices':[{'id':k,'name':v[0],'available':service.engine.available(k)} for k,v in VOICES.items()]}
    @app.post('/api/elevenlabs')
    def configure_elevenlabs():
        if service.working or service.has_cloud_queue():
            return {'error':'Сначала поставьте задачи озвучки на паузу.'},409
        data=request.get_json();old=service.settings()
        if data.get('remove'):
            service.save_settings({'key':'','voices':[]});return {'configured':False,'voices':[]}
        key=data.get('key') or old.get('key','')
        if not isinstance(key,str) or not 10<=len(key)<=256 or any(c.isspace() for c in key):raise ValueError('Введите API-ключ ElevenLabs.')
        voices=elevenlabs.list_voices(key)
        service.save_settings({'key':key,'voices':voices})
        return {'configured':True,'voices':voices}
    @app.post('/api/logout')
    def logout():session.clear();return {'ok':True}
    @app.post('/api/books')
    def upload():
        service.space()
        with service.db() as db:
            if db.execute('SELECT count(*) FROM books').fetchone()[0]>=40:raise ValueError('В библиотеке 40 книг. Удалите ненужные перед загрузкой.')
        file=request.files.get('file');raw=request.form.get('text','');id=secrets.token_hex(12);folder=service.books/id;folder.mkdir()
        try:
            title=request.form.get('title','').strip()[:120]
            if file and file.filename:
                suffix=Path(file.filename).suffix.lower()
                if suffix not in ['.pdf','.docx','.doc']:raise ValueError('Выберите PDF, DOCX или DOC.')
                source='original'+suffix;file.save(folder/source)
                if (folder/source).stat().st_size>30*1024**2:raise ValueError('Файл больше 30 МБ.')
                state='uploaded';text='';title=title or Path(file.filename).stem[:120]
            else:
                text=raw.strip()
                if not 20<=len(text)<=MAX_TEXT:raise ValueError('Вставьте от 20 до 500 000 символов.')
                source='Текст';state='draft';title=title or 'Новая книга'
            with service.db() as db:db.execute('INSERT INTO books(id,title,source,text,state,created) VALUES (?,?,?,?,?,?)',[id,title,source,text,state,time.time()])
        except Exception:shutil.rmtree(folder);raise
        return {'id':id},201
    def book_or_404(id):
        if not re.fullmatch('[a-f0-9]{24}',id):from flask import abort;abort(404)
        book=service.get(id)
        if not book:from flask import abort;abort(404)
        return book
    @app.get('/api/books/<id>')
    def detail(id):
        book=book_or_404(id);book['parts']=[i for i in range(book['total']) if (service.books/id/f'{i:05d}.mp3').exists()];book['busy']=service.working==id;return book
    @app.post('/api/books/<id>/save')
    def save(id):
        book=book_or_404(id)
        if service.working==id or book['state'] in ['uploaded','extracting','queued','rendering']:return {'error':'Сначала остановите обработку и дождитесь завершения части.'},409
        data=request.get_json();provider=data.get('provider','local');eleven_voice_id=data.get('eleven_voice_id','');text=data.get('text','');title=data.get('title','').strip()[:120];voice=data.get('voice','denis');speed=float(data.get('speed',1));pause=float(data.get('pause',.35))
        if not isinstance(text,str) or not 20<=len(text)<=MAX_TEXT or not title:raise ValueError('Заполните название и текст (20–500 000 символов).')
        if provider not in ['local','elevenlabs']:raise ValueError('Выберите способ озвучки.')
        if provider=='elevenlabs':
            if not .8<=speed<=1.2:raise ValueError('Для ElevenLabs выберите скорость от 0.8 до 1.2.')
            if eleven_voice_id not in {v['id'] for v in service.settings().get('voices',[])}:raise ValueError('Подключите ElevenLabs и выберите голос.')
        if voice not in VOICES or not .75<=speed<=1.35 or not .15<=pause<=1.2:raise ValueError('Недопустимые настройки голоса.')
        for p in (service.books/id).glob('*.mp3'):p.unlink()
        service.update(id,title=title,text=text,voice=voice,speed=speed,pause=pause,provider=provider,eleven_voice_id=eleven_voice_id,state='draft',total=0,done=0,error='');return {'ok':True}
    @app.post('/api/books/<id>/sample')
    def sample(id):
        book=book_or_404(id)
        if not book['text']:raise ValueError('Сначала дождитесь извлечения текста.')
        service.provider_ready(book)
        if book['provider']=='elevenlabs' and request.get_json().get('consent') is not True:raise ValueError('Подтвердите пробную озвучку через ElevenLabs: она тоже расходует лимит.')
        with service.db() as db:
            if db.execute('SELECT count(*) FROM books').fetchone()[0]>=40:raise ValueError('Удалите ненужные книги перед пробой голоса.')
        service.space();sample_id=secrets.token_hex(12);(service.books/sample_id).mkdir()
        with service.db() as db:db.execute('INSERT INTO books(id,title,source,text,state,voice,speed,pause,created,provider,eleven_voice_id) VALUES (?,?,?,?,?,?,?,?,?,?,?)',[sample_id,'Проба — '+book['title'],'Фрагмент',book['text'][:400],'queued',book['voice'],book['speed'],book['pause'],time.time(),book['provider'],book['eleven_voice_id']])
        return {'id':sample_id},201
    @app.post('/api/books/<id>/action')
    def action(id):
        book=book_or_404(id);command=request.get_json().get('action')
        if command=='pause' and book['state'] in ['queued','rendering']:service.update(id,state='paused');return {'ok':True}
        if command=='start' and book['state'] in ['draft','paused','error'] and book['text']:
            if service.working==id:return {'error':'Дождитесь завершения текущей части.'},409
            service.provider_ready(book)
            if book['provider']=='elevenlabs' and request.get_json().get('consent') is not True:raise ValueError('Подтвердите отправку текста в ElevenLabs и расход лимита.')
            service.space();service.update(id,state='queued',error='');return {'ok':True}
        return {'error':'Действие недоступно для текущего состояния книги.'},409
    @app.delete('/api/books/<id>')
    def remove(id):
        book=book_or_404(id)
        if service.working==id or book['state'] in ['uploaded','extracting','queued','rendering']:return {'error':'Остановите обработку и дождитесь завершения текущей части.'},409
        with service.db() as db:db.execute('DELETE FROM books WHERE id=?',[id])
        shutil.rmtree(service.books/id);return {'ok':True}
    @app.get('/api/books/<id>/audio/<part>')
    def audio(id,part):
        book=book_or_404(id)
        if part=='full':name='book.mp3'
        elif part.isdigit() and 0<=int(part)<book['total']:name=f'{int(part):05d}.mp3'
        else:from flask import abort;abort(404)
        path=service.books/id/name
        if not path.exists():from flask import abort;abort(404)
        return send_file(path,mimetype='audio/mpeg',conditional=True,as_attachment=request.args.get('download')=='1',download_name=book['title']+('.mp3' if part=='full' else ' — часть '+str(int(part)+1)+'.mp3'))
    if start_worker:
        app.worker_lock=worker_lock
        threading.Thread(target=service.run,daemon=True).start()
    return app

def main():
    parser=argparse.ArgumentParser();parser.add_argument('command',choices=['serve','password']);args=parser.parse_args();root=Path(os.getenv('DATA_DIR','/data'));root.mkdir(parents=True,exist_ok=True)
    if args.command=='password':
        first=getpass.getpass('Новый пароль библиотеки (минимум 12 символов): ');second=getpass.getpass('Повторите пароль: ')
        if len(first)<12 or first!=second:raise SystemExit('Пароли не совпадают или слишком короткие.')
        path=root/'password.json';path.write_text(json.dumps({'hash':generate_password_hash(first),'epoch':secrets.token_hex(16)}));path.chmod(0o600);print('Пароль сохранён.');return
    from waitress import serve
    serve(create_app(start_worker=True),host='0.0.0.0',port=int(os.getenv('PORT','8140')),threads=6)
if __name__=='__main__':main()
