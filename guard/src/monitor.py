import collections
import datetime as dt
import ipaddress
import json
import re
import subprocess
import time
from urllib.parse import urlsplit
import docker_api

BOTS={
 'marathon':{'name':'Марафон','container':'glava-marathon-bot-1','cli':['php','/var/www/html/lib/bot-guard.php']},
 'pulse':{'name':'Пульс','container':'pulse-bot-1','cli':['php','/var/www/html/assets/bot-guard.php']},
 'milk':{'name':'Молоко','container':'milk-duty-web-1','cli':['python','/app/src/bot_guard.py']},
}
PROXY='glava-marathon-proxy-1'


def valid_ip(value):
    try:return str(ipaddress.ip_address(value))
    except ValueError:return None


def ssh_events(raw):
    events=[]
    for line in raw.splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        message=str(row.get('MESSAGE',''))
        match=re.search(r'(Accepted (?:password|publickey)|Failed password|Invalid user) (?:for (?:invalid user )?)?([^ ]+) from ([0-9a-fA-F:.]+)',message)
        if not match:continue
        ip=valid_ip(match[3])
        if ip:
            try:stamp=int(row.get('__REALTIME_TIMESTAMP','0'))/1e6
            except (ValueError,TypeError):continue
            port=re.search(r' from [0-9a-fA-F:.]+ port ([0-9]{1,5})',message)
            events.append({'time':stamp,'ip':ip,'user':match[2][:80],'result':'success' if match[1].startswith('Accepted') else 'failed','method':match[1],'port':int(port[1]) if port else None})
    return events


def ssh(since):
    start=dt.datetime.fromtimestamp(since,dt.timezone.utc).isoformat()
    try:
        result=subprocess.run(['journalctl','-u','ssh.service','--since',start,'-n','10000','-o','json','--no-pager'],capture_output=True,timeout=12)
    except subprocess.TimeoutExpired:
        raise ValueError('Журнал SSH не успел загрузиться') from None
    if result.returncode:raise ValueError('Журнал SSH недоступен. Проверьте подключение журнала хоста.')
    return ssh_events(result.stdout.decode(errors='replace'))


def http_events(raw,since):
    for line in raw.splitlines():
        try:
            row=json.loads(line)
            if not isinstance(row,dict) or not str(row.get('logger','')).startswith('http.log.access'):continue
            stamp=float(row.get('ts',0))
            if stamp<since:continue
            request=row.get('request',{});ip=valid_ip(str(request.get('remote_ip','')))
            if not ip:continue
            status=int(row.get('status',0))
            path=urlsplit(str(request.get('uri','/'))).path
            parts=[re.sub(r'[^a-zA-Z0-9_.-]','',p)[:40] for p in path.split('/')[:3]]
            path='/'.join('[id]' if len(p)>24 or re.fullmatch(r'[0-9]+',p or '-') else p for p in parts)
            host=re.sub(r'[^a-zA-Z0-9.:-]','',str(request.get('host','')))[:180]
            yield {'time':stamp,'ip':ip,'host':host,'path':path,'status':status,'method':str(request.get('method',''))[:10]}
        except (ValueError,TypeError,AttributeError):continue


