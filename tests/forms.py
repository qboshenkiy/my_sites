"""Web forms + native Telegram polls with a fake transport; no real bot messages."""
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
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
def port():
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));return sock.getsockname()[1]
class Client:
    def __init__(self,base):self.base=base;self.csrf='';self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,action,body=None,status=200):
        req=urllib.request.Request(self.base+'/api.php?action='+action,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        try:r=self.opener.open(req,timeout=20)
        except urllib.error.HTTPError as e:r=e
        with r:
            data=json.load(r);assert r.status==status,(action,r.status,data);return data
    def boot(self):
        data=self.call('bootstrap');self.csrf=data['csrf'];return data
    def register(self,name,login):
        self.boot();self.call('register',{'name':name,'login':login,'password':'testing-password'});return self.boot()['user']['id']

with tempfile.TemporaryDirectory(prefix='pulse-forms-') as tmp:
    folder=Path(tmp);pdir=folder/'pulse';mdir=folder/'marathon';pdir.mkdir();mdir.mkdir()
    pp,mp=port(),port();purl=f'http://127.0.0.1:{pp}';murl=f'http://127.0.0.1:{mp}'
    env=dict(os.environ,QUIZ_DATA_DIR=str(pdir),MARATHON_DATA_DIR=str(mdir),MARATHON_URL=murl,PULSE_URL=purl,
             PULSE_BRIDGE_SECRET='fixture-bridge-key-'+'f'*40,TELEGRAM_BOT_TOKEN='999999:fixture-telegram-token',TELEGRAM_BOT_USERNAME='fixture_pulse_bot',APP_URL=purl)
    servers=[]
    try:
        for root,p in [(ROOT,pp),(ROOT/'marathon',mp)]:servers.append(subprocess.Popen([PHP,'-S',f'127.0.0.1:{p}','-t',str(root),str(root/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL))
        admin=Client(purl)
        for _ in range(80):
            try:admin.boot();break
            except OSError:time.sleep(.1)
        admin.call('setup',{'password':'testing-admin-password'});admin.boot()
        a,b,guest,outsider=[Client(purl) for _ in range(4)]
        ua=a.register('Анна','reader_a');ub=b.register('Борис','reader_b');guest.boot();outsider.boot()
        source=Client(murl);source.boot();source.call('setup',{'login':'admin','password':'testing-admin-password','name':'Команда'});source.boot()
        for tg,name in [('201','Телеграм Анна'),('202','Телеграм Борис')]:
            uid=source.call('create_user',{'name':name,'role':'participant'})['id']
            with closing(sqlite3.connect(mdir/'marathon.sqlite')) as db:db.execute('UPDATE users SET telegram_id=? WHERE id=?',(tg,uid));db.commit()
        questions=[{'text':'2 + 2?','type':'quiz','seconds':20,'options':['4','5'],'correct':0,'points':500},
                   {'text':'Что из этого дерево?','type':'quiz','seconds':20,'options':['Дуб','Камень'],'correct':0,'points':500}]
        quiz=admin.call('save',{'title':'Самостоятельный тест','questions':questions})['id']
        def create(**changes):return admin.call('form_create',dict(quiz_id=quiz,**changes))
        f=create();token=f['token'];fid=f['id']
        public=guest.call('form_get&token='+token);assert all('correct' not in q and 'reference' not in q for q in public['questions'])
        a.call('form_results&form='+fid,status=404);guest.call('forms',status=401)
        guest.call('form_submit',{'token':token,'name':'Гость','answers':[0]},400)
        guest.call('form_submit',{'token':token,'name':'Гость','answers':[True,0]},400)
        hidden=a.call('form_submit',{'token':token,'name':'Ignored','answers':[0,1],'points':100000})
        assert hidden['submitted'] and 'points' not in hidden['attempt'] and 'answers' not in hidden['attempt']
        again=a.call('form_submit',{'token':token,'answers':[0,0]});assert again==hidden
        assert not a.call('assessments')['assessments']
        guest.call('form_submit',{'token':token,'name':'Гостевой ответ','answers':[0,0]})
        admin.call('save',{'id':quiz,'title':'Изменён шаблон','questions':[questions[0]]})
        assert len(guest.call('form_get&token='+token)['questions'])==2
        admin.call('form_configure',{'form':fid,'revision':1,'active':True,'published':True})
        shown=a.call('form_get&token='+token);assert shown['attempt']['points']==500 and shown['attempt']['percent']==50
        assert all('correct' in q for q in shown['questions'])
        assert all('correct' not in q for q in outsider.call('form_get&token='+token)['questions'])
        report=admin.call('form_results&form='+fid);assert len(report['attempts'])==2 and report['form']['assessment_id']
        grade=next(x for x in admin.call('assessments')['assessments'] if x['source_form_id']==fid)
        admin.call('save_assessment',dict(grade,scores=[{'user_id':ua,'points':650},{'user_id':ub,'points':0}]))
        assert a.call('form_get&token='+token)['attempt']['percent']==65
        assert b.call('assessments')['assessments'][0]['scores'][0]['percent']==0
        admin.call('form_configure',{'form':fid,'revision':1,'active':False,'published':True},409)
        admin.call('form_configure',{'form':fid,'revision':2,'active':False,'published':False})
        assert 'points' not in a.call('form_get&token='+token)['attempt']
        assert a.call('assessments')['assessments']==[]
        outsider.call('form_submit',{'token':token,'name':'Closed','answers':[0,0]},409)
        locked=create(require_account=True);outsider.call('form_submit',{'token':locked['token'],'name':'Guest','answers':[0]},401)
        print('PASS: immutable form snapshot, server scoring, one attempt, guest/account privacy, release/re-hide, manual correction and closed intake')

        # Native Telegram calls are captured; identity lookup uses the local marathon fixture only.
        code_php=r'''function query(string $s,array $a=[]):PDOStatement{global $db;$q=$db->prepare($s);$q->execute($a);return $q;}function fail(string $m,int $s=400):never{throw new RuntimeException($m,$s);}
        $db=new PDO('sqlite:'.getenv('QUIZ_DATA_DIR').'/quiz.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);$db->exec('PRAGMA foreign_keys=ON;PRAGMA busy_timeout=10000;');$me=null;
        require $argv[1];require $argv[2];require $argv[3];communitySchema();pulseTelegramSchema();formsBotSchema();$input=json_decode(stream_get_contents(STDIN),true);$calls=[];
        $pulseFormBotTransport=function($m,$a)use(&$calls,$input){$calls[]=[$m,$a];if(($input['fail_method']??'')===$m)throw new RuntimeException('synthetic network failure');
        if($m==='getChatMember')return ['status'=>(string)$a['user_id']==='101'?'creator':'member'];
        if($m==='sendPoll'){$n=(int)(query("SELECT value FROM settings WHERE key='fake_poll_seq'")->fetchColumn()?:0)+1;query("INSERT OR REPLACE INTO settings VALUES ('fake_poll_seq',?)",[(string)$n]);return ['poll'=>['id'=>'poll-'.$n],'message_id'=>$n];}return [];};
        if(isset($input['update']))formsBotUpdate($input['update'],'999999');if(!empty($input['tick']))formsBotTick();echo json_encode($calls,JSON_UNESCAPED_UNICODE);'''
        def bot(update=None,tick=False,fail=None):
            return json.loads(subprocess.check_output([PHP,'-r',code_php,str(ROOT/'assets/community.php'),str(ROOT/'assets/pulse-telegram.php'),str(ROOT/'assets/forms-bot.php')],env=env,input=json.dumps(dict(update=update,tick=tick,fail_method=fail)),text=True,encoding='utf-8'))
        seq=10000
        def message(tg,text,chat=None,kind='private'):
            global seq
            seq+=1;return dict(update_id=seq,message=dict(text=text,**{'from':dict(id=tg,first_name='TG '+str(tg))},chat=dict(id=chat or tg,type=kind,title='Группа теста')))
        def answer(tg,poll,choice):
            global seq
            seq+=1;return dict(update_id=seq,poll_answer=dict(poll_id=poll,user=dict(id=tg,first_name='TG '+str(tg)),option_ids=[choice]))
        admin.call('save',{'id':quiz,'title':'Telegram тест','questions':questions})
        tf=create();calls=bot(message(201,'/start ft_'+tf['token']),True)
        sent=next(args for method,args in calls if method=='sendPoll');assert sent['type']=='regular' and not sent['is_anonymous']
        assert 'correct_option_id' not in sent and 'correct_option_ids' not in sent
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:poll=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE form_id=?',(tf['id'],)).fetchone()[0]
        update=answer(201,poll,0);bot(update,True);assert bot(update,True)==[]
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:poll2=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE form_id=?',(tf['id'],)).fetchone()[0]
        assert poll2!=poll
        bot(answer(202,poll2,0),True)  # Cannot answer another user's private test.
        bot(answer(201,poll2,1),True)
        data=admin.call('form_results&form='+tf['id']);assert len(data['attempts'])==1 and data['attempts'][0]['percent']==50
        def callback(tg,data,chat=None,kind='private'):
            global seq
            seq+=1;return dict(update_id=seq,callback_query=dict(id=str(seq),**{'from':dict(id=tg,first_name='TG')},message=dict(chat=dict(id=chat or tg,type=kind)),data=data))
        hidden=bot(callback(201,'pr:'+tf['id']));assert 'ещё не открыл' in json.dumps(hidden,ensure_ascii=False)
        admin.call('form_configure',{'form':tf['id'],'revision':1,'active':True,'published':True})
        review=bot(callback(201,'pr:'+tf['id']));assert '500' in json.dumps(review) and 'Правильно' in json.dumps(review,ensure_ascii=False)
        print('PASS: native private Telegram polls, delayed correctness, identity, per-chat isolation, duplicate updates and final scoring')

        group=create();connection=admin.call('form_telegram_create',{'form':group['id']});command=connection['command']
        denied=bot(message(201,command,-10010,'supergroup'));assert 'только администратор' in json.dumps(denied,ensure_ascii=False)
        bot(message(101,command,-10010,'supergroup'),True)
        row=admin.call('form_results&form='+group['id'])['deliveries'][0];assert row['state']=='active' and row['position']==0
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:gp=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE id=?',(connection['id'],)).fetchone()[0]
        bot(answer(201,gp,0));bot(answer(202,gp,1))
        a.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'next'},404)
        denied=bot(callback(201,f"pg:{row['id']}:{row['revision']}:next",-10010,'supergroup'));assert 'Управлять' in json.dumps(denied,ensure_ascii=False)
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'next'})
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'next'},409)
        bot(tick=True)
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:gp2=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE id=?',(connection['id'],)).fetchone()[0]
        bot(answer(202,gp,0));bot(answer(201,gp2,0)) # Old closed poll cannot change the result.
        row=admin.call('form_results&form='+group['id'])['deliveries'][0]
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'finish'});bot(tick=True)
        data=admin.call('form_results&form='+group['id']);assert sorted(a['points'] for a in data['attempts'])==[0,1000]
        row=data['deliveries'][0]
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'review'},409)
        admin.call('form_configure',{'form':group['id'],'revision':1,'active':True,'published':True})
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'review'})
        assert any('Правильные ответы' in args.get('text','') for method,args in bot(tick=True))
        failed=create();connection=admin.call('form_telegram_create',{'form':failed['id']});bot(message(101,connection['command'],-10011,'supergroup'),True,'sendPoll')
        row=admin.call('form_results&form='+failed['id'])['deliveries'][0];assert row['state']=='error'
        assert bot(tick=True)==[]
        admin.call('form_telegram_command',{'form':failed['id'],'delivery':row['id'],'revision':row['revision'],'command':'retry'});bot(tick=True)
        assert admin.call('form_results&form='+failed['id'])['deliveries'][0]['state']=='active'
        print('PASS: group admin binding/control, web next/finish, stale commands, closed polls, partial attempts, release-gated review and explicit retry after failure')
        if os.environ.get('FORMS_UI')=='1':
            subprocess.run(['node',str(ROOT/'tests/forms_ui.cjs')],env=dict(env,FORMS_TEST_URL=purl,FORMS_QUIZ_ID=quiz,FORMS_USER_A=ua,FORMS_USER_B=ub),check=True,timeout=100)
    finally:
        for server in servers:server.terminate();server.wait(timeout=10)
