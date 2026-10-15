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
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2027-03-16',TELEGRAM_BOT_TOKEN='test-token',TELEGRAM_BOT_USERNAME='fixture_bot',APP_URL='https://example.test')
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
        locked=bot('circle:new',True);assert '22' in messages(locked)
        reader=Client();reader.boot();req=reader.call('telegram_request',{'kind':'login'});bot('a_'+req['token'],True);reader.call('telegram_status',{'token':req['token']});reader.boot()
        admin.call('week_lock',{'week':1,'open':1});admin.call('week_plan',{'week':1,'books':[{'title':'Матфей','chapter_from':1,'chapter_to':7}]});admin.call('week_lock',{'week':1,'open':0})
        pending=bot('прочитал 3');old_confirm=button(pending,'Подтвердить')
        # Fixture completed first round; no production data is modified.
        calendar=reader.call('profile')['marathon']
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:
            for week in calendar['calendar']:
                db.execute('INSERT INTO reports(user_id,week,chapters_override,days_manual,editor_id,updated_at) VALUES (?,?,?,?,?,?)',(uid,week['number'],week['goal'],7,uid,int(time.time())))
                db.execute('INSERT INTO week_completions(user_id,week,completed_on) VALUES (?,?,?)',(uid,week['number'],week['end']))
        db.close()
        before=reader.call('profile');assert before['stats']['goalWeeks']==22
        circles=bot('🔁 Круги чтения');assert 'Начать круг 2' in str(circles)
        confirmation=bot(button(circles,'Начать круг 2'),True)
        bot(button(confirmation,'Отмена'),True);assert reader.call('profile')['marathon']['round']==1
        confirmation=bot('circle:new',True);start_button=button(confirmation,'Начать новый круг')
        bot(start_button,True,sender=777777);assert reader.call('profile')['marathon']['round']==1
        started=bot(start_button,True);assert 'Круг 2 начат' in messages(started)
        bot(start_button,True)
        second=reader.call('profile');assert second['marathon']['round']==2 and second['marathon']['start']=='2027-03-16' and second['marathon']['current']==1
        assert second['stats']['chapters']==0 and second['stats']['goalWeeks']==0 and second['user']['telegram_id']=='123456'
        assert second['stats']['pace']['books'][0]['title']=='Матфей'
        assert admin.call('profile',suffix='&user='+other)['marathon']['round']==1
        history=reader.call('round_history',suffix='&round=1');assert history['stats']['chapters']==154 and history['stats']['goalWeeks']==22 and 'raw' not in history
        assert '154' in messages(bot('circle:1',True))
        reader.call('round_history',suffix='&round=1&user='+other,status=403)
        reader.call('week_result',{'week':1,'chapters':2,'round':1},409)
        reader.call('week_result',{'week':1,'chapters':2},409)
        assert 'недоступно' in messages(bot(old_confirm,True))
        admin.call('week_lock',{'week':1,'open':1});admin.call('week_plan',{'week':1,'books':[{'title':'Changed Global','chapter_from':1,'chapter_to':9}]})
        assert reader.call('profile')['stats']['pace']['goal']==7, 'Round plan is a frozen copy, unaffected by first-round edits'
        prompt=bot('📖 Отметить чтение');assert 'от 1 до 7' in messages(prompt)
        preview=bot('3');assert 'Пока ничего не зачтено' in messages(preview)
        assert reader.call('profile')['stats']['chapters']==0
        bot(button(preview,'Подтвердить'),True)
        assert reader.call('profile')['stats']['chapters']==3
        bot('📖 Отметить чтение');bot('Отмена');bot('2')
        assert reader.call('profile')['stats']['chapters']==3
        quick=bot('amount:1',True);bot(button(quick,'Подтвердить'),True)
        assert reader.call('profile')['stats']['chapters']==4
        reader.call('week_result',{'round':2,'week':1,'chapters':2})
        assert reader.call('profile')['stats']['chapters']==2
        admin.call('week_result',{'user':uid,'round':2,'week':1,'chapters':5,'days':1})
        assert reader.call('profile')['stats']['chapters']==5
        bot('📖 Отметить чтение');wrong_number=bot('2');correct_number=bot('1')
        bot(button(wrong_number,'Подтвердить'),True)
        assert reader.call('profile')['stats']['chapters']==5
        bot(button(correct_number,'Подтвердить'),True)
        assert reader.call('profile')['stats']['chapters']==6
        roster=admin.call('overview')['users'];assert next(u for u in roster if u['id']==uid)['round']==2
        assert reader.call('round_history',suffix='&round=1')['stats']['chapters']==154
        reader.call('start_round',{'round':2},400)
        reader.call('complete_week',{'round':2,'week':2},400)
        export=admin.call('export_xlsx',suffix='&week=1')
        with zipfile.ZipFile(io.BytesIO(export)) as z:
            sheet=z.read('xl/worksheets/sheet1.xml').decode();assert 'Круг' in sheet and '2027-03-16' in sheet
            plans=z.read('xl/worksheets/sheet3.xml').decode();assert 'Круг 2' in plans and 'Матфей' in plans and '2027-03-16' in plans
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:
            archived=db.execute('SELECT snapshot FROM reading_rounds WHERE user_id=? AND number=1',(uid,)).fetchone()[0]
            assert len(json.loads(archived)['raw']['reports'])==22
            db.execute("UPDATE reading_rounds SET start='2027-03-08' WHERE user_id=? AND number=2",(uid,))
        db.close()
        admin.call('week_result',{'user':uid,'round':2,'week':1,'chapters':6},400)
        admin.call('week_lock',{'user':uid,'round':2,'week':1,'open':1})
        admin.call('week_result',{'user':uid,'round':2,'week':1,'chapters':6,'days':2})
        assert reader.call('profile')['stats']['reports'][0]['chapters']==6
        print('PASS: persistent Telegram menu, numeric/quick entry, cancellation, private progress, confirmed new round, immutable history, personal dates, frozen plans, stale requests, staff edits/locks and XLSX round metadata.')
    finally:server.terminate();server.wait(timeout=10)
