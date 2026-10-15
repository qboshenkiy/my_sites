"""Isolated HTTP tests for weekly books, whole-plan completion and late marks."""
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
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
BASE='http://127.0.0.1:8104/'
class Client:
    def __init__(self):
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf=''
    def call(self, action, data=None, status=200, suffix=''):
        request=urllib.request.Request(BASE+'api.php?action='+action+suffix,
            data=json.dumps(data).encode() if data is not None else None,
            headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        try: response=self.opener.open(request, timeout=15)
        except urllib.error.HTTPError as error: response=error
        with response:
            raw=response.read()
            assert response.status==status,(action,response.status,raw)
            return json.loads(raw) if 'json' in response.headers.get('Content-Type','') else raw
    def boot(self):
        result=self.call('bootstrap');self.csrf=result['csrf'];return result

with tempfile.TemporaryDirectory(prefix='marathon-books-') as folder:
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2026-10-22',
             TELEGRAM_BOT_TOKEN='fake-test-token',TELEGRAM_BOT_USERNAME='fixture_bot')
    server=subprocess.Popen([PHP,'-S','127.0.0.1:8104','-t',str(ROOT),str(ROOT/'router.php')],
                            env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        admin=Client()
        for _ in range(60):
            try: admin.boot();break
            except urllib.error.URLError: time.sleep(.1)
        admin.call('setup',{'name':'Test Admin','login':'admin','password':'test-password-2026'});admin.boot()
        uid=admin.call('create_user',{'name':'Reader One','role':'participant'})['id']
        other=admin.call('create_user',{'name':'Reader Two','role':'participant'})['id']
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:
            db.execute('UPDATE users SET telegram_id=? WHERE id=?',('123456',uid))
        db.close()
        reader=Client();reader.boot();request=reader.call('telegram_request',{'kind':'login'})
        update={'update_id':1001,'callback_query':{'id':'callback','from':{'id':123456},'data':'a_'+request['token'],
                    'message':{'chat':{'type':'private','id':123456}}}}
        code='require $argv[1]; echo json_encode(telegramUpdate(json_decode(stream_get_contents(STDIN),true)));'
        subprocess.run([PHP,'-r',code,str(ROOT/'lib/telegram.php')],env=env,input=json.dumps(update),text=True,check=True,stdout=subprocess.DEVNULL)
        reader.call('telegram_status',{'token':request['token']});reader.boot()
        books=[{'title':'Матфей','chapter_from':1,'chapter_to':7},{'title':'Марк','chapter_from':1,'chapter_to':3}]
        admin.call('week_plan',{'week':2,'books':books})
        admin.call('week_plan',{'week':3,'books':[{'title':'Лука','chapter_from':1,'chapter_to':20}]})
        profile=reader.call('profile')['stats'];current=profile['pace']
        assert current['goal']==10 and len(current['books'])==2
        assert current['status']=='in_progress' and current['plannedByToday']==6 and current['daysLeft']==4
        assert profile['reports'][0]['status']=='overdue' and profile['reports'][2]['status']=='upcoming'
        reader.call('week_plan',{'week':2,'books':books},403)
        reader.call('complete_week',{'user':other,'week':2,'days':2},403)
        reader.call('complete_week',{'week':3,'days':1},400)
        reader.call('complete_week',{'week':2,'days':0},400)
        reader.call('complete_week',{'week':2,'days':5},400)
        admin.call('week_plan',{'week':2,'books':[{'title':'Same','chapter_from':1,'chapter_to':4},{'title':'Same','chapter_from':4,'chapter_to':7}]},400)
        reader.call('add_reading',{'chapters':3,'date':'2026-10-22','title':'Some reading','key':'first_daily_entry'})
        current=reader.call('profile')['stats']['pace'];assert current['chapters']==3 and current['perDay']==2
        result=reader.call('complete_week',{'week':2,'days':3})['week']
        assert result['chapters']==10 and result['days']==3 and result['actualPerDay']==3.33
        assert result['status']=='completed' and result['completedOn']=='2026-10-22'
        again=reader.call('complete_week',{'week':2,'days':1})['week']
        assert again['chapters']==10 and again['days']==3
        corrected=reader.call('week_result',{'week':2,'chapters':2,'days':2,'title':'Corrected total'})['week']
        assert corrected['chapters']==2 and corrected['chaptersDaily']==3 and corrected['days']==2
        assert corrected['actualPerDay']==1 and corrected['status']=='in_progress' and corrected['completedOn'] is None
        assert len(reader.call('profile')['stats']['entries'])==1, 'Weekly correction must preserve daily history'
        reader.call('week_result',{'week':2,'chapters':11,'days':2},400)
        reader.call('week_result',{'week':2,'chapters':3,'days':5},400)
        reader.call('week_result',{'user':other,'week':2,'chapters':3,'days':2},403)
        reader.call('clear_week_result',{'user':other,'week':2},403)
        reader.call('clear_week_result',{'week':3},400)
        cleared=reader.call('clear_week_result',{'week':2})['week']
        assert cleared['chapters']==0 and cleared['days']==0 and not cleared['recorded']
        assert not reader.call('profile')['stats']['entries']
        reader.call('week_result',{'week':2,'chapters':4,'days':2})
        reader.call('add_reading',{'chapters':1,'date':'2026-10-22','title':'Extra','key':'after_correction'})
        state=reader.call('profile')['stats'];assert state['pace']['chapters']==5
        entry=next(e for e in state['entries'] if e['title']=='Extra')
        reader.call('delete_reading',{'id':entry['id']})
        assert reader.call('profile')['stats']['pace']['chapters']==4
        reader.call('complete_week',{'week':2,'days':3})
        edited=reader.call('week_result',{'week':2,'chapters':10,'days':4})['week']
        assert edited['days']==4 and edited['actualPerDay']==2.5 and edited['completedOn']=='2026-10-22'
        reader.call('add_reading',{'chapters':1,'date':'2026-10-22','key':'no_more_chapters'},400)
        admin.call('week_plan',{'week':2,'books':[{'title':'Short','chapter_from':1,'chapter_to':9}]},400)
        assert reader.call('profile')['stats']['pace']['goal']==10
        admin.call('week_lock',{'week':1,'open':1})
        admin.call('week_plan',{'week':1,'books':books})
        admin.call('week_lock',{'week':1,'open':0})
        reader.call('add_reading',{'chapters':1,'date':'2026-10-15','key':'closed_daily_entry'},400)
        late=reader.call('complete_week',{'week':1,'days':9})['week']
        assert late['status']=='completed_late' and late['overdueDays']==4 and not late['editable']
        assert late['chapters']==10 and late['days']==9 and late['actualPerDay']==1.11
        assert len(late['completedBooks'])==2
        admin.call('week_result',{'user':uid,'week':1,'chapters':8},400)
        reader.call('week_result',{'week':1,'chapters':8,'days':3},400)
        reader.call('clear_week_result',{'week':1},400)
        export=admin.call('export_xlsx',suffix='&week=1')
        with zipfile.ZipFile(io.BytesIO(export)) as archive:
            assert archive.testzip() is None
            for file in archive.namelist():
                if file.endswith('.xml') or file.endswith('.rels'):ET.fromstring(archive.read(file))
            assert 'План чтения' in archive.read('xl/workbook.xml').decode()
            assert 'С опозданием' in archive.read('xl/worksheets/sheet1.xml').decode()
            assert 'Матфей' in archive.read('xl/worksheets/sheet3.xml').decode()
        admin.call('save_report',{'user':uid,'week':2,'pages':50,'minutes':20,'books':1,'title':'Legacy title','note':'Legacy note'})
        reader.call('clear_week_result',{'week':2})
        archive_stats=reader.call('profile')['stats']
        legacy=next(r for r in archive_stats['legacy']['reports'] if r['week']==2)
        assert archive_stats['pace']['chapters']==0 and archive_stats['legacy']['pages']==50
        assert legacy['title']=='Legacy title' and legacy['note']=='Legacy note'
        # Roles grant permissions without removing anyone from the reading roster.
        aid=admin.boot()['user']['id']
        reader.call('update_user',{'user':other,'name':'Forbidden'},403)
        reader.call('delete_user',{'user':other},403)
        reader.call('archived_users',status=403)
        admin.call('update_user',{'user':uid,'name':'Reader Moderator','role':'moderator'})
        assert reader.boot()['user']['role']=='moderator'
        roster=admin.call('overview')['users']
        assert {aid,uid,other}.issubset({u['id'] for u in roster})
        assert next(u for u in roster if u['id']==uid)['weekly'][0]['chapters']==10
        reader.call('week_result',{'week':2,'chapters':6,'days':2})
        admin.call('week_result',{'week':2,'chapters':4,'days':2})
        admin.call('update_user',{'user':uid,'role':'admin'})
        assert reader.call('profile')['stats']['pace']['chapters']==6
        exported=admin.call('export_xlsx',suffix='&week=2')
        with zipfile.ZipFile(io.BytesIO(exported)) as archive:
            sheet=archive.read('xl/worksheets/sheet1.xml').decode()
            assert 'Test Admin' in sheet and 'Reader Moderator' in sheet
        admin.call('update_user',{'user':aid,'name':'Renamed Admin'})
        assert admin.boot()['user']['name']=='Renamed Admin'
        admin.call('delete_user',{'user':aid},400)
        admin.call('update_user',{'user':aid,'active':0},400)
        admin.call('delete_user',{'user':uid})
        assert reader.boot()['user'] is None
        assert uid not in {u['id'] for u in admin.call('overview')['users']}
        assert admin.call('archived_users')['users'][0]['id']==uid
        admin.call('profile',suffix='&user='+uid,status=404)
        admin.call('update_user',{'user':uid,'name':'No edit of archive'},404)
        admin.call('restore_user',{'user':uid})
        assert reader.boot()['user'] is None, 'Old sessions must stay revoked after restoration'
        restored=admin.call('profile',suffix='&user='+uid)
        assert restored['user']['role']=='admin' and restored['stats']['pace']['chapters']==6
        assert restored['stats']['reports'][0]['chapters']==10
        assert not admin.call('archived_users')['users']
        # A fresh Telegram login succeeds, preserving the original binding.
        request=reader.call('telegram_request',{'kind':'login'})
        update['update_id']=1002;update['callback_query']['data']='a_'+request['token']
        subprocess.run([PHP,'-r',code,str(ROOT/'lib/telegram.php')],env=env,input=json.dumps(update),text=True,check=True,stdout=subprocess.DEVNULL)
        reader.call('telegram_status',{'token':request['token']})
        assert reader.boot()['user']['id']==uid
        print('PASS: role-independent reading, staff weekly editing, staff XLSX, account editing, archive/restore, permissions and session revocation.')
        print('PASS: weekly CRUD/corrections below daily totals, retained history, new readings after correction, reset, ownership/locks, books, manual days, late marks and XLSX.')
    finally:
        server.terminate();server.wait(timeout=10)
