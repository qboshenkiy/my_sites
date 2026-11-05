"""Persistent incident detection and a dedicated Telegram notification bot."""
import collections
import hashlib
import hmac
import json
import re
import secrets
import threading
import time
import urllib.error
import urllib.request
import monitor
import ip_activity
import bot_diagnostics

DEFAULTS={'enabled':True,'http_limit':240,'bot_limit':60,'cooldown':600,'http_errors':True,'bot_errors':True,'telegram_enabled':False,'bot_token':'','bot_username':'','bot_id':'','group_id':'','group_title':'','epoch':''}


class TelegramError(ValueError):
    def __init__(self,code=0,retry_after=0):
        self.retry_after=min(3600,max(0,int(retry_after or 0)))
        super().__init__('Telegram: '+('слишком частая отправка; повторим позже' if code==429 else 'не удалось выполнить запрос. Проверьте токен, доступ к группе и права бота.'))


def telegram(token,method,args=None):
    request=urllib.request.Request('https://api.telegram.org/bot'+token+'/'+method,data=json.dumps(args or {}).encode(),headers={'Content-Type':'application/json'})
    try:
        with urllib.request.urlopen(request,timeout=12) as response:result=json.load(response)
    except urllib.error.HTTPError as error:
        with error:
            try:result=json.load(error)
            except ValueError:result={}
        raise TelegramError(error.code,result.get('parameters',{}).get('retry_after',0)) from None
    except (OSError,ValueError):raise TelegramError() from None
    if not result.get('ok'):raise TelegramError(result.get('error_code',0),result.get('parameters',{}).get('retry_after',0))
    return result.get('result')


