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
    def __init__(self,base):self.base=base;self.csrf='';self.player='';self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,action,body=None,status=200):
        req=urllib.request.Request(self.base+'/api.php?action='+action,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf,'X-Player-Token':self.player})
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
    # Start with the deployed schema to exercise an additive upgrade with saved work.
    legacy_token='a'*32
    with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
        db.executescript("""CREATE TABLE pulse_forms(id TEXT PRIMARY KEY,token TEXT UNIQUE NOT NULL,owner_id TEXT NOT NULL,
            title TEXT NOT NULL,description TEXT NOT NULL,quiz TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,
            published INTEGER NOT NULL DEFAULT 0,require_account INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,
            revision INTEGER NOT NULL DEFAULT 1,assessment_id TEXT);""")
        legacy_quiz={'questions':[{'text':'Сколько?', 'options':['Один','Два'],'correct':0,'type':'quiz','points':10,'reference':'Бытие 1:1'}]}
        db.execute('INSERT INTO pulse_forms(id,token,owner_id,title,description,quiz,created_at) VALUES (?,?,?,?,?,?,?)',
                   ('legacy',legacy_token,'legacy-owner','Старый тест','',json.dumps(legacy_quiz),int(time.time())))
        db.commit()
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
        legacy=guest.call('form_get&token='+legacy_token)
        assert legacy['immediate_results'] and not legacy['results_visible']
        legacy=guest.call('form_submit',{'token':legacy_token,'name':'Гость','answers':[0]})
        assert legacy['attempt']['percent']==100 and legacy['questions'][0]['reference']=='Бытие 1:1'
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
            assert db.execute('SELECT immediate_results FROM pulse_forms WHERE id=?',('legacy',)).fetchone()[0]==1
        print('PASS: existing form schema migrates additively and old tests show results after completion')
        source=Client(murl);source.boot();source.call('setup',{'login':'admin','password':'testing-admin-password','name':'Команда'});source.boot()
        for tg,name in [('201','Телеграм Анна'),('202','Телеграм Борис')]:
            uid=source.call('create_user',{'name':name,'role':'participant'})['id']
            with closing(sqlite3.connect(mdir/'marathon.sqlite')) as db:db.execute('UPDATE users SET telegram_id=? WHERE id=?',(tg,uid));db.commit()
        questions=[{'text':'Какие два числа подходят?','type':'quiz','seconds':20,'options':['4','5','6','7','8'],'correct':[0,4],'points':500,'reference':'Числа 6:24–26'},
                   {'text':'Что из этого дерево?','type':'quiz','seconds':20,'options':['Дуб','Камень'],'correct':0,'points':500,'reference':'Псалом 1:3'}]
        quiz=admin.call('save',{'title':'Самостоятельный тест','questions':questions})['id']
        def create(**changes):return admin.call('form_create',dict(quiz_id=quiz,immediate_results=False,**changes))
        immediate=admin.call('form_create',{'quiz_id':quiz})
        before=guest.call('form_get&token='+immediate['token'])
        assert before['immediate_results'] and not before['results_visible']
        assert all('correct' not in q and 'reference' not in q for q in before['questions'])
        guest.call('form_submit',{'token':immediate['token'],'name':'Гость','answers':[[0,4]]},400)
        shown=guest.call('form_submit',{'token':immediate['token'],'name':'Гость','answers':[[0,4],1]})
        assert shown['results_visible'] and not shown['published'] and shown['attempt']['percent']==50
        assert shown['attempt']['answers']==[[0,4],1] and shown['questions'][0]['reference']=='Числа 6:24–26'
        assert guest.call('form_get&token='+immediate['token'])==shown
        assert not outsider.call('form_get&token='+immediate['token'])['results_visible']
        manager=admin.call('form_results&form='+immediate['id'])['form']
        assert manager['assessment_id'] is None
        admin.call('form_configure',{'form':immediate['id'],'revision':1,'active':True,'published':False,'immediate_results':False})
        assert 'answers' not in guest.call('form_get&token='+immediate['token'])['attempt']
        admin.call('form_configure',{'form':immediate['id'],'revision':2,'active':True,'published':False,'immediate_results':True})
        assert guest.call('form_get&token='+immediate['token'])['attempt']['percent']==50
        print('PASS: guests see their own score and references immediately, only after a complete submission, without publishing a ranking')
        f=create();token=f['token'];fid=f['id']
        public=guest.call('form_get&token='+token);assert all('correct' not in q and 'reference' not in q for q in public['questions'])
        a.call('form_results&form='+fid,status=404);guest.call('forms',status=401)
        guest.call('form_submit',{'token':token,'name':'Гость','answers':[0]},400)
        guest.call('form_submit',{'token':token,'name':'Гость','answers':[True,0]},400)
        hidden=a.call('form_submit',{'token':token,'name':'Ignored','answers':[[0,4],1],'points':100000})
        assert hidden['submitted'] and 'points' not in hidden['attempt'] and 'answers' not in hidden['attempt']
        again=a.call('form_submit',{'token':token,'answers':[[0,4],0]});assert again==hidden
        assert not a.call('assessments')['assessments']
        guest.call('form_submit',{'token':token,'name':'Гостевой ответ','answers':[[0,4],0]})
        owner_report=admin.call('form_results&form='+fid)
        original_attempt=next(x for x in owner_report['attempts'] if x['user_id']==ua)
        detail=admin.call('form_attempt',{'form':fid,'attempt':original_attempt['id']})
        assert detail['attempt']['answers']==[[0,4],1] and detail['attempt']['points']==500
        assert all('correct' in q for q in detail['questions'])
        a.call('form_attempt',{'form':fid,'attempt':original_attempt['id']},404)
        admin.call('form_attempt',{'form':fid,'attempt':'missing'},404)
        assert 'points' not in a.call('form_get&token='+token)['attempt']

        admin.call('save',{'id':quiz,'title':'Изменён шаблон','questions':[questions[0]]})
        assert len(guest.call('form_get&token='+token)['questions'])==2
        admin.call('form_configure',{'form':fid,'revision':1,'active':True,'published':True})
        shown=a.call('form_get&token='+token);assert shown['attempt']['points']==500 and shown['attempt']['percent']==50
        assert all('correct' in q for q in shown['questions'])
        published_before=a.call('standings')
        admin.call('form_configure',{'form':fid,'revision':2,'active':True,'published':True,'immediate_results':True})
        assert a.call('standings')==published_before, 'Changing personal visibility must preserve the published ranking snapshot'
        admin.call('form_configure',{'form':fid,'revision':3,'active':True,'published':True,'immediate_results':False})
        assert a.call('standings')==published_before
        assert all('correct' not in q for q in outsider.call('form_get&token='+token)['questions'])
        report=admin.call('form_results&form='+fid);assert len(report['attempts'])==2 and report['form']['assessment_id']
        grade=next(x for x in admin.call('assessments')['assessments'] if x['source_form_id']==fid)
        admin.call('save_assessment',dict(grade,scores=[{'user_id':ua,'points':650},{'user_id':ub,'points':0}]))
        assert a.call('form_get&token='+token)['attempt']['percent']==65
        assert b.call('assessments')['assessments'][0]['scores'][0]['percent']==0
        admin.call('form_configure',{'form':fid,'revision':1,'active':False,'published':True},409)
        admin.call('form_configure',{'form':fid,'revision':4,'active':False,'published':False})
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
        if($m==='sendPoll'){$n=(int)(query("SELECT value FROM settings WHERE key='fake_poll_seq'")->fetchColumn()?:0)+1;query("INSERT OR REPLACE INTO settings VALUES ('fake_poll_seq',?)",[(string)$n]);return ['poll'=>['id'=>'poll-'.$n],'message_id'=>$n];}
        if($m==='sendMessage'){$n=(int)(query("SELECT value FROM settings WHERE key='fake_message_seq'")->fetchColumn()?:0)+1;query("INSERT OR REPLACE INTO settings VALUES ('fake_message_seq',?)",[(string)$n]);return ['message_id'=>$n];}
        if($m==='editMessageText')return ['message_id'=>$a['message_id']];return [];};
        if(isset($input['update']))formsBotUpdate($input['update'],'999999');if(!empty($input['tick']))formsBotTick();echo json_encode($calls,JSON_UNESCAPED_UNICODE);'''
        def bot(update=None,tick=False,fail=None):
            return json.loads(subprocess.check_output([PHP,'-r',code_php,str(ROOT/'assets/community.php'),str(ROOT/'assets/pulse-telegram.php'),str(ROOT/'assets/forms-bot.php')],env=dict(env,APP_URL='https://pulse.example.test'),input=json.dumps(dict(update=update,tick=tick,fail_method=fail)),text=True,encoding='utf-8'))
        seq=10000
        def message(tg,text,chat=None,kind='private'):
            global seq
            seq+=1;return dict(update_id=seq,message=dict(text=text,**{'from':dict(id=tg,first_name='TG '+str(tg))},chat=dict(id=chat or tg,type=kind,title='Группа теста')))
        def answer(tg,poll,choice):
            global seq
            seq+=1;return dict(update_id=seq,poll_answer=dict(poll_id=poll,user=dict(id=tg,first_name='TG '+str(tg)),option_ids=choice if isinstance(choice,list) else [choice]))
        admin.call('save',{'id':quiz,'title':'Telegram тест','questions':questions})
        tf=create();calls=bot(message(201,'/start ft_'+tf['token']),True)
        sent=next(args for method,args in calls if method=='sendPoll');assert sent['type']=='regular' and not sent['is_anonymous'] and sent['allows_multiple_answers'] is True
        assert 'correct_option_id' not in sent and 'correct_option_ids' not in sent
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:poll=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE form_id=?',(tf['id'],)).fetchone()[0]
        update=answer(201,poll,[0,4]);bot(update,True);assert bot(update,True)==[]
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:poll2=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE form_id=?',(tf['id'],)).fetchone()[0]
        assert poll2!=poll
        bot(answer(202,poll2,0),True)  # Cannot answer another user's private test.
        finished=bot(answer(201,poll2,1),True)
        assert 'Результат на сайте' in json.dumps(finished,ensure_ascii=False) and 'Проверить результат' in json.dumps(finished,ensure_ascii=False)
        assert 'Правильно:' not in json.dumps(finished,ensure_ascii=False)
        data=admin.call('form_results&form='+tf['id']);assert len(data['attempts'])==1 and data['attempts'][0]['percent']==50
        def callback(tg,data,chat=None,kind='private',message_id=None):
            global seq
            seq+=1;return dict(update_id=seq,callback_query=dict(id=str(seq),**{'from':dict(id=tg,first_name='TG')},message=dict(message_id=message_id,chat=dict(id=chat or tg,type=kind)),data=data))
        hidden=bot(callback(201,'pr:'+tf['id']));assert 'ещё не открыл' in json.dumps(hidden,ensure_ascii=False)
        summary=bot(message(201,'/start fr_'+tf['id']))
        link=next(button['url'] for method,args in summary if method=='sendMessage' for row in args.get('reply_markup',{}).get('inline_keyboard',[]) for button in row if 'url' in button)
        secret=link.split('#result=')[1]
        assert '#result=' in link and '?test='+tf['token'] in link
        shared=outsider.call('form_get',{'token':tf['token'],'result':secret});assert shared['submitted'] and 'answers' not in shared['attempt']
        outsider.call('form_get',{'token':locked['token'],'result':secret},404)
        denied=bot(callback(202,'pa:'+tf['id']));assert 'Правильно:' not in json.dumps(denied,ensure_ascii=False)
        admin.call('form_configure',{'form':tf['id'],'revision':1,'active':True,'published':True})
        review=bot(callback(201,'pa:'+tf['id']));assert '500' in json.dumps(review) and 'Правильно' in json.dumps(review,ensure_ascii=False)
        assert '❌ Неверно' in json.dumps(review,ensure_ascii=False) and 'Ваш ответ:' in json.dumps(review,ensure_ascii=False)
        shared=outsider.call('form_get',{'token':tf['token'],'result':secret});assert shared['attempt']['percent']==50 and shared['attempt']['answers'][1]==1
        admin.call('form_configure',{'form':tf['id'],'revision':2,'active':True,'published':False})
        assert 'answers' not in outsider.call('form_get',{'token':tf['token'],'result':secret})['attempt']
        admin.call('form_configure',{'form':tf['id'],'revision':3,'active':True,'published':True})
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
            db.execute('UPDATE form_result_links SET expires_at=0');db.commit()
        outsider.call('form_get',{'token':tf['token'],'result':secret},404)
        print('PASS: native private Telegram polls, delayed correctness, identity, per-chat isolation, duplicate updates and final scoring')
        instant_tg=admin.call('form_create',{'quiz_id':quiz})
        calls=bot(message(201,'/start ft_'+instant_tg['token']),True)
        assert any(args.get('reply_markup',{}).get('keyboard') for method,args in calls if method=='sendMessage')
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:poll=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE form_id=?',(instant_tg['id'],)).fetchone()[0]
        calls=bot(answer(201,poll,[0,4]),True)
        assert 'Числа 6:24' not in json.dumps(calls,ensure_ascii=False)
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:poll=db.execute('SELECT current_poll_id FROM form_tg_deliveries WHERE form_id=?',(instant_tg['id'],)).fetchone()[0]
        calls=bot(answer(201,poll,1),True)
        assert '50%' in json.dumps(calls,ensure_ascii=False) and 'Верных ответов — 1 из 2' in json.dumps(calls,ensure_ascii=False)
        review=bot(callback(201,'pa:'+instant_tg['id']))
        assert 'Числа 6:24–26' in json.dumps(review,ensure_ascii=False) and 'Псалом 1:3' in json.dumps(review,ensure_ascii=False)
        assert 'Ваш ответ:' in json.dumps(review,ensure_ascii=False) and '❌ Неверно' in json.dumps(review,ensure_ascii=False)
        link_calls=bot(callback(201,'pr:'+instant_tg['id']))
        link=next(button['url'] for method,args in link_calls if method=='sendMessage' for row in args.get('reply_markup',{}).get('inline_keyboard',[]) for button in row if 'url' in button)
        linked=outsider.call('form_get',{'token':instant_tg['token'],'result':link.split('#result=')[1]})
        assert linked['results_visible'] and linked['attempt']['percent']==50
        history=bot(message(201,'Мои результаты'))
        history_buttons=[button for method,args in history if method=='sendMessage' for row in args.get('reply_markup',{}).get('inline_keyboard',[]) for button in row]
        assert any(button.get('callback_data')=='pr:'+instant_tg['id'] and '50%' in button['text'] for button in history_buttons)
        print('PASS: immediate Telegram percentage, answer count, references after completion, website link and percentages in history')

        group=create();connection=admin.call('form_telegram_create',{'form':group['id']});command=connection['command']
        denied=bot(message(201,command,-10010,'supergroup'));assert 'только администратор' in json.dumps(denied,ensure_ascii=False)
        bot(message(101,command,-10010,'supergroup'),True)
        row=admin.call('form_results&form='+group['id'])['deliveries'][0];assert row['state']=='active' and row['position']==0
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:gp,gmid=db.execute('SELECT current_poll_id,current_message_id FROM form_tg_deliveries WHERE id=?',(connection['id'],)).fetchone()
        assert gp is None
        # A player's selections are staged privately; group state reveals no option or identity.
        for option in (0,4):bot(callback(201,f"fa:{connection['id']}:1:0:{option}",-10010,'supergroup',gmid))
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:assert db.execute('SELECT count(*) FROM form_tg_votes WHERE delivery_id=?',(connection['id'],)).fetchone()[0]==0
        assert 'никто не видит' not in json.dumps(bot(callback(201,f"fs:{connection['id']}:1:0",-10010,'supergroup',gmid)),ensure_ascii=False).lower()
        bot(callback(202,f"fa:{connection['id']}:1:0:1",-10010,'supergroup',gmid));bot(callback(202,f"fs:{connection['id']}:1:0",-10010,'supergroup',gmid))
        a.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'next'},404)
        denied=bot(callback(201,f"pg:{row['id']}:{row['revision']}:next",-10010,'supergroup'));assert 'Управлять' in json.dumps(denied,ensure_ascii=False)
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'next'})
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'next'},409)
        edits=[args for method,args in bot(tick=True) if method=='editMessageText']
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:gp2,gmid2=db.execute('SELECT current_poll_id,current_message_id FROM form_tg_deliveries WHERE id=?',(connection['id'],)).fetchone()
        assert gp2 is None and gmid2==gmid
        assert edits and edits[-1]['message_id']==gmid
        for tg,option in ((201,0),(202,1)):
            bot(callback(tg,f"fa:{connection['id']}:2:1:{option}",-10010,'supergroup',gmid));bot(callback(tg,f"fs:{connection['id']}:2:1",-10010,'supergroup',gmid))
        row=admin.call('form_results&form='+group['id'])['deliveries'][0]
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'finish'});bot(tick=True)
        data=admin.call('form_results&form='+group['id']);assert sorted(a['points'] for a in data['attempts'])==[0,1000]
        row=data['deliveries'][0]
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'review'},409)
        admin.call('form_configure',{'form':group['id'],'revision':1,'active':True,'published':True})
        admin.call('form_telegram_command',{'form':group['id'],'delivery':row['id'],'revision':row['revision'],'command':'review'})
        assert any('Правильные ответы' in args.get('text','') for method,args in bot(tick=True))
        failed=create();connection=admin.call('form_telegram_create',{'form':failed['id']});bot(message(101,connection['command'],-10011,'supergroup'));bot(tick=True,fail='sendMessage')
        row=admin.call('form_results&form='+failed['id'])['deliveries'][0];assert row['state']=='error'
        assert bot(tick=True)==[]
        admin.call('form_telegram_command',{'form':failed['id'],'delivery':row['id'],'revision':row['revision'],'command':'retry'});bot(tick=True)
        assert admin.call('form_results&form='+failed['id'])['deliveries'][0]['state']=='active'
        print('PASS: group answers remain hidden, one editable message, admin controls, delayed review and retry after failure')
        # History lists only this Telegram user's work and preserves publication privacy.
        history=bot(message(201,'/results'))
        keyboard=[button for method,args in history if method=='sendMessage' for row in args.get('reply_markup',{}).get('inline_keyboard',[]) for button in row]
        assert any(b.get('callback_data')=='pr:'+tf['id'] for b in keyboard)
        assert not any(b.get('callback_data')=='pr:'+failed['id'] for b in keyboard)
        assert 'Правильно:' not in json.dumps(history,ensure_ascii=False)
        start_calls=bot(message(201,'/start'))
        assert any(args.get('reply_markup',{}).get('keyboard') for method,args in start_calls if method=='sendMessage')
        denied=bot(callback(202,'pr:'+tf['id']))
        assert 'нет сохранённой работы' in json.dumps(denied,ensure_ascii=False)
        assert 'Ваш результат:' not in json.dumps(denied,ensure_ascii=False)
        assert not any(method=='sendMessage' for method,args in bot(message(201,'/results',-10010,'supergroup')))
        # An account-linked attempt submitted on the website is also accessible in Telegram.
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
            db.execute('INSERT OR REPLACE INTO pulse_tg_accounts VALUES (?,?)',('303',ua));db.commit()
        web_history=bot(message(303,'Мои результаты'))
        assert 'pr:'+fid in json.dumps(web_history)
        hidden_result=bot(callback(303,'pr:'+fid))
        assert 'ещё не открыл' in json.dumps(hidden_result,ensure_ascii=False)
        assert '650' not in json.dumps(hidden_result)
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
            db.execute('UPDATE pulse_forms SET published=1 WHERE id=?',(fid,));db.commit()
        web_result=bot(callback(303,'pr:'+fid))
        assert '650' in json.dumps(web_result)
        print('PASS: owner work review, Telegram history, website-linked attempts, private-chat isolation and hidden results')
        # Deletion is owner-only, versioned and removes the published contribution atomically.
        deleting=admin.call('form_results&form='+group['id'])['form']
        a.call('form_delete',{'form':group['id'],'revision':deleting['revision']},404)
        admin.call('form_delete',{'form':group['id'],'revision':0},409)
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
            db.execute("UPDATE form_tg_deliveries SET state='sending' WHERE form_id=?",(group['id'],));db.commit()
        admin.call('form_delete',{'form':group['id'],'revision':deleting['revision']},409)
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
            db.execute("UPDATE form_tg_deliveries SET state='closed' WHERE form_id=?",(group['id'],));db.commit()
        aid=deleting['assessment_id']
        assert any(t['id']==aid for t in admin.call('standings')['tests'])
        admin.call('form_delete',{'form':group['id'],'revision':deleting['revision']})
        assert all(t['id']!=aid for t in admin.call('standings')['tests'])
        guest.call('form_get&token='+group['token'],status=404)
        a.call('form_submit',{'token':group['token'],'answers':[[0,4],0]},404)
        admin.call('form_results&form='+group['id'],status=404)
        assert any(f['id']==fid for f in admin.call('forms')['forms'])
        with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
            assert db.execute('SELECT 1 FROM quizzes WHERE id=?',(quiz,)).fetchone()
            for table,key,value in [('form_attempts','form_id',group['id']),('form_tg_deliveries','form_id',group['id']),('assessments','id',aid),('assessment_scores','assessment_id',aid),('published_scores','assessment_id',aid)]:
                assert db.execute(f'SELECT count(*) FROM {table} WHERE {key}=?',(value,)).fetchone()[0]==0
        print('PASS: form deletion permissions, stale revision, in-flight bot guard, rating cleanup and source quiz preservation')
        block_questions=[
            {'text':'Установите пары','block':'matching','prompts':['Ной','Моисей','Соломон'],'options':['Ковчег','Исход','Храм'],'correct':[0,1,2]},
            {'text':'Расположите события','block':'ordering','options':['Выход из Египта','Переход через море','Вход в землю'],'correct':[0,1,2]},
            {'text':'Вставьте слово: Бог есть ___','block':'missing_word','options':['любовь','страх'],'correct':0},
            {'text':'Как поступить при ссоре?','block':'scenario','options':['Примириться','Отомстить'],'correct':0},
            {'text':'Кто сказал: вот я?','block':'speaker','options':['Исаия','Иона'],'correct':0}]
        block_questions=[dict(q,type='quiz',seconds=90,points=100,reference='Местописание после сдачи') for q in block_questions]
        block_quiz=admin.call('save',{'title':'Все блоки','scoring':'fixed','questions':block_questions})['id']
        normalized=next(q for q in admin.call('quizzes')['quizzes'] if q['id']==block_quiz)['questions']
        for raw,q in zip(block_questions,normalized):
            if q['block'] in ('matching','ordering'):
                assert [q['options'][i] for i in q['correct']]==raw['options']
                assert q['options']!=raw['options'], 'The public list must be shuffled'
        imported=admin.call('import_preview',{'json':json.dumps({'title':'Импорт блоков','questions':block_questions})})['quiz']
        assert [q['block'] for q in imported['questions']]==[q['block'] for q in block_questions]
        for q in imported['questions'][:2]:assert len(q['correct'])==3
        for invalid in [dict(block_questions[0],prompts=['Один']),dict(block_questions[1],correct=[0,0,1]),dict(block_questions[0],options=['Повтор','Повтор','Другой']),dict(block_questions[2],block='unknown')]:
            admin.call('save',{'title':'Некорректный блок','questions':[invalid]},400)
        bf=admin.call('form_create',{'quiz_id':block_quiz})
        block_guest=Client(purl);block_guest.boot()
        safe=block_guest.call('form_get&token='+bf['token'])
        assert all('correct' not in q and 'reference' not in q for q in safe['questions'])
        assert safe['questions'][0]['prompts']==block_questions[0]['prompts']
        answers=[q['correct'] for q in normalized]
        block_guest.call('form_submit',{'token':bf['token'],'name':'Неполный','answers':[normalized[0]['correct'][:2],*answers[1:]]},400)
        wrong_answers=[list(reversed(answers[0])),list(reversed(answers[1])),*answers[2:]]
        score=block_guest.call('form_submit',{'token':bf['token'],'name':'Блоки','answers':wrong_answers})
        assert score['attempt']['percent']==60 and score['attempt']['answers']==wrong_answers
        correct_guest=Client(purl);correct_guest.boot()
        assert correct_guest.call('form_submit',{'token':bf['token'],'name':'Верно','answers':answers})['attempt']['percent']==100
        assert correct_guest.call('form_get&token='+bf['token'])['attempt']['answers']==answers
        # Live website entry point must preserve the same sequence semantics.
        room=admin.call('create_room',{'id':block_quiz})
        player_client=Client(purl);player_client.boot()
        player_client.player=player_client.call('join',{'code':room['code'],'name':'Игрок блоков'})['token']
        admin.call('control',{'room':room['id'],'command':'next'})
        player_client.call('answer',{'index':0,'choices':answers[0][:2]},400)
        player_client.call('answer',{'index':0,'choices':wrong_answers[0]})
        live=player_client.call('state');assert live['answer']['correct'] is False and live['answer']['choices']==wrong_answers[0]
        admin.call('control',{'room':room['id'],'command':'next'})
        player_client.call('answer',{'index':1,'choices':answers[1]})
        live=player_client.call('state');assert live['answer']['correct'] is True and live['answer']['points']==100
        print('PASS: all five blocks save/import, validate, shuffle, keep answers private, preserve order and score correctly on forms and live games')
        # Structured personal Telegram questions use a private, ordered button sequence.
        telegram_form=admin.call('form_create',{'quiz_id':block_quiz})
        bot(message(201,'/start ft_'+telegram_form['token']),True)
        for index,q in enumerate(normalized):
            with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:
                db.row_factory=sqlite3.Row
                delivery=dict(db.execute('SELECT * FROM form_tg_deliveries WHERE form_id=? AND kind=?',(telegram_form['id'],'private')).fetchone())
            if q['block'] in ('matching','ordering'):
                prefix=f"fa:{delivery['id']}:{delivery['revision']}:{index}:"
                partial=bot(callback(201,f"fs:{delivery['id']}:{delivery['revision']}:{index}",message_id=delivery['current_message_id']))
                assert 'Сначала выберите' in json.dumps(partial,ensure_ascii=False)
                selection=list(reversed(q['correct'])) if index==0 else q['correct']
                for option in selection:bot(callback(201,prefix+str(option),message_id=delivery['current_message_id']))
                calls=bot(callback(201,f"fs:{delivery['id']}:{delivery['revision']}:{index}",message_id=delivery['current_message_id']),True)
            else:calls=bot(answer(201,delivery['current_poll_id'],q['correct']),True)
            if index<4:assert 'Местописание после сдачи' not in json.dumps(calls,ensure_ascii=False)
        result=admin.call('form_results&form='+telegram_form['id'])['attempts'][0]
        assert result['percent']==80
        review=bot(callback(201,'pa:'+telegram_form['id']))
        assert 'Ной —' in json.dumps(review,ensure_ascii=False) and 'Местописание после сдачи' in json.dumps(review,ensure_ascii=False)
        print('PASS: structured private Telegram buttons, step completion, mixed block progression, exact sequence scoring and readable final review')
        group_blocks=admin.call('form_create',{'quiz_id':block_quiz})
        binding=admin.call('form_telegram_create',{'form':group_blocks['id']})
        bot(message(101,binding['command'],-10088,'supergroup'),True)
        for index,q in enumerate(normalized):
            delivery=admin.call('form_results&form='+group_blocks['id'])['deliveries'][0]
            with closing(sqlite3.connect(pdir/'quiz.sqlite')) as db:message_id=db.execute('SELECT current_message_id FROM form_tg_deliveries WHERE id=?',(delivery['id'],)).fetchone()[0]
            selection=list(reversed(q['correct'])) if index==1 else q['correct']
            if not isinstance(selection,list):selection=[selection]
            for option in selection:bot(callback(201,f"fa:{delivery['id']}:{delivery['revision']}:{index}:{option}",-10088,'supergroup',message_id))
            bot(callback(201,f"fs:{delivery['id']}:{delivery['revision']}:{index}",-10088,'supergroup',message_id))
            admin.call('form_telegram_command',{'form':group_blocks['id'],'delivery':delivery['id'],'revision':delivery['revision'],'command':'next'});bot(tick=True)
        group_report=admin.call('form_results&form='+group_blocks['id'])
        assert group_report['deliveries'][0]['state']=='closed' and group_report['attempts'][0]['percent']==80
        print('PASS: mixed structured and ordinary blocks in a Telegram group, organizer-controlled progression and ordered scoring')
        if os.environ.get('FORMS_UI')=='1':
            subprocess.run(['node',str(ROOT/'tests/forms_ui.cjs')],env=dict(env,FORMS_TEST_URL=purl,FORMS_QUIZ_ID=quiz,FORMS_USER_A=ua,FORMS_USER_B=ub),check=True,timeout=100)
    finally:
        for server in servers:server.terminate();server.wait(timeout=10)
