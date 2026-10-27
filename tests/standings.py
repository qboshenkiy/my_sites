"""Real PHP/SQLite checks for frozen publications, equal-weight percentage ranking and access control."""
import http.cookiejar,json,os,shutil,socket,subprocess,tempfile,time,urllib.request,urllib.error
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or '/tmp/gitdeck-php-check/php'
class Client:
 def __init__(self,url):self.url=url;self.csrf='';self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def call(self,action,body=None,status=200):
  req=urllib.request.Request(self.url+'/api.php?action='+action,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
  try:r=self.opener.open(req)
  except urllib.error.HTTPError as e:r=e
  with r:data=json.load(r);assert r.status==status,(action,r.status,data);return data
 def boot(self):data=self.call('bootstrap');self.csrf=data['csrf'];return data
 def register(self,name,login):self.boot();self.call('register',{'name':name,'login':login,'password':'testing-password'});return self.boot()['user']
with tempfile.TemporaryDirectory() as tmp:
 with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
 url=f'http://127.0.0.1:{port}'
 server=subprocess.Popen([PHP,'-S',f'127.0.0.1:{port}','-t',str(ROOT)],env=dict(os.environ,QUIZ_DATA_DIR=tmp),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 try:
  admin=Client(url)
  for _ in range(60):
   try:admin.boot();break
   except OSError:time.sleep(.1)
  admin.call('setup',{'password':'testing-admin-password'});admin.boot()
  users=[];clients=[]
  for i,name in enumerate(['Зоя','Анна','Борис','Света']):
   client=Client(url);users.append(client.register(name,'reader_'+str(i)));clients.append(client)
  Client(url).call('standings',status=401)
  assert clients[0].call('standings')['participants']==[]
  def save(title,maximum,scores,old=None):
   payload={'title':title,'max_points':maximum,'held_on':'2026-10-27','scores':[{'user_id':users[i]['id'],'points':points} for i,points in scores.items()]}
   if old:payload.update(id=old['id'],revision=old['revision'])
   id=admin.call('save_assessment',payload)['id'];return next(a for a in admin.call('assessments')['assessments'] if a['id']==id)
  def publish(a,client=admin,status=200):return client.call('publish_results',{'id':a['id'],'revision':a['revision'],'publication_version':(a['publication'] or {}).get('version',0)},status)
  first=save('Тест 1000',1000,{0:800,1:600,2:0});second=save('Тест 100',100,{0:0,1:100,2:0})
  assert clients[0].call('standings')['participants']==[]
  publish(first,clients[0],403);publish(first);publish(first,status=409);publish(second)
  table=clients[0].call('standings');rows=table['participants']
  assert table['max_points']==1100 and table['published_count']==2
  assert rows[0]['name']=='Анна' and rows[0]['percent']==80 and rows[0]['rank']==1
  assert rows[1]['name']=='Зоя' and rows[1]['percent']==40 and rows[1]['rank']==2
  assert [r['rank'] for r in rows[2:]]==[3,3]
  assert sorted(r['completed'] for r in rows[2:])==[0,2]
  # A participant may release their own form, but cannot insert it into the common ranking.
  quiz=clients[0].call('save',{'title':'Личный тест','questions':[{'text':'Ответ?','type':'quiz','seconds':20,'options':['Да','Нет'],'correct':0,'points':100}]})['id']
  form=clients[0].call('form_create',{'quiz_id':quiz})
  clients[0].call('form_submit',{'token':form['token'],'answers':[0]})
  manager=clients[0].call('form_results&form='+form['id'])['form']
  clients[0].call('form_configure',{'form':form['id'],'revision':manager['revision'],'active':True,'published':True})
  assert clients[0].call('standings')['published_count']==2, 'Participant-owned forms must not bypass staff-only ranking publication'
  current=next(a for a in admin.call('assessments')['assessments'] if a['id']==first['id'])
  assert current['scores'][0]['name']=='Зоя', 'Per-test sorting must be by points, not alphabet'
  edited=save('Изменённый черновик',1000,{0:100,1:900,2:0},current)
  assert clients[0].call('standings')['participants'][0]['name']=='Анна','Edits must not alter published snapshot'
  assert next(t for t in clients[0].call('standings')['tests'] if t['id']==first['id'])['title']=='Тест 1000'
  publish(current,status=409)
  publish(edited)
  assert clients[0].call('standings')['participants'][0]['name']=='Анна'
  current=next(a for a in admin.call('assessments')['assessments'] if a['id']==first['id'])
  admin.call('delete_assessment',{'id':current['id'],'revision':current['revision']},409)
  admin.call('unpublish_results',{'id':current['id'],'revision':current['revision'],'publication_version':current['publication']['version']})
  assert clients[0].call('standings')['max_points']==100
  admin.call('delete_assessment',{'id':current['id'],'revision':current['revision']})
  print('PASS: explicit publication, frozen scores, equal-weight average percentages, ranking/ties/missing scores, republishing, unpinning and authorization')
 finally:server.terminate();server.wait(timeout=10)
