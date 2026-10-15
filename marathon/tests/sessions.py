"""Verify persistent login across process/container filesystem replacement and browser restart."""
import copy
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
BASE='http://127.0.0.1:8105/api.php?action='
with tempfile.TemporaryDirectory(prefix='marathon-sessions-') as folder:
    data=Path(folder)/'data'
    env=dict(os.environ,MARATHON_DATA_DIR=str(data))
    jar=http.cookiejar.MozillaCookieJar(str(Path(folder)/'browser-cookies.txt'))
    def client(cookies):return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
    browser=client(jar)
    def call(action,body=None,csrf=''):
        req=urllib.request.Request(BASE+action,data=json.dumps(body).encode() if body is not None else None,
            headers={'Content-Type':'application/json','X-CSRF-Token':csrf})
        with browser.open(req,timeout=10) as response:return json.load(response)
    def start(name):
        runtime=Path(folder)/name;runtime.mkdir()
        process=subprocess.Popen([PHP,'-d','session.save_path='+str(runtime),'-d','session.gc_maxlifetime=1',
            '-S','127.0.0.1:8105','-t',str(ROOT),str(ROOT/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        for _ in range(60):
            try:return process,call('bootstrap')
            except OSError:time.sleep(.1)
        raise AssertionError('Server did not start')
    server,boot=start('container-one')
    try:
        call('setup',{'name':'Persistent Admin','login':'admin','password':'test-password-2026'},boot['csrf'])
        boot=call('bootstrap');uid=boot['user']['id']
        existing=set((data/'sessions').glob('sess_*'))
        with urllib.request.urlopen(BASE+'health',timeout=10) as response:
            assert json.load(response)['ok'] and response.headers.get('Set-Cookie') is None
        assert set((data/'sessions').glob('sess_*'))==existing, 'Health checks must not create sessions'
        cookie=next(c for c in jar if c.name=='marathon_session')
        assert not cookie.discard and cookie.expires>time.time()+399*86400
        assert cookie._rest.get('SameSite')=='Lax' and 'HttpOnly' in cookie._rest
        assert list((data/'sessions').glob('sess_*'))
        # Serialize a real persistent cookie and build a fresh browser client.
        jar.save();jar=http.cookiejar.MozillaCookieJar(jar.filename);jar.load();browser=client(jar)
        assert call('bootstrap')['user']['id']==uid
        server.terminate();server.wait(timeout=10)
        # A fresh process uses a different default PHP session directory, as a new container would.
        server,boot=start('container-two');assert boot['user']['id']==uid
        cookie=next(c for c in jar if c.name=='marathon_session');cookie.expires=int(time.time())+300
        boot=call('bootstrap')
        assert next(c for c in jar if c.name=='marathon_session').expires>time.time()+399*86400
        replay=http.cookiejar.CookieJar()
        for saved_cookie in jar:replay.set_cookie(copy.copy(saved_cookie))
        call('logout',{},boot['csrf']);assert call('bootstrap')['user'] is None
        browser=client(replay);assert call('bootstrap')['user'] is None
        print('PASS: 400-day sliding cookie, browser restart, new process/default session directory, persistent volume and logout revocation.')
    finally:
        server.terminate();server.wait(timeout=10)
