"""Real PHP/SQLite checks: ownership, catalog, marks, legacy data and marathon SSO."""
from contextlib import closing
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
def port():
    with socket.socket() as s:s.bind(('127.0.0.1',0));return s.getsockname()[1]
class Client:
    def __init__(self,base):
        self.base=base;self.csrf='';self.token='';self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,action,body=None,status=200,headers=None):
        h={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        if self.token:h['X-Player-Token']=self.token
        h.update(headers or {})
        req=urllib.request.Request(self.base+'/api.php?action='+action,data=json.dumps(body).encode() if body is not None else None,headers=h)
        try:r=self.opener.open(req,timeout=18)
        except urllib.error.HTTPError as e:r=e
        with r:
            data=json.load(r);assert r.status==status,(action,r.status,data);return data
    def boot(self):
        data=self.call('bootstrap');self.csrf=data['csrf'];return data
    def register(self,name,login):self.boot();self.call('register',{'name':name,'login':login,'password':'testing-password'});return self.boot()['user']

with tempfile.TemporaryDirectory(prefix='pulse-community-') as tmp:
    folder=Path(tmp);pulse=folder/'pulse';marathon=folder/'marathon';pulse.mkdir();marathon.mkdir()
    pulse_port,marathon_port=port(),port();purl=f'http://127.0.0.1:{pulse_port}';murl=f'http://127.0.0.1:{marathon_port}';key='test-bridge-secret-'+'a'*48
    env=dict(os.environ,QUIZ_DATA_DIR=str(pulse),MARATHON_DATA_DIR=str(marathon),MARATHON_URL=murl,PULSE_URL=purl,PULSE_BRIDGE_SECRET=key,TELEGRAM_BOT_TOKEN='999999:pulse-test-bot-token',TELEGRAM_BOT_USERNAME='pulse_fixture_bot')
    servers=[]
    try:
        for root,p in ((ROOT,pulse_port),(ROOT/'marathon',marathon_port)):
            servers.append(subprocess.Popen([PHP,'-S',f'127.0.0.1:{p}','-t',str(root),str(root/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        admin,guest,a,b=Client(purl),Client(purl),Client(purl),Client(purl)
        for _ in range(80):
            try:admin.boot();break
            except OSError:time.sleep(.1)
        admin.call('setup',{'password':'testing-admin-password'});admin.boot()
        before=admin.call('quizzes');assert len(before['quizzes'])==3
        ua=a.register('Анна','reader_a');ub=b.register('Борис','reader_b')
        assert ua['role']=='participant' and ua['id']!=ub['id']
        fixture={'title':'Личный опрос','description':'','questions':[{'text':'Вопрос','type':'quiz','seconds':20,'options':['Да','Нет'],'correct':0}]}
        q=a.call('save',fixture)['id'];assert q in [x['id'] for x in a.call('quizzes')['quizzes']]
        assert b.call('quizzes')['quizzes']==[] and guest.call('catalog')['quizzes']==[]
        b.call('save',dict(fixture,id=q),404);b.call('delete',{'id':q},404);b.call('create_room',{'id':q},404);b.call('publish',{'id':q,'visibility':'public'},404)
        a.call('publish',{'id':q,'visibility':'public'})
        public=guest.call('catalog')['quizzes'][0];assert public['id']==q and 'questions' not in public and 'correct' not in json.dumps(public)
        copied=b.call('clone_quiz',{'id':q})['id'];assert b.call('quizzes')['quizzes'][0]['visibility']=='private'
        room=a.call('create_room',{'id':q});b.call('control',{'room':room['id'],'command':'next'},404);b.call('state&room='+room['id'],status=404)
        foreign=b.call('join',{'code':room['code'],'name':'Ignored when logged in'})
        b.token=foreign['token'];b.call('control',{'room':room['id'],'command':'next'},403);b.token=''
        a.call('publish',{'id':q,'visibility':'private'});assert guest.call('catalog')['quizzes']==[]
        old=guest.call('join',{'code':room['code'],'name':'Старое игровое имя'});guest.token=old['token']
        # Explicit legacy association preserves the player id, token, score and answers.
        with closing(sqlite3.connect(pulse/'quiz.sqlite')) as db:db.execute('UPDATE rooms SET owner_id=NULL WHERE id=?',(room['id'],));db.execute('UPDATE players SET score=750 WHERE id=(SELECT id FROM players WHERE token=?)',(old['token'],));db.commit()
        players=admin.call('room_participants&room='+room['id'])['players'];pid=next(p['id'] for p in players if p['name']=='Старое игровое имя')
        admin.call('link_player',{'player_id':pid,'user_id':ua['id']})
        guest.call('state',status=403)
        assert a.call('assessments')['games'][0]['score']==750
        a.call('directory',status=403);a.call('save_assessment',{'title':'Hack'},403)
        scores=[{'user_id':ua['id'],'points':750},{'user_id':ub['id'],'points':0}]
        grade=admin.call('save_assessment',{'title':'Прошедший тест','max_points':1000,'held_on':'2026-10-18','scores':scores})['id']
        my=a.call('assessments')['assessments'][0];assert len(my['scores'])==1 and my['scores'][0]['percent']==75
        assert b.call('assessments')['assessments'][0]['scores'][0]['percent']==0
        saved=admin.call('assessments')['assessments'][0]
        assert len(saved['scores'])==2
        admin.call('save_assessment',dict(saved,max_points=700),400)
        admin.call('save_assessment',dict(saved,revision=0),409)
        updated=dict(saved,scores=[{'user_id':ua['id'],'points':650}]);admin.call('save_assessment',updated)
        assert a.call('assessments')['assessments'][0]['scores'][0]['percent']==65
        assert b.call('assessments')['assessments']==[]
        print('PASS: legacy data, per-author privacy, public catalog/copy, room ownership and explicit player linking')
        print('PASS: scores/max -> percentages, numeric zero vs empty, own-results privacy and stale edit protection')

        source=Client(murl);source.boot();source.call('setup',{'login':'testadmin','password':'testing-admin-password','name':'Команда'});source.boot()
        ext=source.call('create_user',{'name':'Участник марафона','role':'participant'})['id']
        admin.call('sync_marathon',{})
        accounts=admin.call('directory')['users'];assert sum(u['external_id']==ext for u in accounts)==1
        admin.call('sync_marathon',{});assert len(admin.call('directory')['users'])==len(accounts)
        pushed=source.call('pulse_export',{});assert pushed['imported']==2
        source.call('pulse_export',{});assert len(admin.call('directory')['users'])==len(accounts)
        guest.call('receive_marathon',{'issuer':'f'*32,'users':[]},403)
        stranger=Client(murl);stranger.boot();stranger.call('pulse_export',{},401)
        guest.boot();guest.call('sync_marathon',{},401)
        source.call('pulse_directory',{},403)
        # Bind the authorization code to the originating Pulse browser + PKCE challenge.
        begin=b.call('marathon_begin',{});params=urllib.parse.parse_qs(urllib.parse.urlsplit(begin['url']).query)
        issued=source.call('pulse_authorize',{'state':params['pulse_state'][0],'challenge':params['pulse_challenge'][0]})
        result=urllib.parse.parse_qs(urllib.parse.urlsplit(issued['url']).query)
        code,state=result['marathon_code'][0],result['marathon_state'][0]
        guest.call('marathon_complete',{'code':code,'state':state},403)
        b.call('marathon_complete',{'code':code,'state':state});signed=b.boot()['user'];assert signed['issuer'] and signed['role']=='admin'
        b.call('marathon_complete',{'code':code,'state':state},403)
        source.call('pulse_exchange',{'code':code,'state':state,'verifier':'0'*64},403,{'X-Pulse-Bridge':key})
        assert 'password' not in json.dumps(admin.call('directory')) and 'telegram_id' not in json.dumps(admin.call('directory'))
        # A separate Pulse bot confirms the Telegram identity already linked in marathon.
        with closing(sqlite3.connect(marathon/'marathon.sqlite')) as db:db.execute('UPDATE users SET telegram_id=? WHERE id=?',('123456',ext));db.commit()
        telegram=Client(purl);telegram.boot();request=telegram.call('pulse_telegram_request',{})
        assert request['url'].startswith('https://t.me/pulse_fixture_bot?start=pl_')
        code_php=r'''function query(string $sql,array $args=[]):PDOStatement{global $db;$s=$db->prepare($sql);$s->execute($args);return $s;} function fail(string $m,int $s=400):never{throw new RuntimeException($m,$s);} $db=new PDO('sqlite:'.getenv('QUIZ_DATA_DIR').'/quiz.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);require $argv[1];require $argv[2];echo json_encode(pulseTelegramUpdate(json_decode(stream_get_contents(STDIN),true),'999999'));'''
        def bot(update,override=None):
            return json.loads(subprocess.check_output([PHP,'-r',code_php,str(ROOT/'assets/community.php'),str(ROOT/'assets/pulse-telegram.php')],env=dict(env,**(override or {})),input=json.dumps(update),text=True))
        preview=bot({'update_id':9001,'message':{'from':{'id':123456},'chat':{'type':'private','id':123456},'text':'/start pl_'+request['token']}})
        assert 'Подтвердить вход в Пульс' in json.dumps(preview,ensure_ascii=False)
        assert telegram.call('pulse_telegram_status',{'token':request['token']})['pending']
        def approval(update_id,sender=123456):return {'update_id':update_id,'callback_query':{'id':str(update_id),'from':{'id':sender},'message':{'chat':{'type':'private','id':sender}},'data':'pl_'+request['token']}}
        unlinked=bot(approval(9002,777777));assert 'не привязан к активному аккаунту' in json.dumps(unlinked,ensure_ascii=False)
        assert telegram.call('pulse_telegram_status',{'token':request['token']})['pending']
        # An old/wrong endpoint, a wrong shared key or an unavailable source is NOT an unlinked account.
        for update_id,override in [(9010,{'MARATHON_URL':purl}),(9011,{'PULSE_BRIDGE_SECRET':'wrong-key-'+'z'*40}),(9012,{'MARATHON_URL':'http://127.0.0.1:1'})]:
            unavailable=bot(approval(update_id),override);text=json.dumps(unavailable,ensure_ascii=False)
            assert 'Не удалось связаться с марафоном' in text and 'обновите' in text
            assert telegram.call('pulse_telegram_status',{'token':request['token']})['pending']
        bot(approval(9003));assert bot(approval(9003))==[]
        guest.call('pulse_telegram_status',{'token':request['token']},403)
        telegram.call('pulse_telegram_status',{'token':request['token']});signed=telegram.boot()['user']
        assert signed['external_id']==ext and signed['role']=='participant'
        telegram.call('pulse_telegram_status',{'token':request['token']},403)
        retry=telegram.call('pulse_telegram_request',{});request=retry;bot(approval(9004))
        with closing(sqlite3.connect(marathon/'marathon.sqlite')) as db:db.execute('UPDATE users SET telegram_id=NULL,session_epoch=session_epoch+1 WHERE id=?',(ext,));db.commit()
        telegram.call('pulse_telegram_status',{'token':retry['token']},502)
        print('PASS: push export, dedicated bot confirmation, shared identity, wrong sender/session/replay, unlink protection and distinct bridge failure messages')
        # A session deactivated by directory sync must stop authoring immediately.
        with closing(sqlite3.connect(marathon/'marathon.sqlite')) as db:db.execute("UPDATE users SET active=0 WHERE role='admin'");db.commit()
        admin.call('sync_marathon',{});assert b.boot()['user'] is None;b.call('quizzes',status=401)
        print('PASS: idempotent marathon identity sync, no password/Telegram data, browser-bound one-use SSO and revoked account')
        if os.environ.get('COMMUNITY_UI')=='1':
            with closing(sqlite3.connect(marathon/'marathon.sqlite')) as db:
                db.execute("UPDATE users SET active=1 WHERE role='admin'");db.execute('UPDATE users SET telegram_id=? WHERE id=?',('123456',ext));db.commit()
            subprocess.run(['node',str(ROOT/'tests/community_ui.cjs')],env=dict(env,COMMUNITY_TEST_URL=purl,COMMUNITY_MARATHON_URL=murl,PULSE_BOT_TEST_PHP=PHP,PULSE_BOT_TEST_SCRIPT=code_php,PULSE_BOT_TEST_USER=ext),check=True,timeout=90)
    finally:
        for server in servers:server.terminate();server.wait(timeout=10)
