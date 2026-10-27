from pathlib import Path
import http.cookiejar
import datetime as dt
from zoneinfo import ZoneInfo
import json
import sys
import tempfile
import time
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Application, Handler, password_hash, TelegramError
from core import Store
import http.server

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite')
        with self.store.db() as db:self.store.put(db,'password_hash',password_hash('testing-password-123'))
        self.sent=[]
        def fake(token,method,args=None):
            if method=='sendMessage':self.sent.append(args)
            if method=='getMe':return {'id':123,'is_bot':True,'username':'milk_test_bot'}
            if method=='getWebhookInfo':return {'url':''}
            return True
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),Handler)
        self.server.app=Application(self.store,fake)
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.base='http://127.0.0.1:'+str(self.server.server_port)
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf=''
    def tearDown(self):
        self.server.shutdown();self.server.server_close();self.tmp.cleanup()
    def request(self,path,data=None,status=200,headers=None):
        h={'Origin':self.base,'Content-Type':'application/json','X-CSRF-Token':self.csrf};h.update(headers or {})
        req=urllib.request.Request(self.base+path,data=json.dumps(data).encode() if data is not None else None,headers=h)
        try:r=self.client.open(req)
        except urllib.error.HTTPError as e:r=e
        with r:
            body=json.load(r);self.assertEqual(r.status,status,body);return body
    def login(self):self.csrf=self.request('/api/login',{'password':'testing-password-123'})['csrf']
    def test_auth_csrf_and_person_flow(self):
        self.request('/api/state',status=401)
        self.request('/api/login',{'password':'wrong'},401)
        self.login()
        self.request('/api/people/add',{'name':'Анна'},403,{'Origin':'https://evil.test'})
        self.request('/api/people/add',{'name':'Анна'},403,{'X-CSRF-Token':'bad'})
        self.request('/api/bot',{'token':'123:secret'})
        self.request('/api/people/add',{'name':'Анна'})
        state=self.request('/api/state');self.assertEqual(state['people'][0]['name'],'Анна')
        self.assertTrue(state['people'][0]['invite_url'].startswith('https://t.me/milk_test_bot?start=join_'))
        self.assertNotIn('123:secret',json.dumps(state))
        self.request('/api/people/update',{'id':1,'action':'rename','name':'Аня'})
        self.assertEqual(self.request('/api/state')['people'][0]['name'],'Аня')
        self.request('/api/logout',{})
        self.request('/api/state',status=401)
    def test_manual_reminder_works_on_pause_and_repeated_request_is_idempotent(self):
        self.login()
        self.request('/api/bot',{'token':'123:secret'})
        self.request('/api/people/add',{'name':'Анна'})
        with self.store.db() as db:
            token=db.execute('SELECT invite FROM people WHERE id=1').fetchone()[0]
        self.store.join(token,12345)
        day=dt.datetime.now(ZoneInfo('Asia/Bishkek')).date()+dt.timedelta(days=1)
        while day.weekday()>4:day+=dt.timedelta(days=1)
        body={'day':day.isoformat(),'request_id':'manual-request-12345678'}
        self.request('/api/remind',body,403,{'X-CSRF-Token':'bad'})
        result=self.request('/api/remind',body)
        self.assertTrue(result['ok']);self.assertEqual(result['name'],'Анна')
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.sent[0]['chat_id'],12345)
        self.assertIn(day.strftime('%d.%m.%Y'),self.sent[0]['text'])
        self.request('/api/remind',body)
        self.assertEqual(len(self.sent),1)
        state=self.request('/api/state');self.assertFalse(state['settings']['enabled'])
        self.assertEqual(state['logs'][0]['status'],'sent')
        self.assertTrue(state['logs'][0]['kind'].startswith('manual-'))
        self.request('/api/remind',{'day':day.isoformat(),'request_id':'bad'},400)
        self.request('/api/remind',{'day':'2020-01-01','request_id':'manual-past-12345678'},400)

    def test_manual_retry_runs_even_with_automatic_sends_paused(self):
        self.login();self.request('/api/bot',{'token':'123:secret'})
        self.request('/api/people/add',{'name':'Анна'})
        with self.store.db() as db:
            token=db.execute('SELECT invite FROM people WHERE id=1').fetchone()[0]
        self.store.join(token,12345)
        day=dt.datetime.now(ZoneInfo('Asia/Bishkek')).date()+dt.timedelta(days=1)
        while day.weekday()>4:day+=dt.timedelta(days=1)
        original=self.server.app.transport
        def unavailable(*args):raise TelegramError(429,30)
        self.server.app.transport=unavailable
        result=self.request('/api/remind',{'day':day.isoformat(),'request_id':'manual-retry-12345678'})
        self.assertFalse(result['ok']);self.assertEqual(result['status'],'retry')
        self.server.app.transport=original
        self.server.app.deliver(time.time()+31)
        self.assertEqual(len(self.sent),1)
        self.assertEqual(self.request('/api/state')['logs'][0]['status'],'sent')

    def test_manual_reminder_without_bot_is_not_a_success(self):
        self.login()
        day=dt.datetime.now(ZoneInfo('Asia/Bishkek')).date().isoformat()
        self.request('/api/remind',{'day':day,'request_id':'manual-request-12345678'},400)
        self.assertEqual(self.sent,[])

    def test_password_change_revokes_session(self):
        self.login();self.request('/api/password',{'current':'bad','password':'new-password-123'},400)
        self.request('/api/password',{'current':'testing-password-123','password':'new-password-123'})
        self.request('/api/state',status=401)
        self.request('/api/login',{'password':'testing-password-123'},401)
        self.csrf=self.request('/api/login',{'password':'new-password-123'})['csrf']
        self.request('/api/state')
    def test_cannot_enable_unconnected_queue(self):
        self.login();self.request('/api/people/add',{'name':'Анна'})
        cfg=self.request('/api/state')['settings'];cfg['enabled']=True
        self.request('/api/settings',cfg,400)

if __name__=='__main__':unittest.main()