class Service:
    def __init__(self,database,transport=telegram):
        self.database=database;self.transport=transport;self.lock=threading.RLock();self.stop=threading.Event()
        with self.database() as db:
            db.executescript('''CREATE TABLE IF NOT EXISTS notification_config(id INTEGER PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notification_runtime(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS notification_pair(id INTEGER PRIMARY KEY,hash TEXT,expires REAL,epoch TEXT);
            CREATE TABLE IF NOT EXISTS alert_samples(event_key TEXT PRIMARY KEY,source TEXT,peer TEXT,created REAL,kind TEXT);
            CREATE INDEX IF NOT EXISTS alert_sample_peer ON alert_samples(source,peer,created);
            CREATE TABLE IF NOT EXISTS alerts(id INTEGER PRIMARY KEY,alert_key TEXT,kind TEXT,title TEXT,body TEXT,created REAL,last_seen REAL,count INTEGER NOT NULL DEFAULT 1,read INTEGER NOT NULL DEFAULT 0,delivery TEXT NOT NULL DEFAULT 'local');
            CREATE INDEX IF NOT EXISTS alerts_key ON alerts(alert_key,created);''')
            db.execute('INSERT OR IGNORE INTO notification_config VALUES(1,?)',(json.dumps(DEFAULTS),))
    def config(self,db=None):
        if db is None:
            with self.database() as db:return self.config(db)
        return {**DEFAULTS,**json.loads(db.execute('SELECT value FROM notification_config WHERE id=1').fetchone()[0])}
    def state(self,key,default=None,db=None):
        if db is None:
            with self.database() as db:return self.state(key,default,db)
        row=db.execute('SELECT value FROM notification_runtime WHERE key=?',(key,)).fetchone()
        return json.loads(row[0]) if row else default
    def put(self,db,key,value):db.execute('INSERT OR REPLACE INTO notification_runtime VALUES(?,?)',(key,json.dumps(value)))
    def public(self):
        with self.database() as db:
            cfg=self.config(db);pair=db.execute('SELECT expires FROM notification_pair WHERE id=1 AND epoch=?',(cfg['epoch'],)).fetchone()
            public={k:v for k,v in cfg.items() if k not in ('bot_token','epoch')}
            public.update(token_set=bool(cfg['bot_token']),pair_expires=pair[0] if pair else None,last_scan=self.state('last_scan',None,db),scan_errors=self.state('scan_errors',{},db),delivery_error=self.state('delivery_error','',db),last_delivery=self.state('last_delivery',None,db),connection_error=self.state('poll_error','',db),binding_error=self.state('binding_error','',db),pending=db.execute("SELECT count(*) FROM alerts WHERE delivery='pending'").fetchone()[0])
            return public
    def save(self,data):
        with self.lock:
            cfg=self.config()
            for key in ('enabled','http_errors','bot_errors','telegram_enabled'):
                if key in data:
                    if not isinstance(data[key],bool):raise ValueError('Проверьте переключатели уведомлений')
                    cfg[key]=data[key]
            for key,minimum,maximum in [('http_limit',10,10000),('bot_limit',5,1000),('cooldown',60,3600)]:
                if key in data:
                    value=data[key]
                    if isinstance(value,bool) or not isinstance(value,int) or not minimum<=value<=maximum:raise ValueError('Проверьте пороги и интервал повторных уведомлений')
                    cfg[key]=value
            token=data.get('bot_token','')
            if not isinstance(token,str):raise ValueError('Проверьте токен отдельного бота')
            token=token.strip()
            if token and token!=cfg['bot_token']:
                if not re.fullmatch(r'[0-9]{6,20}:[A-Za-z0-9_-]{20,100}',token):raise ValueError('Проверьте токен отдельного бота')
                if token.split(':')[0] in monitor.installed_bot_ids():raise ValueError('Это действующий бот приложения. Создайте отдельного бота Guard в BotFather.')
                identity=self.transport(token,'getMe')
                if not identity.get('is_bot'):raise ValueError('Telegram не подтвердил бота')
                if self.transport(token,'getWebhookInfo').get('url'):raise ValueError('У этого бота подключён webhook. Создайте отдельного бота для Guard.')
                cfg.update(bot_token=token,bot_username=identity.get('username',''),bot_id=str(identity['id']),group_id='',group_title='',epoch=secrets.token_hex(16))
            if cfg['telegram_enabled'] and not cfg['bot_token']:raise ValueError('Сначала введите токен нового бота Guard')
            with self.database() as db:
                old=self.config(db)
                db.execute('UPDATE notification_config SET value=? WHERE id=1',(json.dumps(cfg),))
                if old['epoch']!=cfg['epoch']:
                    db.execute('DELETE FROM notification_pair');self.put(db,'bot_offset',0)
                    db.execute("UPDATE alerts SET delivery='local' WHERE delivery='pending'")
                if not old['enabled'] and cfg['enabled']:
                    self.put(db,'http_started',time.time())
                    db.execute("DELETE FROM notification_runtime WHERE key LIKE 'cursor_%'")
                if not cfg['telegram_enabled'] or not cfg['enabled']:
                    db.execute("UPDATE alerts SET delivery='local' WHERE delivery='pending'")
                self.put(db,'delivery_error','')
            return self.public()
    def pair(self):
        with self.lock,self.database() as db:
            cfg=self.config(db)
            if not cfg['bot_token']:raise ValueError('Сначала сохраните токен отдельного бота')
            code=secrets.token_hex(16);expires=time.time()+900
            self.put(db,'binding_error','')
            db.execute('INSERT OR REPLACE INTO notification_pair VALUES(1,?,?,?)',(hashlib.sha256(code.encode()).hexdigest(),expires,cfg['epoch']))
            return {'command':'/guard'+('@'+cfg['bot_username'] if cfg['bot_username'] else '')+' '+code,'expires':expires}
    def poll(self):
        with self.lock:
            cfg=self.config()
            if not cfg['bot_token']:return
            updates=self.transport(cfg['bot_token'],'getUpdates',{'offset':self.state('bot_offset',0),'timeout':0,'limit':100,'allowed_updates':['message']})
            with self.database() as db:self.put(db,'poll_error','')
            for update in updates:
                message=update.get('message',{});chat=message.get('chat',{});sender=message.get('from',{})
                match=re.fullmatch(r'/guard(?:@([A-Za-z0-9_]+))?\s+([a-f0-9]{32})',message.get('text','').strip())
                if match and (not match[1] or match[1].lower()==cfg['bot_username'].lower()) and chat.get('type') in ('group','supergroup') and not sender.get('is_bot'):
                    with self.database() as db:pair=db.execute('SELECT * FROM notification_pair WHERE id=1').fetchone()
                    valid=pair and pair['epoch']==cfg['epoch'] and pair['expires']>=time.time() and hmac.compare_digest(pair['hash'],hashlib.sha256(match[2].encode()).hexdigest())
                    if valid:
                        member=self.transport(cfg['bot_token'],'getChatMember',{'chat_id':chat['id'],'user_id':sender['id']})
                        if member.get('status') in ('creator','administrator') and str(chat['id']).startswith('-'):
                            # Send permission must work before changing the destination.
                            self.transport(cfg['bot_token'],'sendMessage',{'chat_id':chat['id'],'text':'✅ Guard подключён. Сюда будут приходить предупреждения о высокой частоте запросов, ошибках 500–599 и сбоях ботов. Настройки: https://guard.vano.sbena.net','link_preview_options':{'is_disabled':True}})
                            with self.database() as db:
                                cfg.update(group_id=str(chat['id']),group_title=str(chat.get('title','Группа'))[:160])
                                db.execute('UPDATE notification_config SET value=? WHERE id=1',(json.dumps(cfg),));db.execute('DELETE FROM notification_pair')
                                db.execute("UPDATE alerts SET delivery='local' WHERE delivery='pending'")
                                self.put(db,'delivery_error','');self.put(db,'binding_error','')
                        else:
                            with self.database() as db:self.put(db,'binding_error','Команду подключения должен отправить администратор группы. Получите новую команду и отправьте её от своего аккаунта администратора.')
                with self.database() as db:self.put(db,'bot_offset',int(update['update_id'])+1)
    def record(self,db,cfg,key,kind,title,body,count=1,now=None):
        now=time.time() if now is None else now
        row=db.execute('SELECT id FROM alerts WHERE alert_key=? AND created>? ORDER BY id DESC LIMIT 1',(key,now-cfg['cooldown'])).fetchone()
        if row:
            db.execute('UPDATE alerts SET count=count+?,last_seen=?,body=?,read=0 WHERE id=?',(count,now,body,row['id']))
        else:
            delivery='pending' if cfg['telegram_enabled'] and cfg['bot_token'] and cfg['group_id'] else 'local'
            db.execute('INSERT INTO alerts(alert_key,kind,title,body,created,last_seen,count,delivery) VALUES(?,?,?,?,?,?,?,?)',(key,kind,title,body,now,now,count,delivery))
    def ingest(self,events,now=None):
        now=time.time() if now is None else now
        with self.lock,self.database() as db:
            cfg=self.config(db)
            if not cfg['enabled']:return
            touched=collections.Counter();error_groups={};responses=collections.defaultdict(collections.Counter)
            for event in events:
                added=db.execute('INSERT OR IGNORE INTO alert_samples VALUES(?,?,?,?,?)',(event['key'],event['source'],event['peer'],event['time'],event['kind'])).rowcount
                if not added:continue
                if event['kind']=='in':
                    touched[(event['source'],event['peer'])]+=1
                    if 'status' in event:responses[(event['source'],event['peer'])][event['status']]+=1
                elif event['kind']=='error':
                    key=event['error_key'];group=error_groups.setdefault(key,{'event':event,'count':0});group['count']+=1
            for (source,peer),new_count in touched.items():
                total=db.execute("SELECT count(*) FROM alert_samples WHERE kind='in' AND source=? AND peer=? AND created>?",(source,peer,now-60)).fetchone()[0]
                is_web=source.startswith('web:');threshold=cfg['http_limit'] if is_web else cfg['bot_limit']
                if total>=threshold:
                    label=source[4:] if is_web else monitor.BOTS.get(source[4:],{}).get('name',source)
                    title='Высокая частота '+('HTTP-запросов' if is_web else 'сообщений боту')
                    body=f'{label}\n'+('IP: ' if is_web else 'Telegram ID: ')+peer+f'\nЗа последние 60 секунд: {total}. Порог: {threshold}.\nПроверьте активность в Guard.'
                    if is_web:
                        codes=responses[(source,peer)]
                        body+='\nОтветы в новых записях: '+', '.join(str(code)+' — '+str(count) for code,count in sorted(codes.items()))+'.'
                        body+='\n403/429 — запрос отклонён; 308 — перенаправлен. Число запросов не означает успешный взлом. Статус бана — во вкладке «Защита».'
                    self.record(db,cfg,'spam:'+source+':'+peer,'spam',title,body,new_count,now)
            for key,group in error_groups.items():
                event=group['event'];enabled=cfg['http_errors'] if event['source'].startswith('web:') else cfg['bot_errors']
                if enabled:self.record(db,cfg,key,'error',event['title'],event['body'],group['count'],now)
            db.execute('DELETE FROM alert_samples WHERE created<?',(now-600,))
            db.execute('DELETE FROM alerts WHERE created<? OR id<(SELECT COALESCE(MAX(id),0)-5000 FROM alerts)',(now-30*86400,))
    def collect(self):
        now=time.time();errors={}
        started=self.state('http_started')
        if started is None:
            started=now
            with self.database() as db:self.put(db,'http_started',started)
        try:
            try:
                raw=monitor.docker_api.logs(monitor.PROXY,max(started,now-180),tail=2000)
            except ValueError:
                raw=monitor.docker_api.logs(monitor.PROXY,max(started,now-180),tail=200)
                errors['http_sample']='Большой поток запросов: проверена сокращённая выборка журнала.'
            if not self.state('traffic_backfill_done',False):
                try:
                    previous=monitor.docker_api.logs(monitor.PROXY,now-86400,tail=10000)
                except ValueError:previous=raw
                ip_activity.record_raw(self.database,previous,now-86400)
                with self.database() as db:self.put(db,'traffic_backfill_done',True)
            ip_activity.record_raw(self.database,raw,max(started,now-180))
            self.ingest(http_samples(raw,max(started,now-180)),now)
        except (OSError,ValueError,TimeoutError):errors['http']='Не удалось проверить журнал запросов'
        for bot in monitor.BOTS:
            info=None
            try:
                info=monitor.docker_api.inspect(monitor.BOTS[bot]['container'])
                self.observe_bot(bot,info,now)
            except (OSError,ValueError,TimeoutError):
                errors[bot]=monitor.BOTS[bot]['name']+': Guard не смог проверить состояние контейнера; остановка бота не подтверждена.'
            try:
                cursor=self.state('cursor_'+bot)
                feed=monitor.bot_action(bot,'activity',{'after':cursor})
                self.ingest(bot_samples(bot,feed.get('events',[])),now)
                with self.database() as db:self.put(db,'cursor_'+bot,feed['cursor'])
            except (OSError,ValueError,TimeoutError):
                name=monitor.BOTS[bot]['name']
                errors[bot]=name+(': контейнер '+info['status']+'.' if info and info.get('status')!='running' else ': не удалось прочитать активность Guard. Это не подтверждает остановку бота; проверьте обновление интеграции Guard.')
        with self.database() as db:self.put(db,'last_scan',now);self.put(db,'scan_errors',errors)
    def observe_bot(self,bot,info,now):
        status=info.get('status','unknown');name=monitor.BOTS[bot]['name']
        if status not in ('running','exited','dead','restarting','paused','created'):return
        key='bot_health_'+bot
        with self.database() as db:
            previous=self.state(key,None,db);cfg=self.config(db)
            self.put(db,key,status)
            if not cfg['enabled'] or not cfg['bot_errors'] or previous==status:return
            if status!='running':
                cause='Нехватка памяти (OOM).' if info.get('oom_killed') else 'Код завершения: '+str(info.get('exit_code','—'))+'. Точная причина требует проверки журнала.'
                self.record(db,cfg,'bot_health:'+bot,'error','Контейнер бота «'+name+'» не работает',f'Бот: {name}\nКонтейнер: {monitor.BOTS[bot]["container"]}\nСостояние: {status}\n{cause}\nОткройте «Боты» в Guard для диагностики и запуска.',1,now)
            elif previous and previous!='running':
                self.record(db,cfg,'bot_recovered:'+bot,'recovery','Контейнер бота «'+name+'» снова запущен',f'Бот: {name}\nКонтейнер снова работает. Доставка сообщений отдельно не проверялась.',1,now)
    def listing(self):
        with self.database() as db:
            return {'alerts':[dict(r) for r in db.execute('SELECT id,kind,title,body,created,last_seen,count,read,delivery FROM alerts ORDER BY id DESC LIMIT 100')],'unread':db.execute('SELECT count(*) FROM alerts WHERE read=0').fetchone()[0],'config':self.public()}
    def acknowledge(self,identifier):
        if isinstance(identifier,bool) or not isinstance(identifier,int) or identifier<0:raise ValueError('Выберите уведомление')
        with self.database() as db:
            if identifier:db.execute('UPDATE alerts SET read=1 WHERE id=?',(identifier,))
            else:db.execute('UPDATE alerts SET read=1')
    def deliver(self,test=False):
        with self.lock:
            cfg=self.config();now=time.time()
            if not cfg['telegram_enabled'] or not cfg['bot_token'] or not cfg['group_id']:
                if test:raise ValueError('Сохраните токен, включите Telegram и подключите группу')
                return
            if not test and (not cfg['enabled'] or now<self.state('retry_at',0) or now-self.state('last_delivery',0)<30):return
            with self.database() as db:rows=[dict(r) for r in db.execute("SELECT id,title,body,count FROM alerts WHERE delivery='pending' ORDER BY id LIMIT 5")]
            if not test and not rows:return
            text='✅ Guard: проверка уведомлений. Группа подключена, отправка работает.' if test else '🛡 Guard · предупреждения\n\n'+'\n\n'.join(f"#{r['id']} · {r['title']}\n{r['body']}\nСобытий: {r['count']}" for r in rows)
            if len(text)>3800:text=text[:3750]+'\n… Подробности в Guard.'
            try:
                self.transport(cfg['bot_token'],'sendMessage',{'chat_id':cfg['group_id'],'text':text+'\n\nhttps://guard.vano.sbena.net','link_preview_options':{'is_disabled':True}})
            except TelegramError as error:
                with self.database() as db:self.put(db,'delivery_error',str(error));self.put(db,'retry_at',now+max(60,error.retry_after))
                raise
            with self.database() as db:
                if not test:
                    db.executemany("UPDATE alerts SET delivery='sent' WHERE id=?",[(r['id'],) for r in rows])
                self.put(db,'delivery_error','');self.put(db,'last_delivery',now);self.put(db,'retry_at',0)
    def start(self):
        def work():
            next_scan=0
            while not self.stop.is_set():
                try:
                    try:self.poll()
                    except (ValueError,OSError,TimeoutError):
                        with self.database() as db:self.put(db,'poll_error','Не удалось связаться с отдельным ботом Guard. Проверьте токен, права и отсутствие второго экземпляра.')
                    if time.monotonic()>=next_scan:
                        self.collect();next_scan=time.monotonic()+30
                    try:self.deliver()
                    except (ValueError,OSError,TimeoutError):pass
                except Exception:
                    # Never log raw transport errors: request URLs can contain credentials.
                    try:
                        with self.database() as db:self.put(db,'scan_errors',{'worker':'Ошибка проверки. Повторим автоматически.'})
                    except Exception:pass
                self.stop.wait(5)
        self.thread=threading.Thread(target=work,daemon=True,name='guard-alerts');self.thread.start()


