"""Bluff mode integration with real HTTP, an isolated SQLite database and fake players."""
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
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
BASE='http://127.0.0.1:8108/api.php?action='
class Client:
    def __init__(self):self.o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf='';self.token=''
    def call(self,a,p=None,status=200,suffix=''):
        h={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        if self.token:h['X-Player-Token']=self.token
        req=urllib.request.Request(BASE+a+suffix,data=json.dumps(p).encode() if p is not None else None,headers=h)
        try:r=self.o.open(req,timeout=10)
        except urllib.error.HTTPError as e:r=e
        with r:
            data=json.load(r);assert r.status==status,(a,r.status,data);return data
    def boot(self):self.csrf=self.call('bootstrap')['csrf']
with tempfile.TemporaryDirectory(prefix='pulse-bluff-') as folder:
    server=subprocess.Popen([PHP,'-S','127.0.0.1:8108','-t',str(ROOT),str(ROOT/'router.php')],env=dict(os.environ,QUIZ_DATA_DIR=folder),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        host=Client()
        for _ in range(60):
            try:host.boot();break
            except OSError:time.sleep(.1)
        host.call('setup',{'password':'test-password-2026'});host.boot()
        quiz={'title':'Выдумки','mode':'bluff','scoring':'fixed','questions':[
            {'text':'Кто построил ковчег?','truth':'Ной','aliases':['Ноах'],'category':'Бытие','seconds':60,'reference':'Бытие 6'},
            {'text':'Столица Италии?','truth':'Рим','category':'География','seconds':60}]}
        qid=host.call('save',quiz)['id']
        # Both native JSON and conversion of ordinary question JSON create editable bluff games.
        native=host.call('import_preview',{'json':json.dumps({'title':'JSON','mode':'bluff','categories':[{'title':'Бытие','questions':[{'question':'Кто?','truth':'Ной','aliases':['Ноах']}]}]})})
        assert native['quiz']['questions'][0]['truth']=='Ной'
        converted=host.call('import_preview',{'mode':'bluff','json':json.dumps({'title':'Converted','questions':[{'text':'Кто?','category':'Бытие','options':['Ной','Моисей'],'correct':0}]})})
        assert converted['quiz']['questions'][0]['truth']=='Ной'
        host.call('save',converted['quiz'])
        room=host.call('create_room',{'id':qid});rid=room['id'];players=[]
        modified=json.loads(json.dumps(quiz));modified['id']=qid;modified['questions'][0]['truth']='Новое имя';host.call('save',modified)
        def join(name):
            p=Client();p.boot();p.token=p.call('join',{'name':name,'code':room['code']})['token'];players.append(p);return p
        a=join('A');host.call('control',{'room':rid,'command':'next'},400)
        b=join('B');c=join('C')
        host.call('control',{'room':rid,'command':'next'})
        def hs():return host.call('state',suffix='&room='+rid)
        def op(p,action,**kw):return p.call(action,{'round':1,'index':0,**kw})
        fixtures={'quiz':quiz};s=a.call('state');fixtures['choose']=s;assert s['status']=='choose' and s['chooser']==s['playerId'] and s['question'] is None
        b.call('bluff_select',{'round':1,'category':'Бытие'},403)
        op(a,'bluff_select',category='Бытие')
        s=a.call('state');fixtures['write']=s;assert s['status']=='write' and 'truth' not in s['question'] and 'aliases' not in str(s)
        token=hs()['projectorToken'];screen=Client();screen.boot()
        ps=screen.call('state',suffix='&projector='+token);assert ps['playerId'] is None and ps['question']==s['question']
        screen.call('bluff_lie',{'round':1,'index':0,'text':'test'},401)
        screen.call('control',{'room':rid,'command':'reveal'},401)
        for text in [' НОЙ!!! ','ноах']:
            r=op(a,'bluff_lie',text=text);assert r['matchedTruth'] and not r['accepted']
        assert b.call('state')['written']==0 and 'matchedTruth' not in b.call('state')
        a.call('bluff_lie',{'round':1,'index':0,'text':'!!!'},400)
        op(a,'bluff_lie',text='Моисей');a.call('bluff_lie',{'round':1,'index':0,'text':'другое'},409)
        d=join('D');d.call('bluff_lie',{'round':1,'index':0,'text':'late'},403)
        op(b,'bluff_lie',text='МОИСЕЙ!');op(c,'bluff_lie',text='Авраам')
        host.call('control',{'room':rid,'command':'reveal','round':1,'phase':'write'},409)
        s=a.call('state');fixtures['vote']=s;assert s['status']=='vote' and len(s['choices'])==3
        assert s['choices']==a.call('state')['choices'] and s['myLie']=='Моисей'
        assert 'authors' not in str(s['choices']) and 'truth' not in str(s['choices']) and 'reference' not in s['question']
        truth=next(x['id'] for x in s['choices'] if x['text']=='Ной')
        own=next(x['id'] for x in s['choices'] if x['own'])
        other=next(x['id'] for x in s['choices'] if x['text']=='Авраам')
        a.call('bluff_vote',{'round':1,'index':0,'choice':own},400)
        op(a,'bluff_vote',choice=other);a.call('bluff_vote',{'round':1,'index':0,'choice':truth},409)
        op(b,'bluff_vote',choice=truth)
        assert all(p['score']==0 for p in a.call('state')['players'])
        d.call('bluff_vote',{'round':1,'index':0,'choice':truth},403)
        op(c,'bluff_vote',choice=own)
        s=hs();assert s['status']=='results' and s['question']['truth']=='Ной'
        assert {p['name']:p['score'] for p in s['players']}=={'A':500,'B':1500,'C':500,'D':0}
        fixtures['results']=s
        subprocess.run(['node',str(ROOT/'tests/bluff_render.cjs')],input=json.dumps(fixtures),text=True,encoding='utf-8',check=True)
        assert set(next(x['authors'] for x in s['choices'] if x['id']==own))=={'A','B'}
        assert s['players']==hs()['players'];host.call('control',{'room':rid,'command':'reveal'},409)
        # Round-robin chooser and stale request protection; skipped writing still opens voting.
        host.call('control',{'room':rid,'command':'next'});s=b.call('state');assert s['chooser']==s['playerId'] and s['round']==2
        b.call('bluff_select',{'round':1,'category':'География'},409)
        b.call('bluff_select',{'round':2,'category':'География'})
        with sqlite3.connect(Path(folder)/'quiz.sqlite') as db:db.execute('UPDATE bluff_rooms SET deadline=0 WHERE room_id=?',(rid,))
        db.close()
        s=a.call('state');assert s['status']=='vote' and len(s['choices'])==1
        for p in players:p.call('bluff_vote',{'round':2,'index':1,'choice':s['choices'][0]['id']})
        s=hs();assert s['status']=='results' and {p['name']:p['score'] for p in s['players']}=={'A':1500,'B':2500,'C':1500,'D':1000}
        host.call('control',{'room':rid,'command':'next'});assert hs()['status']=='finished'
        Client().call('join',{'name':'After','code':room['code']},400)
        # Selection timer, early host transitions, read-only projector and room isolation.
        modified['questions'][0]['category']='123';modified['questions'][1]['category']='456';host.call('save',modified)
        room2=host.call('create_room',{'id':qid});rid2=room2['id']
        for p,name in [(a,'A'),(b,'B')]:p.token=p.call('join',{'name':name,'code':room2['code']})['token']
        host.call('control',{'room':rid2,'command':'next'})
        with sqlite3.connect(Path(folder)/'quiz.sqlite') as db:db.execute('UPDATE bluff_rooms SET deadline=0 WHERE room_id=?',(rid2,))
        db.close()
        s=a.call('state');assert s['status']=='write'
        a.call('bluff_lie',{'round':1,'index':s['index'],'text':'0'});assert a.call('state')['myLie']=='0'
        host.call('control',{'room':rid2,'command':'reveal'});assert a.call('state')['status']=='vote'
        host.call('control',{'room':rid2,'command':'reveal'});assert a.call('state')['status']=='results'
        assert all(p['score']==0 for p in a.call('state')['players'])
        print('PASS: bluff editor/API and JSON, rotating category chooser, private truth/alias match, no answer leaks, merged lies and self-vote rejection, fixed scoring exactly once, late joins, timers, stale requests, projector and room isolation.')
    finally:server.terminate();server.wait(timeout=5)
