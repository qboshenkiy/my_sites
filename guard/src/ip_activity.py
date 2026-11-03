"""Redacted per-IP HTTP evidence kept locally; never stores bodies or credentials."""
import collections
import hashlib
import ipaddress
import json
import math
import re
import time
from urllib.parse import urlsplit,parse_qsl,unquote
from firewall_agent import canonical


SCHEMA='''CREATE TABLE IF NOT EXISTS traffic_entries(event_key TEXT PRIMARY KEY,ip TEXT,created REAL,site TEXT,status INTEGER,data TEXT);
CREATE INDEX IF NOT EXISTS traffic_ip_time ON traffic_entries(ip,created);
CREATE INDEX IF NOT EXISTS traffic_time ON traffic_entries(created);'''
PROBE=re.compile(r'(?i)(?:^|/)(?:\.env(?:[./]|$)|\.git(?:/|$)|\.svn(?:/|$)|\.aws(?:/|$)|\.ssh(?:/|$)|phpinfo\.php|info\.php|wp-login\.php|wp-admin(?:/|$)|vendor/phpunit|actuator/(?:env|heapdump)|etc/passwd)')


def safe_text(value,limit=300):
    value=re.sub(r'[\x00-\x1f\x7f]','',str(value))
    value=re.sub(r'\b\d{6,20}:[A-Za-z0-9_-]{20,}|sk_[A-Za-z0-9_-]{16,}|\b[a-fA-F0-9]{32,}\b','[код скрыт]',value)
    return value[:limit]


def path_text(path):
    parts=[]
    for part in path.split('/'):
        if re.fullmatch(r'[A-Za-z0-9_-]{32,}',part) or len(part)>100:part='[скрытый сегмент]'
        parts.append(safe_text(part,100))
    return '/'.join(parts)[:800]


def events(raw,since=0):
    for line in raw.splitlines():
        try:
            row=json.loads(line)
            if not isinstance(row,dict) or not str(row.get('logger','')).startswith('http.log.access'):continue
            stamp=float(row.get('ts',0))
            if not math.isfinite(stamp) or stamp<since:continue
            request=row.get('request',{});ip=canonical(request.get('remote_ip',''))
            uri=urlsplit(str(request.get('uri','/')));path=path_text(uri.path)
            truncated=False
            try:query=parse_qsl(uri.query,keep_blank_values=True,max_num_fields=100)
            except ValueError:query=[];truncated=True
            action=next((v for k,v in query if k=='action' and re.fullmatch(r'[a-z_]{1,30}',v)),None)
            keys=sorted({safe_text(k,40) if len(k)<25 else '[поле скрыто]' for k,v in query})[:20]
            header=request.get('headers',{});ua=next((v for k,v in header.items() if k.lower()=='user-agent'),[])
            if isinstance(ua,list):ua=' '.join(str(v) for v in ua[:2])
            duration=float(row.get('duration',0));duration=round(duration*1000,2) if math.isfinite(duration) and duration>=0 else None
            entry={'time':stamp,'ip':ip,'host':safe_text(request.get('host',''),180),'method':safe_text(request.get('method',''),12),'path':path,'query_keys':keys,'query_truncated':truncated,'action':action,'status':int(row.get('status',0)),'user_agent':safe_text(ua,240),'protocol':safe_text(request.get('proto',''),20),'source_port':safe_text(request.get('remote_port',''),6),'duration_ms':duration,'response_bytes':max(0,int(row.get('size',0) or 0)),'request_bytes':max(0,int(row.get('bytes_read',0) or 0)),'probe':bool(PROBE.search(unquote(unquote(uri.path))))}
            entry['event_key']=hashlib.sha256(json.dumps(entry,sort_keys=True,ensure_ascii=False).encode()).hexdigest()
            yield entry
        except (ValueError,TypeError,AttributeError):continue