def http_samples(raw,since):
    result=[]
    for event in monitor.http_events(raw,since):
        source='web:'+event['host'];key=hashlib.sha256(json.dumps(event,sort_keys=True).encode()).hexdigest()
        result.append({'key':key,'source':source,'peer':event['ip'],'time':event['time'],'kind':'in','status':event['status']})
        if 500<=event['status']<=599:
            result.append({'key':key+':error','source':source,'peer':event['ip'],'time':event['time'],'kind':'error','error_key':f"http:{event['host']}:{event['status']}:{event['path']}",'title':f"Ошибка HTTP {event['status']}",'body':f"Сайт: {event['host']}\nIP: {event['ip']}\n{event['method']} {event['path']}\nСервер вернул {event['status']}."})
    return result


def bot_samples(bot,events):
    result=[]
    for event in events:
        if event.get('direction') not in ('in','blocked','error'):continue
        error=event['direction']=='error';person=str(event['person']);name=monitor.BOTS[bot]['name']
        identity='' if person=='0' else f"Участник: {str(event.get('name',''))[:80] or person}\nTelegram ID: {person}\n"
        text=str(event.get('text',''))[:400]
        detail=('\n'+bot_diagnostics.summary(text)+'\nСбой одного действия не подтверждает остановку всего бота.') if error else ''
        result.append({'key':f"bot:{bot}:{event['id']}",'source':'bot:'+bot,'peer':person,'time':event['created'],'kind':'error' if error else 'in','error_key':'bot_error:'+bot+':'+person,'title':'Сбой действия бота «'+name+'»','body':f"Бот: {name}\n{identity}{text}{detail}"})
    return result
