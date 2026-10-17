"""Real HTTP + signed Telegram fixtures; no calls to a real bot or production database."""
import hashlib
import hmac
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
TOKEN='123456:miniapp-test-token-never-real'
def proof(uid=101,age=0,token=TOKEN,extra=None,user=None):
    fields={'auth_date':str(int(time.time())-age),'query_id':'fixture_query','user':json.dumps(user if user is not None else {'id':uid,'first_name':'Reader'},ensure_ascii=False,separators=(',',':'))}
    fields.update(extra or {})
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    fields['hash']=hmac.new(secret,'\n'.join(f'{k}={fields[k]}' for k in sorted(fields)).encode(),hashlib.sha256).hexdigest()
    return urllib.parse.urlencode(fields)

with tempfile.TemporaryDirectory(prefix='marathon-miniapp-') as folder:
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2026-10-22',TELEGRAM_BOT_TOKEN=TOKEN,TELEGRAM_BOT_USERNAME='fixture_bot',APP_URL='https://vano.sbena.net')
    def php(code,body=''):
        return json.loads(subprocess.check_output([PHP,'-r','require $argv[1];'+code,str(ROOT/'lib/telegram.php')],input=body,text=True,encoding='utf-8',env=env))
    php("""db();foreach([['reader','Reader','participant','101',1,null],['admin','Admin','admin','202',1,null],['inactive','Inactive','participant','303',0,null],['deleted','Deleted','participant','404',0,time()]] as $u)sql('INSERT INTO users(id,name,role,telegram_id,active,deleted_at,created_at) VALUES (?,?,?,?,?,?,?)',array_merge($u,[time()]));echo '{}';""")
    cookie=php("$_SERVER['HTTPS']='on';$_SERVER['HTTP_X_MARATHON_MINIAPP']='1';sessionStart();echo json_encode(session_get_cookie_params());")
    assert cookie['secure'] is True and cookie['httponly'] is True and cookie['samesite']=='None'
    # The bot uses inline/menu launch mode, not keyboard-button web_app without initData.
    result=php("echo json_encode(telegramUpdate(['update_id'=>100,'message'=>['from'=>['id'=>101],'chat'=>['id'=>101,'type'=>'private'],'text'=>'/app']]));")
    launch=next(r['args']['reply_markup']['inline_keyboard'][0][0] for r in result if r['method']=='sendMessage')
    assert launch['web_app']['url']=='https://vano.sbena.net/index.php?miniapp=1'
    assert php("putenv('APP_URL=http://vano.sbena.net:8081');echo json_encode(telegramMiniAppUrl());") is None
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    base=f'http://127.0.0.1:{port}/'
    class Client:
        def __init__(self):
            self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf=''
        def call(self,action,data=None,status=200,csrf=True):
            headers={'Content-Type':'application/json'}
            if csrf:headers['X-CSRF-Token']=self.csrf
            request=urllib.request.Request(base+'api.php?action='+action,data=json.dumps(data).encode() if data is not None else None,headers=headers)
            try:response=self.opener.open(request,timeout=10)
            except urllib.error.HTTPError as error:response=error
            with response:
                body=response.read();assert response.status==status,(action,response.status,body)
                return json.loads(body)
        def boot(self):
            b=self.call('bootstrap');self.csrf=b['csrf'];return b
    with open(Path(folder)/'http.log','w',encoding='utf-8') as log:
        server=subprocess.Popen([PHP,'-S',f'127.0.0.1:{port}','-t',str(ROOT),str(ROOT/'router.php')],env=env,stdout=log,stderr=log)
        try:
            reader=Client()
            for _ in range(50):
                try:reader.boot();break
                except urllib.error.URLError:time.sleep(.1)
            assert reader.boot()['telegram']['miniapp_url'].endswith('index.php?miniapp=1')
            reader.call('telegram_miniapp_login',{'init_data':proof()},403,csrf=False)
            reader.call('telegram_miniapp_login',{'init_data':proof()})
            assert reader.boot()['user']['id']=='reader'
            previous_csrf=reader.csrf;reader.call('telegram_miniapp_login',{'init_data':proof()});reader.boot()
            assert reader.csrf==previous_csrf  # re-opening does not invalidate another tab
            reader.call('add_reading',{'chapters':3,'date':'2026-10-22','title':'Book','key':'miniapp_entry_1'})
            assert reader.call('profile')['stats']['pace']['chapters']==3
            reader.call('overview',status=403)
            reader.call('telegram_miniapp_login',{'init_data':proof(user={'id':101,'role':'admin','first_name':'Forged role'})})
            assert reader.boot()['user']['role']=='participant'
            assert reader.call('profile')['stats']['pace']['chapters']==3
            invalid=[proof(age=3700),proof(age=-120),proof(token='wrong-token'),proof(user={'id':'101'}),proof(user={'id':-1}),proof(user={'id':101,'is_bot':True}),proof(user=[]),proof()+'&user=duplicate',proof()+'&hash=duplicate',proof().replace('101','202'),proof()+'%ZZ','x'*20000,'{}']
            for value in invalid:
                guest=Client();guest.boot();guest.call('telegram_miniapp_login',{'init_data':value},400);guest.call('profile',status=401)
            for uid in [303,404,999]:
                guest=Client();guest.boot();guest.call('telegram_miniapp_login',{'init_data':proof(uid)},403);guest.call('profile',status=401)
            # Newer Telegram adds a signature field: HMAC covers all fields except hash.
            reader.call('telegram_miniapp_login',{'init_data':proof(extra={'signature':'fixture_signature'})})
            reader.boot()
            # Always switch to the verified Telegram identity, even if another account had a cookie.
            reader.call('telegram_miniapp_login',{'init_data':proof(202)})
            assert reader.boot()['user']['role']=='admin'
            history=reader.call('audit')['events']
            assert any(e['event']=='telegram_miniapp_login' for e in history)
            assert any(e['event']=='reading' and e['metadata'].get('channel')=='miniapp' for e in history)
            assert TOKEN not in json.dumps(history) and 'fixture_signature' not in json.dumps(history)
            reader.call('telegram_miniapp_login',{'init_data':proof()})
            assert reader.boot()['user']['id']=='reader'
            with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:db.execute("UPDATE users SET active=0,session_epoch=session_epoch+1 WHERE id='reader'")
            db.close();assert reader.boot()['user'] is None
            reader.call('telegram_miniapp_login',{'init_data':proof()},403)
            with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:db.execute("UPDATE users SET active=1 WHERE id='reader'")
            db.close()
            assert php('echo json_encode(sql("SELECT COUNT(*) FROM users")->fetchColumn());')==4
            if os.environ.get('MINIAPP_UI')=='1':
                subprocess.run(['node',str(ROOT/'tests/miniapp_ui.cjs')],env=dict(env,MINIAPP_TEST_URL=base,MINIAPP_PROOF=proof()),check=True,timeout=60)
            print('PASS: Mini App HMAC/expiry/CSRF/duplicates, signed identity and role isolation, linked/disabled/deleted accounts, cookie identity switch, real reading API, audit privacy and inline bot launch')
        finally:server.terminate();server.wait(timeout=10)
