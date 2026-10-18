"""Disposable HTTP/SQLite/UI test. Never calls a real AI API."""
import http.cookiejar,json,os,shutil,socket,sqlite3,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PHP='C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe' if os.name=='nt' else 'php'
with socket.socket() as s:s.bind(('127.0.0.1',0));PORT=s.getsockname()[1]
BASE=f'http://127.0.0.1:{PORT}'
class Client:
    def __init__(self):self.web=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf=''
    def call(self,action,data=None,status=200):
        r=urllib.request.Request(BASE+'/api.php?action='+action,data=json.dumps(data).encode() if data is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        try:response=self.web.open(r,timeout=8)
        except urllib.error.HTTPError as e:response=e
        with response:value=json.load(response);assert response.status==status,(action,response.status,value);return value
    def boot(self):value=self.call('state');self.csrf=value['csrf'];return value
with tempfile.TemporaryDirectory(prefix='sketch-test-') as tmp:
    process=subprocess.Popen([PHP,'-S',f'127.0.0.1:{PORT}','-t',str(ROOT)],env=dict(os.environ,DRAW_DATA_DIR=tmp,ADMIN_PASSWORD='test-admin-password',GAME_ACCESS_CODE='test-code-123',OPENAI_API_KEY='',APP_URL=BASE),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        a=Client()
        for _ in range(60):
            try:state=a.boot();break
            except OSError:time.sleep(.1)
        assert not state['player'] and len(state['categories'])==4 and not state['aiReady']
        a.call('join',{'name':'Иван','code':'wrong'},401)
        a.call('join',{'name':'Иван','code':'test-code-123'})
        a.call('category_save',{'title':'Nope','words':['x']},403)
        a.call('start',{'category':state['categories'][0]['id']});r=a.boot()['round']
        a.call('start',{'category':1},409)
        stranger=Client();stranger.boot();stranger.call('join',{'name':'Другой','code':'test-code-123'});stranger.call('skip',{'round':r['id']},404)
        a.call('judge',{'round':r['id'],'image':'fake'},422);assert not a.boot()['history']
        a.call('skip',{'round':r['id']});assert a.boot()['round'] is None
        a.call('admin_login',{'password':'test-admin-password'});assert a.boot()['admin']
        a.call('category_import',{'categories':[{'title':'Новая','words':['Дом','Окно']}]});assert len(a.boot()['categories'])==5
        a.call('category_import',{'categories':[{'title':'Не сохранится','words':['Дом']},{'title':'Ошибка','words':[]}]},422);assert len(a.boot()['categories'])==5
        cat=a.boot()['categories'][-1];a.call('category_save',{'id':cat['id'],'title':'Архитектура','words':['Дом']});assert a.boot()['categories'][-1]['title']=='Архитектура'
        a.call('category_delete',{'id':cat['id']});assert len(a.boot()['categories'])==4
        a.csrf='bad';a.call('logout',{},403);a.boot()
        if os.environ.get('SKETCH_UI')=='1':
            subprocess.run(['node',str(ROOT/'tests/mobile.cjs'),BASE],env=os.environ,check=True)
        print('PASS: isolated SQLite, login, CSRF, category CRUD/import atomicity, round ownership, no fabricated AI scores')
    finally:process.terminate();process.wait(timeout=5)
