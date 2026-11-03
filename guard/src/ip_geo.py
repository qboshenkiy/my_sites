"""Approximate network geolocation, on-demand and cached; not a person's location."""
import ipaddress
import json
import math
import time
import urllib.request
from firewall_agent import canonical


def fetch(url):
    req=urllib.request.Request(url,headers={'User-Agent':'Guard-IP-lookup/1.0'})
    with urllib.request.urlopen(req,timeout=7) as response:
        raw=response.read(1024*1024+1)
        if len(raw)>1024*1024:raise ValueError('Ответ слишком большой')
        return json.loads(raw)


def cloud_range(database,ip):
    with database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS ip_geo_aux(key TEXT PRIMARY KEY,data TEXT,fetched REAL)')
        row=db.execute("SELECT data,fetched FROM ip_geo_aux WHERE key='google_cloud'").fetchone()
    if row and row[1]>time.time()-86400:payload=json.loads(row[0])
    else:
        payload=fetch('https://www.gstatic.com/ipranges/cloud.json')
        with database() as db:db.execute('INSERT OR REPLACE INTO ip_geo_aux VALUES(?,?,?)',('google_cloud',json.dumps(payload),time.time()))
    address=ipaddress.ip_address(ip)
    for item in payload.get('prefixes',[]):
        prefix=item.get('ipv4Prefix') or item.get('ipv6Prefix')
        if prefix and address in ipaddress.ip_network(prefix):return {'prefix':prefix,'region':item.get('scope'),'provider':item.get('service')}
    return None


def lookup(database,raw):
    ip=canonical(raw)
    if not ipaddress.ip_address(ip).is_global:return {'ip':ip,'available':False,'note':'Локальный или служебный адрес: география не определяется'}
    with database() as db:
        db.execute('CREATE TABLE IF NOT EXISTS ip_geography(ip TEXT PRIMARY KEY,data TEXT,fetched REAL)')
        row=db.execute('SELECT data,fetched FROM ip_geography WHERE ip=?',(ip,)).fetchone()
        if row and row[1]>time.time()-86400:return json.loads(row[0])
    result={'ip':ip,'available':False,'fetched_at':time.time(),'note':'Примерная география сети или дата-центра, не местонахождение человека.'}
    try:
        data=fetch('https://ipinfo.io/'+ip+'/json')
        for key in ('city','region','country','org','hostname','timezone'):
            result[key]=str(data.get(key,''))[:180]
        coordinates=str(data.get('loc','')).split(',')
        if len(coordinates)==2:
            latitude,longitude=map(float,coordinates)
            if math.isfinite(latitude) and math.isfinite(longitude) and -90<=latitude<=90 and -180<=longitude<=180:result.update(latitude=latitude,longitude=longitude,available=True)
        result.update(source='IPinfo',source_url='https://ipinfo.io/'+ip)
    except (OSError,ValueError,TypeError):result['error']='Сервис географии временно недоступен'
    if 'Google' in result.get('org','') or not result['available']:
        try:
            cloud=cloud_range(database,ip)
            if cloud:
                result.update(cloud_prefix=cloud['prefix'],cloud_region=cloud['region'])
                if cloud['region']=='asia-southeast3':
                    result.update(available=True,country='TH',city='Bangkok',region='Bangkok',latitude=13.7563,longitude=100.5018,org=result.get('org') or 'Google Cloud',source='Google Cloud + IPinfo' if not result.get('error') else 'Google Cloud',source_url='https://www.gstatic.com/ipranges/cloud.json');result.pop('error',None)
        except (OSError,ValueError,TypeError):pass
    with database() as db:
        db.execute('INSERT OR REPLACE INTO ip_geography VALUES(?,?,?)',(ip,json.dumps(result,ensure_ascii=False),time.time() if not result.get('error') else time.time()-86100))
    return result
