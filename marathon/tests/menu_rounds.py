"""Isolated menu and repeat-round integration tests; no Telegram network calls."""
import http.cookiejar
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
import zipfile
ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
BASE='http://127.0.0.1:8106/api.php?action='
class Client:
    def __init__(self):self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf=''
    def call(self,action,data=None,status=200,suffix=''):
        req=urllib.request.Request(BASE+action+suffix,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        try:r=self.opener.open(req,timeout=20)
        except urllib.error.HTTPError as e:r=e
        with r:
            raw=r.read();assert r.status==status,(action,r.status,raw)
            return json.loads(raw) if 'json' in r.headers.get('Content-Type','') else raw
    def boot(self):result=self.call('bootstrap');self.csrf=result['csrf'];return result
with tempfile.TemporaryDirectory(prefix='marathon-menu-') as folder:
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2026-10-22',TELEGRAM_BOT_TOKEN='test-token',TELEGRAM_BOT_USERNAME='fixture_bot',APP_URL='https://example.test')
    server=subprocess.Popen([PHP,'-S','127.0.0.1:8106','-t',str(ROOT),str(ROOT/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        admin=Client()
        for _ in range(80):
            try:admin.boot();break
            except OSError:time.sleep(.1)
        admin.call('setup',{'name':'Admin','login':'admin','password':'test-password-2026'});admin.boot()
        uid=admin.call('create_user',{'name':'Repeat Reader','role':'participant'})['id']
        other=admin.call('create_user',{'name':'Other Reader','role':'participant'})['id']
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:db.execute("UPDATE users SET telegram_id='123456' WHERE id=?",(uid,))
        db.close()
        n=1000
        def bot(text='',callback=False,sender=123456):
            global n
            n+=1;message={'chat':{'type':'private','id':sender}}
            update={'update_id':n}
            if callback:update['callback_query']={'id':str(n),'from':{'id':sender},'message':message,'data':text}
            else:update['message']={**message,'from':{'id':sender},'text':text}
            code='require $argv[1];echo json_encode(telegramUpdate(json_decode(stream_get_contents(STDIN),true)),JSON_UNESCAPED_UNICODE);'
            result=json.loads(subprocess.check_output([PHP,'-r',code,str(ROOT/'lib/telegram.php')],input=json.dumps(update),env=env,text=True,encoding='utf-8'))
            for item in result:
                if item['method']=='sendMessage':assert len(item['args']['text'].encode())<=3500
            return result
        def messages(result):return '\n'.join(i['args'].get('text','') for i in result)
        def button(result,label):
            for item in result:
                for row in item['args'].get('reply_markup',{}).get('inline_keyboard',[]):
                    for b in row:
                        if label in b['text']:return b['callback_data']
            raise AssertionError((label,result))
        home=bot('/start');assert any('keyboard' in i['args'].get('reply_markup',{}) for i in home)
        for action in ['📊 Мой прогресс','📚 План недели','🗓 Мои недели','🔁 Круги чтения','❓ Помощь']:
            result=bot(action);assert messages(result) and 'Repeat Reader' not in messages(bot(action,sender=777777))
        assert 'example.test' in str(bot('🌐 Открыть сайт'))

        reader=Client();reader.boot();req=reader.call('telegram_request',{'kind':'login'});bot('a_'+req['token'],True);reader.call('telegram_status',{'token':req['token']});reader.boot()
        def profile(c=reader):return c.call('profile',suffix='&user='+uid)
        assert len(reader.boot()['marathon']['calendar'])==2
        assert len(profile()['stats']['reports'])==2 and len(profile(admin)['stats']['reports'])==22
        assert 'Неделя 3:' not in messages(bot('🗓 Мои недели'))
        reader.call('start_week_repeat',{'week':2,'cycle':1},400)
        reader.call('complete_week',{'week':3},400)
        admin.call('complete_week',{'user':uid,'week':1})
        first=bot('прочитал 7');confirm=button(first,'Подтвердить');assert profile()['stats']['pace']['chapters']==0
        bot(confirm,True);p=profile();assert p['stats']['progress']==100 and p['stats']['pace']['completed']
        assert p['stats']['goalWeeks']==2 and p['stats']['pace']['days']>=1
        prompt=bot('repeat:new',True);cancel=button(prompt,'Отмена');bot(cancel,True);assert profile()['stats']['pace']['cycle']==1
        prompt=bot('repeat:new',True);yes=button(prompt,'Начать повтор');bot(yes,True)
        p=profile();w=p['stats']['pace'];assert w['cycle']==2 and w['chapters']==0 and w['totalChapters']==7 and len(w['repeats'])==1
        assert w['start']=='2026-10-19' and w['end']=='2026-10-25' and p['marathon']['start']=='2026-10-12'
        assert p['stats']['reports'][0]['chapters']==7 and p['stats']['goalWeeks']==2 and p['stats']['progress']==0
        assert p['stats']['totalChapters']==14
        bot(yes,True);assert profile()['stats']['pace']['cycle']==2
        reader.call('week_result',{'week':2,'chapters':3,'cycle':1},409)
        preview=bot('прочитал 3');stale=button(preview,'Подтвердить')
        reader.call('week_result',{'week':2,'chapters':7,'cycle':2})
        reader.call('start_week_repeat',{'week':2,'cycle':2})
        bot(stale,True);assert profile()['stats']['pace']['chapters']==0
        assert profile()['stats']['pace']['cycle']==3 and len(profile()['stats']['pace']['repeats'])==2
        preview=bot('прочитал 3');bot(button(preview,'Подтвердить'),True)
        p=profile();assert p['stats']['pace']['chapters']==3 and p['stats']['progress']==43
        assert p['stats']['totalChapters']==24
        subprocess.run(['node',str(ROOT/'tests/render_weekly.cjs')],input=json.dumps(p),text=True,encoding='utf-8',check=True)
        assert '43%' in messages(bot('📊 Мой прогресс')) and 'круг 3' in messages(bot('📊 Мой прогресс'))
        admin.call('week_result',{'user':uid,'week':2,'cycle':3,'chapters':7,'days':2})
        p=profile();assert p['stats']['pace']['days']==2 and p['stats']['pace']['completedCycles']==3
        admin.call('start_week_repeat',{'user':uid,'week':2,'cycle':3})
        reader.call('start_week_repeat',{'week':2,'cycle':3},400)
        assert len(profile()['stats']['pace']['repeats'])==3
        assert profile()['stats']['pace']['repeats'][-1]['days']==2
        reader.call('week_result',{'week':2,'cycle':4,'chapters':2})
        reader.call('clear_week_result',{'week':2,'cycle':4})
        assert len(profile()['stats']['pace']['repeats'])==3 and profile()['stats']['pace']['totalChapters']==21
        # Weekly repeats are private and do not change another participant.
        assert profile(admin)['stats']['reports'][1]['cycle']==4
        assert admin.call('profile',suffix='&user='+other)['stats']['pace']['cycle']==1
        moderator=Client();moderator.boot();admin.call('create_user',{'name':'Mod','role':'moderator','login':'moderator','password':'mod-password-2026'});moderator.call('login',{'login':'moderator','password':'mod-password-2026'});assert len(moderator.boot()['marathon']['calendar'])==2
        assert len(moderator.call('overview')['marathon']['calendar'])==2
        moderator.call('export_xlsx',suffix='&week=3',status=400)
        workbook=moderator.call('export_xlsx',suffix='&week=2')
        with zipfile.ZipFile(io.BytesIO(workbook)) as z:assert 'Лука' not in z.read('xl/worksheets/sheet3.xml').decode()
        # Next calendar week starts at pass one; unfinished optional repeats do not steal chapters.
        env['MARATHON_TEST_TODAY']='2026-10-26'
        plan=bot('прочитал 2');assert 'Неделя 3' in messages(plan) and 'Неделя 2 ·' not in messages(plan)
        bot(button(plan,'Подтвердить'),True)
        assert 'Неделя 4:' not in messages(bot('🗓 Мои недели'))
        print('PASS: weekly repeats, history and days, unchanged calendar and other weeks, weekly progress, participant future privacy, confirmations, replay/stale guards, next-week reset.')
    finally:
        server.terminate();server.wait(timeout=5)
