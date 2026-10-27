from pathlib import Path
import http.cookiejar
import json
import sys
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from app import Application, Handler, password_hash
from core import Store
import http.server

class HttpTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.store=Store(Path(self.tmp.name)/'db.sqlite')
        with self.store.db() as db:self.store.put(db,'password_hash',password_hash('testing-password-123'))
        def fake(token,method,args=None):
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
