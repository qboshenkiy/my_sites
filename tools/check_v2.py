"""Feature checks against two isolated PHP servers. No real Telegram traffic."""
import http.cookiejar,io,json,os,subprocess,tempfile,time,urllib.error,urllib.request,zipfile
from pathlib import Path
from xml.etree import ElementTree as ET

ROOT=Path(__file__).resolve().parents[1]
PHP='C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
class Client:
 def __init__(self,base):self.base=base;self.csrf='';self.token='';self.o=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
 def call(self,a,data=None,status=200,suffix=''):
  h={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
  if self.token:h['X-Player-Token']=self.token
  req=urllib.request.Request(self.base+'api.php?action='+a+suffix,data=json.dumps(data).encode() if data is not None else None,headers=h)
  try:r=self.o.open(req,timeout=10)
  except urllib.error.HTTPError as e:r=e
  content=r.read();assert r.status==status,(a,r.status,content)
  return json.loads(content) if 'json' in r.headers.get('Content-Type','') else content
 def boot(self):b=self.call('bootstrap');self.csrf=b['csrf'];return b

def spawn(folder,port,env):
 p=subprocess.Popen([PHP,'-S',f'127.0.0.1:{port}','-t',str(folder),str(folder/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
 c=Client(f'http://127.0.0.1:{port}/')
 for _ in range(50):
  try:c.boot();return p,c
  except urllib.error.URLError:time.sleep(.1)
 raise AssertionError('Server unavailable')

with tempfile.TemporaryDirectory(prefix='sites-v2-') as tmp:
 processes=[]
 try:
  env=dict(os.environ,QUIZ_DATA_DIR=tmp+'/pulse')
  p,h=spawn(ROOT,8102,env);processes.append(p);h.call('setup',{'password':'test-password-v2'});h.boot()
  image=h.call('upload_image',{'content':'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRZkAAAAASUVORK5CYII='})['id']
  assert h.call('image',suffix='&id='+image).startswith(b'\x89PNG')
  h.call('upload_image',{'content':'data:image/svg+xml;base64,PHN2Zy8+'},400)
  qs=[{'text':'Question '+str(i),'type':'quiz','options':['Yes','No'],'correct':0,'seconds':20,'category':'Category A','points':points,'image':image} for i,points in enumerate([10,20])]
  quiz=h.call('save',{'title':'Board','mode':'board','questions':qs})['id']
  h.call('save',{'title':'Bad','mode':'board','questions':[qs[0],qs[0]]},400)
  room=h.call('create_room',{'id':quiz})
  players=[Client(h.base),Client(h.base)]
  for i,c in enumerate(players):c.token=c.call('join',{'code':room['code'],'name':'Player '+str(i)})['token']
  h.call('control',{'room':room['id'],'command':'next'});s=h.call('state',suffix='&room='+room['id']);assert s['status']=='board'
  projector=Client(h.base);ps=projector.call('state',suffix='&projector='+s['projectorToken']);assert ps['status']=='board'
  projector.boot();projector.call('control',{'room':room['id'],'command':'finish'},401)
  h.call('control',{'room':room['id'],'command':'select','index':1})
  for c in players:c.call('answer',{'index':1,'choice':0})
  h.call('control',{'room':room['id'],'command':'reveal'})
  result=players[0].call('state');assert [p['score'] for p in result['players']]==[20,20] and [p['rank'] for p in result['players']]==[1,1]
  h.call('control',{'room':room['id'],'command':'next'});h.call('control',{'room':room['id'],'command':'select','index':1},400)
  h.call('control',{'room':room['id'],'command':'select','index':0});players[0].call('answer',{'index':0,'choice':0});players[1].call('answer',{'index':0,'choice':1})
  h.call('control',{'room':room['id'],'command':'reveal'});h.call('control',{'room':room['id'],'command':'next'});s=players[0].call('state');assert s['status']=='finished' and [p['score'] for p in s['players']]==[30,20] and [p['rank'] for p in s['players']]==[1,2]
  print('PASS Pulse: stored images, duplicate cells, board selection, all-player fixed scoring, rank ties, projector read-only access.')

  folder=ROOT/'marathon';env=dict(os.environ,MARATHON_DATA_DIR=tmp+'/reading',MARATHON_TEST_TODAY='2026-10-20',TELEGRAM_BOT_TOKEN='fake-token',TELEGRAM_BOT_USERNAME='fixture_bot')
  p,a=spawn(folder,8103,env);processes.append(p);a.call('setup',{'name':'Admin','login':'admin','password':'test-password-v2'});a.boot()
  uid=a.call('create_user',{'name':'Reader','role':'participant'})['id'];other=a.call('create_user',{'name':'Other','role':'participant'})['id']
  a.call('week_plan',{'week':2,'goal':60});invite=a.call('telegram_request',{'kind':'invite','user':uid})
  def bot(update):
   code='require "'+str(folder/'lib/telegram.php').replace('\\','/')+'"; echo json_encode(telegramUpdate(json_decode(stream_get_contents(STDIN),true)));'
   result=subprocess.run([PHP,'-r',code],input=json.dumps(update),env=env,text=True,capture_output=True);assert result.returncode==0,result.stderr;return json.loads(result.stdout)
  sender={'id':777111,'is_bot':False,'username':'reader'};chat={'id':777111,'type':'private'}
  def approve(token,kind,update):return bot({'update_id':update,'callback_query':{'id':str(update),'from':sender,'message':{'chat':chat},'data':kind+'_'+token}})
  approve(invite['token'],'i',1)
  r=Client(a.base);r.boot();req=r.call('telegram_request',{'kind':'login'});approve(req['token'],'a',2);r.call('telegram_status',{'token':req['token']});r.boot()
  r.call('add_reading',{'chapters':10,'date':'2026-10-19','title':'Book','key':'entry-key-0001'})
  r.call('add_reading',{'chapters':10,'date':'2026-10-19','title':'Book','key':'entry-key-0001'})
  assert r.call('profile')['stats']['chapters']==10
  a.call('complete_week',{'user':uid,'week':1,'days':7})
  update={'update_id':3,'message':{'from':sender,'chat':chat,'text':'прочитал 50'}}
  response=bot(update);assert 'Зачтено' in response[0]['args']['text'];assert bot(update)==[]
  s=r.call('profile')['stats'];assert s['chapters']==67 and s['days']==8 and s['pace']['remaining']==0
  rejected=bot({'update_id':4,'message':{'from':sender,'chat':chat,'text':'прочитал 1'}});assert 'не больше 0' in rejected[0]['args']['text']
  r.call('add_reading',{'chapters':1,'date':'2026-10-20','key':'entry-key-0002'},400)
  a.call('week_result',{'user':uid,'week':1,'chapters':2},400)
  a.call('week_lock',{'week':1,'open':1});a.call('week_result',{'user':uid,'week':1,'chapters':3,'days':2})
  a.call('week_lock',{'week':1,'open':0});a.call('week_result',{'user':uid,'week':1,'chapters':4},400)
  r.call('profile',suffix='&user='+other,status=403)
  # Assign moderator to an existing linked participant; no separate account required.
  a.call('update_user',{'user':uid,'role':'moderator'});assert r.boot()['user']['role']=='moderator';r.call('overview')
  r.call('week_lock',{'week':1,'open':1},403)
  a.call('update_user',{'user':uid,'role':'participant'});r.boot()
  pace=a.call('profile',suffix='&user='+other)['stats']['pace'];assert pace['perDay']==10 and pace['daysLeft']==6
  xlsx=a.call('export_xlsx',suffix='&week=2')
  with zipfile.ZipFile(io.BytesIO(xlsx)) as z:
   assert z.testzip() is None
   for name in z.namelist():ET.fromstring(z.read(name))
   assert b'<f>IF(C2' in z.read('xl/worksheets/sheet1.xml')
  Path(tmp+'/report.xlsx').write_bytes(xlsx)
  print('PASS Marathon: daily/site/Telegram caps, duplicate updates, automatic days and pace, closed/reopened weeks, participant privacy, promotion, real OOXML workbook with formulas.')
 finally:
  for p in processes:p.terminate();p.wait(timeout=10)