def traffic(raw,since):
    addresses={};events=[];total=0;errors=0
    for event in http_events(raw,since):
        ip=event['ip'];stamp=event['time'];status=event['status'];total+=1;errors+=int(status>=400)
        entry=addresses.setdefault(ip,{'ip':ip,'requests':0,'errors':0,'minutes':collections.Counter(),'last_seen':0})
        entry['requests']+=1;entry['errors']+=int(status>=400);entry['minutes'][int(stamp//60)]+=1;entry['last_seen']=max(entry['last_seen'],stamp)
        events.append(event)
    rows=[]
    for entry in addresses.values():
        entry['peak_per_minute']=max(entry.pop('minutes').values(),default=0);rows.append(entry)
    return {'requests':total,'errors':errors,'unique_ips':len(rows),'peak_per_minute':max((r['peak_per_minute'] for r in rows),default=0),'ips':sorted(rows,key=lambda r:r['requests'],reverse=True)[:100],'events':events[-200:][::-1],'sample_limit':10000}


def seed_people(bot):
    """Import known bindings without inventing any historical conversation."""
    item=BOTS[bot]
    if bot in ('marathon','pulse'):
        if bot=='marathon':
            location="(getenv('MARATHON_DATA_DIR')?:'/var/lib/marathon').'/marathon.sqlite'"
            sql="SELECT telegram_id AS id,name,COALESCE(telegram_name,'') AS username FROM users WHERE telegram_id IS NOT NULL"
        else:
            location="(getenv('QUIZ_DATA_DIR')?:'/var/lib/pulse').'/quiz.sqlite'"
            sql="SELECT t.telegram_id AS id,a.name,'' AS username FROM pulse_tg_accounts t JOIN pulse_accounts a ON a.id=t.user_id"
        script=("require "+json.dumps(item['cli'][1])+";$file="+location+";"
                "if(is_file($file)){try{$source=new PDO('sqlite:'.$file);$source->exec('PRAGMA query_only=ON;PRAGMA busy_timeout=3000');"
                "$q=guardDb()->prepare('INSERT OR IGNORE INTO people(id,name,username,last_seen) VALUES(?,?,?,0)');"
                "foreach($source->query("+json.dumps(sql)+") as $r){if(preg_match('/^[0-9]{1,20}$/',(string)$r['id']))$q->execute([(string)$r['id'],$r['name'],$r['username']]);}"
                "}catch(Throwable $e){}}echo json_encode(['ok'=>true]);")
        docker_api.execute(item['container'],['php','-r',script],user='www-data')
    else:
        script=("import sys,sqlite3,os,json;sys.path.insert(0,'/app/src');import bot_guard;"
                "p=os.path.join(os.getenv('DATA_DIR','/data'),'duty.sqlite');"
                "s=sqlite3.connect('file:'+p+'?mode=ro',uri=True);"
                "rows=list(s.execute('SELECT chat_id,name FROM people WHERE chat_id IS NOT NULL'));s.close();"
                "ctx=bot_guard.database();d=ctx.__enter__();"
                "d.executemany('INSERT OR IGNORE INTO people(id,name,username,last_seen) VALUES(?,?,?,0)',[(str(r[0]),r[1],'') for r in rows]);"
                "ctx.__exit__(None,None,None);print(json.dumps({'ok':True}))")
        docker_api.execute(item['container'],['python','-c',script])


def bot_action(bot,action,data=None):
    if not isinstance(bot,str) or not isinstance(action,str) or bot not in BOTS or action not in ('people','history','block','unblock','send','activity','identity'):raise ValueError('Выберите бота и действие')
    item=BOTS[bot]
    if action=='people':seed_people(bot)
    return docker_api.execute(item['container'],item['cli']+[action,json.dumps(data or {},ensure_ascii=False)],user='www-data' if bot!='milk' else None)


def bots():
    result=[]
    for key,item in BOTS.items():
        row={'id':key,'name':item['name']}
        try:row.update(docker_api.inspect(item['container']))
        except (OSError,ValueError):row['status']='unavailable'
        result.append(row)
    return result


def bot_control(bot,action):
    if not isinstance(bot,str) or not isinstance(action,str) or bot not in BOTS or action not in ('start','stop','restart'):raise ValueError('Выберите бота и действие')
    # Milk's bot shares its web process. Avoid stopping its website from the bot page.
    if bot=='milk':raise ValueError('Бот «Молоко» работает внутри сайта. Управляйте контейнером через GitDeck.')
    docker_api.request('POST','/containers/'+BOTS[bot]['container']+'/'+action+'?t=15')
    return {'ok':True}


def installed_bot_ids():
    result=set()
    for bot,item in BOTS.items():
        try:
            if bot!='milk':
                info=json.loads(docker_api.request('GET','/containers/'+item['container']+'/json'))
                for entry in info.get('Config',{}).get('Env',[]):
                    if entry.startswith('TELEGRAM_BOT_TOKEN='):
                        identity=entry.split('=',1)[1].split(':',1)[0]
                        if identity.isdecimal():result.add(identity)
            else:
                identity=bot_action(bot,'identity').get('bot_id')
                if identity:result.add(str(identity))
        except (OSError,ValueError,TimeoutError):continue
    return result
