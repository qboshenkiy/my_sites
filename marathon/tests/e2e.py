import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
EXTERNAL=os.environ.get('MARATHON_TEST_BASE')
BASE=EXTERNAL or 'http://127.0.0.1:8098/'

class Client:
    def __init__(self):
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf=''
    def call(self,action,payload=None,expected=200,suffix=''):
        req=urllib.request.Request(BASE+'api.php?action='+action+suffix,data=json.dumps(payload).encode() if payload is not None else None,
            headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        try: r=self.opener.open(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        data=json.loads(r.read());assert r.status==expected,(action,r.status,data);return data
    def boot(self):
        data=self.call('bootstrap');self.csrf=data['csrf'];return data

counter=100
def bot(update,env):
    # Execute only the pure update handler; never send data to real Telegram.
    if EXTERNAL:
        proc=subprocess.run(['docker','exec','-i',os.environ['MARATHON_TEST_CONTAINER'],'php','-r',
             'require "/var/www/html/lib/telegram.php"; echo json_encode(telegramUpdate(json_decode(stream_get_contents(STDIN),true)),JSON_UNESCAPED_UNICODE);'],
             input=json.dumps(update),text=True,capture_output=True)
    else:
        proc=subprocess.run([PHP,'-r','require "'+str(ROOT/'lib/telegram.php').replace('\\','/')+'"; echo json_encode(telegramUpdate(json_decode(stream_get_contents(STDIN),true)),JSON_UNESCAPED_UNICODE);'],
             input=json.dumps(update),env=env,text=True,capture_output=True)
    assert proc.returncode==0,proc.stderr
    return json.loads(proc.stdout)

def approve(token,kind,telegram_id,env):
    global counter
    counter+=1
    chat={'id':telegram_id,'type':'private'}
    sender={'id':telegram_id,'is_bot':False,'first_name':'Test','username':'test_reader'}
    start={'update_id':counter,'message':{'from':sender,'chat':chat,'text':'/start '+kind+'_'+token}}
    result=bot(start,env)
    assert result and result[0]['args'].get('reply_markup'),result
    counter+=1
    callback={'update_id':counter,'callback_query':{'id':str(counter),'from':sender,'message':{'chat':chat},'data':kind+'_'+token}}
    result=bot(callback,env)
    assert len(result)>=2,result
    assert bot(callback,env)==[],'Duplicate Telegram update must be ignored'

with tempfile.TemporaryDirectory(prefix='glava-test-') as data_dir:
    env=dict(os.environ,MARATHON_DATA_DIR=data_dir,TELEGRAM_BOT_TOKEN='test-token-not-real',TELEGRAM_BOT_USERNAME='fixture_bot',APP_URL='https://example.com')
    server=None if EXTERNAL else subprocess.Popen([PHP,'-S','127.0.0.1:8098','-t',str(ROOT),str(ROOT/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        admin,mod,reader,other=Client(),Client(),Client(),Client()
        for _ in range(60):
            try:b=admin.boot();break
            except urllib.error.URLError:time.sleep(.1)
        else:raise AssertionError('Server unavailable')
        assert not b['configured']
        assert b['marathon']['start']=='2026-10-12' and b['marathon']['end']=='2027-03-14'
        assert len(b['marathon']['calendar'])==22
        other.call('overview',expected=401)
        other.call('create_user',{},expected=403)
        admin.call('setup',{'login':'admin','password':'test-password-123','name':'Администратор'})
        admin.boot()
        admin.call('setup',{'login':'other','password':'test-password-123'},expected=409)
        mod_id=admin.call('create_user',{'name':'Модератор','role':'moderator','login':'moderator','password':'mod-password-123'})['id']
        mod.boot();mod.call('login',{'login':'moderator','password':'mod-password-123'});mod.boot()
        uid=mod.call('create_user',{'name':'Анна <Тест>','role':'participant'})['id']
        second=admin.call('create_user',{'name':'Борис','role':'participant'})['id']
        mod.call('create_user',{'name':'Bad','role':'admin','login':'badadmin','password':'test-password-123'},expected=403)
        mod.call('settings',{'title':'Bad','goal':10},expected=403)
        week=min(22,b['marathon']['current'])
        assert week>0,'Test expects marathon to have started'
        mod.call('save_report',{'user':uid,'week':week,'pages':120,'minutes':90,'books':1,'title':'Книга','note':'Комментарий'})
        mod.call('save_report',{'user':uid,'week':week,'pages':150,'minutes':100,'books':1})
        mod.call('save_report',{'user':uid,'week':week,'pages':-1},expected=400)
        if week<22:mod.call('save_report',{'user':uid,'week':week+1,'pages':100},expected=400)
        profile=admin.call('profile',suffix='&user='+uid)
        assert profile['stats']['legacy']['pages']==150 and profile['stats']['recorded']==1
        invite=mod.call('telegram_request',{'kind':'invite','user':uid})
        approve(invite['token'],'i',555000111,env)
        assert admin.call('profile',suffix='&user='+uid)['user']['telegram_id']=='555000111'
        reader.boot();req=reader.call('telegram_request',{'kind':'login'})
        assert reader.call('telegram_status',{'token':req['token']})['pending']
        other.boot();other.call('telegram_status',{'token':req['token']},expected=400)
        approve(req['token'],'a',555000111,env)
        reader.call('telegram_status',{'token':req['token']});r=reader.boot()
        assert r['user']['id']==uid and r['user']['role']=='participant'
        assert reader.call('profile')['stats']['legacy']['pages']==150
        reader.call('profile',suffix='&user='+second,expected=403)
        reader.call('overview',expected=403)
        reader.call('audit',expected=403)
        reader.call('export',expected=403)
        reader.call('save_report',{'user':uid,'week':week,'pages':9999},expected=403)
        reader.call('telegram_status',{'token':req['token']},expected=400)
        assert 'password' not in r['user']
        assert 'password' not in admin.call('overview')['users'][0]
        assert mod.call('audit')['events']
        admin.call('update_user',{'user':uid,'active':0})
        assert reader.boot()['user'] is None
        reader.call('profile',expected=401)
        admin.call('update_user',{'user':uid,'active':1})
        admin.call('settings',{'title':'Наш марафон','goal':200})
        admin.call('week_plan',{'week':week,'goal':200})
        assert admin.boot()['marathon']['goal']==200
        # Protected application and data directories are inaccessible over HTTP.
        for path in ['storage/marathon.sqlite','lib/core.php','.env','tools/bot.php']:
            try:other.opener.open(BASE+path);raise AssertionError(path+' is public')
            except urllib.error.HTTPError as e:assert e.code in (403,404)
        print('PASS: 22-week dates, staff roles, weekly reports, idempotent edits, Telegram invitation and login, replay/session protection, participant privacy, disabled accounts and audit log.')
    finally:
        if server:server.terminate();server.wait(timeout=10)
