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
        if ip:events.append({'time':int(row.get('__REALTIME_TIMESTAMP','0'))/1e6,'ip':ip,'user':match[2][:80],'result':'success' if match[1].startswith('Accepted') else 'failed','method':match[1]})
    return events[-1000:]


def ssh(since):
    start=dt.datetime.fromtimestamp(since,dt.timezone.utc).isoformat()
    try:
        result=subprocess.run(['journalctl','-u','ssh.service','--since',start,'-n','10000','-o','json','--no-pager'],capture_output=True,timeout=12)
    except subprocess.TimeoutExpired:
        raise ValueError('Журнал SSH не успел загрузиться') from None
    if result.returncode:raise ValueError('Журнал SSH недоступен. Проверьте подключение журнала хоста.')
    return ssh_events(result.stdout.decode(errors='replace'))


def traffic(raw,since):
    addresses={};events=[];total=0;errors=0
    for line in raw.splitlines():
        try:row=json.loads(line)
        except ValueError:continue
        if not str(row.get('logger','')).startswith('http.log.access') or row.get('ts',0)<since:continue
        request=row.get('request',{});ip=valid_ip(str(request.get('remote_ip','')))
        if not ip:continue
        stamp=float(row['ts']);status=int(row.get('status',0));total+=1;errors+=int(status>=400)
        entry=addresses.setdefault(ip,{'ip':ip,'requests':0,'errors':0,'minutes':collections.Counter(),'last_seen':0})
        entry['requests']+=1;entry['errors']+=int(status>=400);entry['minutes'][int(stamp//60)]+=1;entry['last_seen']=max(entry['last_seen'],stamp)
        # Do not expose path segments, query tokens, cookies, headers or request bodies.
        path=urlsplit(str(request.get('uri','/'))).path
        parts=[re.sub(r'[^a-zA-Z0-9_.-]','',p)[:40] for p in path.split('/')[:3]]
        path='/'.join('[id]' if len(p)>24 or re.fullmatch(r'[0-9]+',p or '-') else p for p in parts)
        events.append({'time':stamp,'ip':ip,'host':str(request.get('host',''))[:180],'path':path,'status':status,'method':str(request.get('method',''))[:10]})
    rows=[]
    for entry in addresses.values():
        entry['peak_per_minute']=max(entry.pop('minutes').values(),default=0);rows.append(entry)
    return {'requests':total,'errors':errors,'ips':sorted(rows,key=lambda r:r['requests'],reverse=True)[:100],'events':events[-200:][::-1],'sample_limit':10000}


def bot_action(bot,action,data=None):
    if not isinstance(bot,str) or not isinstance(action,str) or bot not in BOTS or action not in ('people','history','block','unblock','send'):raise ValueError('Выберите бота и действие')
    item=BOTS[bot]
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