def record(database,entries):
    with database() as db:
        db.executescript(SCHEMA)
        db.executemany('INSERT OR IGNORE INTO traffic_entries VALUES(?,?,?,?,?,?)',[(e['event_key'],e['ip'],e['time'],e['host'],e['status'],json.dumps(e,ensure_ascii=False)) for e in entries])
        db.execute('DELETE FROM traffic_entries WHERE created<?',(time.time()-7*86400,))
        db.execute('DELETE FROM traffic_entries WHERE event_key IN (SELECT event_key FROM traffic_entries ORDER BY created DESC LIMIT -1 OFFSET 200000)')


def record_raw(database,raw,since=0):record(database,list(events(raw,since)))


def report(database,ip,period=86400):
    ip=canonical(ip)
    if period not in (3600,86400,604800):raise ValueError('Выберите час, сутки или неделю')
    since=time.time()-period
    with database() as db:
        db.executescript(SCHEMA)
        total,first,last=db.execute('SELECT count(*),min(created),max(created) FROM traffic_entries WHERE ip=? AND created>=?',(ip,since)).fetchone()
        statuses={str(r[0]):r[1] for r in db.execute('SELECT status,count(*) FROM traffic_entries WHERE ip=? AND created>=? GROUP BY status',(ip,since))}
        sites=[{'host':r[0],'count':r[1]} for r in db.execute('SELECT site,count(*) FROM traffic_entries WHERE ip=? AND created>=? GROUP BY site ORDER BY count(*) DESC',(ip,since))]
        paths=[{'path':r[0],'method':r[1],'count':r[2]} for r in db.execute("SELECT json_extract(data,'$.path'),json_extract(data,'$.method'),count(*) FROM traffic_entries WHERE ip=? AND created>=? GROUP BY 1,2 ORDER BY count(*) DESC LIMIT 30",(ip,since))]
        recent=[json.loads(r[0]) for r in db.execute('SELECT data FROM traffic_entries WHERE ip=? AND created>=? ORDER BY created DESC LIMIT 500',(ip,since))]
        times=[r[0] for r in db.execute('SELECT created FROM traffic_entries WHERE ip=? AND created>=? ORDER BY created',(ip,since))]
        probes=db.execute("SELECT count(*),sum(CASE WHEN status>=200 AND status<300 THEN 1 ELSE 0 END) FROM traffic_entries WHERE ip=? AND created>=? AND json_extract(data,'$.probe')=1",(ip,since)).fetchone()
    left=peak=0
    for right,stamp in enumerate(times):
        while times[left]<=stamp-60:left+=1
        peak=max(peak,right-left+1)
    findings=[]
    if probes[0]:findings.append(f'Запросов к типовым служебным путям: {probes[0]}. Это характерно для автоматического сканирования.')
    if probes[1]:findings.append('Некоторые служебные пути вернули 2xx. Нужно проверить содержимое ответа: сам код ещё не доказывает утечку.')
    if total and statuses.get('404',0)==total:findings.append('Все сохранённые запросы вернули 404. Признаков получения запрошенных файлов в этой выборке нет.')
    if not total:findings.append('Сохранённых HTTP-запросов этого IP за период нет. Журнал может быть неполным или запросы уже блокируются до сайта.')
    return {'ip':ip,'is_public':ipaddress.ip_address(ip).is_global,'period':period,'total':total,'first_seen':first,'last_seen':last,'peak_per_minute':peak,'statuses':statuses,'sites':sites,'paths':paths,'events':recent,'findings':findings,'event_limit':500,'retention_days':7}


def peers(database,period=86400):
    if period not in (3600,86400,604800):raise ValueError('Выберите период')
    with database() as db:
        db.executescript(SCHEMA)
        return [{'ip':r[0],'requests':r[1],'last_seen':r[2]} for r in db.execute('SELECT ip,count(*),max(created) FROM traffic_entries WHERE created>=? GROUP BY ip ORDER BY count(*) DESC LIMIT 100',(time.time()-period,))]
