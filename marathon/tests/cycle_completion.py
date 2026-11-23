"""Regression checks against an isolated database and local HTTP server."""
import http.cookiejar
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

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php')
BASE='http://127.0.0.1:8113/api.php?action='
class Client:
    def __init__(self):
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf=''
    def call(self,action,data=None,status=200,suffix=''):
        req=urllib.request.Request(BASE+action+suffix,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        try:response=self.opener.open(req,timeout=15)
        except urllib.error.HTTPError as error:response=error
        with response:
            raw=response.read();assert response.status==status,(action,response.status,raw)
            return json.loads(raw)
    def boot(self):self.csrf=self.call('bootstrap')['csrf']

with tempfile.TemporaryDirectory(prefix='marathon-correction-') as folder:
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2026-10-22')
    server=subprocess.Popen([PHP,'-S','127.0.0.1:8113','-t',str(ROOT),str(ROOT/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        admin=Client()
        for _ in range(60):
            try:admin.boot();break
            except OSError:time.sleep(.1)
        admin.call('setup',{'name':'Admin','login':'admin','password':'test-password-2026'});admin.boot()
        uid=admin.call('create_user',{'name':'Reader','role':'participant'})['id']
        admin.call('create_user',{'name':'Mod','role':'moderator','login':'moderator','password':'test-password-2026'})
        mod=Client();mod.boot();mod.call('login',{'login':'moderator','password':'test-password-2026'});mod.boot()
        def week(n=2):return admin.call('profile',suffix='&user='+uid)['stats']['reports'][n-1]
        def remove(cycle,expected=None):return admin.call('delete_week_cycle',{'user':uid,'week':2,'cycle':cycle,'active_cycle':cycle if expected is None else expected})['week']
        # Removing the last pass does not generate an endless sequence of replacements.
        w=remove(1);assert w['cycle']==0 and w['chapters']==0 and len(w['deletedRepeats'])==1
        for _ in range(3):
            admin.call('delete_week_cycle',{'user':uid,'week':2,'cycle':1,'active_cycle':0},400)
            assert week()['cycle']==0 and len(week()['deletedRepeats'])==1
        admin.call('restore_week_cycle',{'user':uid,'week':2,'cycle':1,'active_cycle':0})
        assert week()['cycle']==1 and not week()['deletedRepeats'] and not week()['repeats']
        remove(1)
        admin.call('week_result',{'user':uid,'week':2,'cycle':1,'chapters':2},409)
        w=admin.call('week_result',{'user':uid,'week':2,'cycle':0,'chapters':2})['week']
        assert w['cycle']==2 and w['chapters']==2
        remove(2)
        w=admin.call('start_week_repeat',{'user':uid,'week':2,'cycle':0})['week']
        assert w['cycle']==3 and not w['repeats'] and len(w['deletedRepeats'])==2
        admin.call('complete_week',{'user':uid,'week':2,'cycle':3})
        admin.call('start_week_repeat',{'user':uid,'week':2,'cycle':3})
        assert remove(4)['cycle']==3 and week()['chapters']==week()['goal']
        assert remove(3)['cycle']==0
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:
            db.execute('UPDATE weekly_cycle_state SET cycle=5 WHERE user_id=? AND week=2',(uid,))
            db.execute('DELETE FROM migrations WHERE version=6')
        subprocess.run([PHP,'-r','require $argv[1];db();',str(ROOT/'lib/core.php')],env=env,check=True)
        assert week()['cycle']==0 and len(week()['deletedRepeats'])==4
        # A closed past week can be completed/corrected by admin without reopening it.
        p={'user':uid,'week':1,'cycle':1,'completed_on':'2026-10-18'}
        assert not week(1)['editable']
        mod.call('correct_week_completion',p,403)
        for date in ('2026-10-11','2026-10-23','2026-02-30'):
            admin.call('correct_week_completion',{**p,'completed_on':date},400)
        late=admin.call('complete_week',{'user':uid,'week':1})['week'];assert late['late']
        fixed=admin.call('correct_week_completion',p)['week']
        assert fixed['completedOn']=='2026-10-18' and fixed['status']=='completed' and not fixed['late'] and fixed['days']==7
        assert not week(1)['editable'] and fixed['overdueDays']==0
        late=admin.call('correct_week_completion',{**p,'completed_on':'2026-10-20'})['week']
        assert late['late'] and late['overdueDays']==2 and late['days']==9
        admin.call('correct_week_completion',p)
        # Preserve daily entries and the corrected date on later ordinary edits.
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:
            db.execute('INSERT INTO reading_entries VALUES (?,?,?,?,?,?,?,?,?,?)',('daily',uid,1,'2026-10-17',1,'','',uid,'site',int(time.time())))
        admin.call('correct_week_completion',p)
        assert len(admin.call('profile',suffix='&user='+uid)['stats']['entries'])==1
        admin.call('week_lock',{'week':1,'open':True})
        w=week(1)
        admin.call('week_result',{'user':uid,'week':1,'cycle':1,'chapters':w['goal'],'note':'Comment'})
        assert week(1)['completedOn']=='2026-10-18' and not week(1)['late']
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:
            assert db.execute("SELECT COUNT(*) FROM audit WHERE event='correct_week_completion'").fetchone()[0]>=4
        if os.getenv('MARATHON_TEST_UI')=='1':
            admin.call('week_lock',{'week':1,'open':0})
            subprocess.run(['node',str(ROOT/'tests/completion_ui.cjs')],env=dict(env,MARATHON_COMPLETION_URL='http://127.0.0.1:8113/',MARATHON_COMPLETION_USER=uid),check=True)
        print('PASS: last-pass deletion, restoration, explicit restart, stale requests, administrator-only backdated completion, closed weeks, preserved entries and audit.')
    finally:server.terminate();server.wait(timeout=10)
