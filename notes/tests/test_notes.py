import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
TEMP=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=TEMP.name;os.environ['COOKIE_SECURE']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import app,bot
class NotesTests(unittest.TestCase):
 def setUp(self):
  with app.database() as db:
   for t in ['notes','folders','versions','attempts','sync_mutations','telegram','links','bot_updates','bot_state','bot_info']:db.execute('DELETE FROM '+t)
  salt='ef'*16;Path(TEMP.name,'password.json').write_text(json.dumps({'salt':salt,'digest':hashlib.scrypt(b'notes-test-password',salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()}))
  self.client=app.app.test_client();self.csrf=self.post('/api/login',{'password':'notes-test-password'}).json['csrf']
 def post(self,url,data):return self.client.post(url,json={'csrf':getattr(self,'csrf',''),**data},headers={'Origin':'http://localhost'})
 def create(self,folder=None):return self.post('/api/note/create',{'folder_id':folder}).json
 def save(self,n,**patch):return self.post('/api/note/save',{**n,**patch})
 def test_photos_sync_validation_and_old_clients(self):
  import base64
  photo={'name':'Снимок.jpg','data':'data:image/jpeg;base64,'+base64.b64encode(b'\xff\xd8\xfftest\xff\xd9').decode()}
  n=self.save(self.create(),title='Фото с телефона',photos=[photo]).json
  self.assertEqual(n['photos'],[photo])
  response=self.client.get('/api/offline');self.assertEqual(self.client.get('/api/offline',headers={'If-None-Match':response.headers['ETag']}).status_code,304)
  self.assertEqual(self.client.get('/api/offline').json['notes'][0]['photos'],[photo])
  legacy={k:v for k,v in n.items() if k!='photos'}
  n=self.save(legacy,body='Правка на ноутбуке').json
  self.assertEqual(n['photos'],[photo])
  op={'mutation_id':'f'*32,'base_revision':n['revision'],'entity':{**n,'body':'Офлайн с фото'}}
  self.assertEqual(self.post('/api/sync',op).status_code,200)
  self.assertEqual(self.client.get('/api/note/'+n['id']).json['photos'],[photo])
  self.assertEqual(self.post('/api/sync',op).status_code,200)
  self.assertEqual(self.save(self.client.get('/api/note/'+n['id']).json,photos=[{'data':'data:image/svg+xml;base64,AAAA'}]).status_code,400)
  self.assertEqual(self.save(self.client.get('/api/note/'+n['id']).json,photos=[photo]*5).status_code,400)
  self.assertEqual(app.app.test_client().get('/api/note/'+n['id']).status_code,401)
  op['mutation_id']='e'*32
  result=self.post('/api/sync',op).json
  self.assertTrue(result['conflict'])
  self.assertEqual(self.client.get('/api/note/'+result['id']).json['photos'],[photo])
  self.assertEqual(self.client.get('/api/export').json['notes'][0]['photos'],[photo])
 def test_auth_csrf_and_private_exports(self):
  self.assertEqual(app.app.test_client().get('/api/notes').status_code,401)
  self.assertEqual(app.app.test_client().get('/api/export').status_code,401)
  self.assertEqual(self.post('/api/note/create',{'csrf':'wrong'}).status_code,403)
  self.assertEqual(self.client.post('/api/note/create',json={'csrf':self.csrf}).status_code,403)
  self.assertEqual(self.client.get('/api/notes').headers['Cache-Control'],'no-store')
 def test_save_search_and_unicode(self):
  n=self.create();r=self.save(n,title='Идея',body='Поехать в БИШКЕК. <script>text</script>',pinned=True);self.assertEqual(r.status_code,200)
  self.assertEqual(r.json['revision'],2)
  found=self.client.get('/api/notes?q=бишкек').json;self.assertEqual(found['total'],1)
  self.assertEqual(self.client.get('/api/notes?q=%25').json['total'],0)
  self.assertEqual(self.client.get('/api/notes?view=pinned').json['total'],1)
  self.assertEqual(self.client.get('/api/note/'+n['id']).json['body'],'Поехать в БИШКЕК. <script>text</script>')
 def test_conflict_never_overwrites_other_client(self):
  n=self.create();first=self.save(n,body='Правка с компьютера');self.assertEqual(first.status_code,200)
  stale=self.save(n,body='Правка с телефона');self.assertEqual(stale.status_code,409)
  self.assertEqual(stale.json['current']['body'],'Правка с компьютера')
  self.assertEqual(self.client.get('/api/note/'+n['id']).json['body'],'Правка с компьютера')
 def test_trash_restore_preserves_contents(self):
  n=self.save(self.create(),title='Важное',body='Не потерять').json
  removed=self.post('/api/note/trash',{**n,'restore':False});self.assertEqual(removed.status_code,200)
  self.assertEqual(self.client.get('/api/notes').json['total'],0);self.assertEqual(self.client.get('/api/notes?view=trash').json['total'],1)
  self.assertEqual(self.save(removed.json,body='нельзя').status_code,409)
  restored=self.post('/api/note/trash',{**removed.json,'restore':True}).json
  self.assertEqual(restored['body'],'Не потерять');self.assertIsNone(restored['deleted'])
 def test_folders_and_exports(self):
  f=self.post('/api/folder',{'name':'Работа'}).json
  self.assertEqual(self.post('/api/folder',{'name':'РАБОТА'}).status_code,400)
  n=self.save(self.create(f['id']),title='План',body='Сделать').json
  self.assertEqual(self.client.get('/api/notes?folder='+str(f['id'])).json['total'],1)
  self.post('/api/folder/delete',{'id':f['id']})
  after=self.client.get('/api/note/'+n['id']).json;self.assertIsNone(after['folder_id']);self.assertEqual(after['body'],'Сделать')
  self.assertEqual(self.save(n,body='stale folder').status_code,409)
  export=self.client.get('/api/export').json;self.assertEqual(len(export['notes']),1);self.assertNotIn('attempts',export)
  self.assertIn('План',self.client.get('/api/note/'+n['id']+'/export').get_data(as_text=True))
 def test_offline_sync_is_idempotent_and_ordered(self):
  first={'mutation_id':'a'*32,'base_revision':0,'entity':{'id':'b'*32,'title':'Офлайн','body':'Первый текст','folder_id':None,'pinned':False,'deleted':None}}
  r=self.post('/api/sync',first);self.assertEqual(r.status_code,200);self.assertEqual(r.json['revision'],1)
  self.assertEqual(self.post('/api/sync',first).json,r.json)
  second={'mutation_id':'c'*32,'base_revision':0,'after':'a'*32,'entity':{**first['entity'],'body':'Вторая правка'}}
  self.assertEqual(self.post('/api/sync',second).json['revision'],2)
  self.assertEqual(self.post('/api/sync',second).json['revision'],2)
  snapshot=self.client.get('/api/offline').json;self.assertEqual(len(snapshot['notes']),1);self.assertEqual(snapshot['notes'][0]['body'],'Вторая правка')
  self.assertIn('csrf',snapshot)
 def test_offline_conflict_preserves_both_versions(self):
  n=self.save(self.create(),title='Общая',body='Исходный текст').json
  changed=self.save(n,body='Правка на другом устройстве').json
  offline={'mutation_id':'d'*32,'base_revision':n['revision'],'entity':{**n,'body':'Моя офлайн-правка'}}
  r=self.post('/api/sync',offline);self.assertEqual(r.status_code,200);self.assertTrue(r.json['conflict']);self.assertNotEqual(r.json['id'],n['id'])
  self.assertEqual(self.client.get('/api/note/'+n['id']).json['body'],'Правка на другом устройстве')
  copy=self.client.get('/api/note/'+r.json['id']).json;self.assertEqual(copy['body'],'Моя офлайн-правка')
  self.assertEqual(self.post('/api/sync',offline).json,r.json)
  next_change={'mutation_id':'e'*32,'after':'d'*32,'entity':{**n,'body':'Продолжение офлайн-правки'}}
  self.assertEqual(self.post('/api/sync',next_change).json['id'],r.json['id'])
  self.assertEqual(self.client.get('/api/note/'+n['id']).json['body'],'Правка на другом устройстве')
 def test_telegram_bot_pairing_capture_and_private_access(self):
  from unittest.mock import patch
  replies=[]
  def msg(uid,text,chat=42):return {'update_id':uid,'message':{'chat':{'id':chat,'type':'private'},'from':{'id':chat},'text':text}}
  with patch.object(bot,'send',side_effect=lambda chat,text,markup=None:replies.append((chat,text,markup))),patch.object(bot,'call',return_value={}):
   bot.handle(msg(1,'Чужая заметка',99));self.assertEqual(self.client.get('/api/notes').json['total'],0)
   code=self.post('/api/telegram/link',{}).json['code'];bot.handle(msg(2,'/start '+code))
   bot.handle(msg(3,'Моя новая заметка\nПодробности'));bot.handle(msg(3,'Моя новая заметка\nПодробности'))
   self.assertEqual(self.client.get('/api/notes').json['total'],1)
   bot.handle(msg(4,'📚 Мои заметки'));self.assertIn('inline_keyboard',replies[-1][2])
   bot.handle(msg(5,'/start '+code,99));bot.handle(msg(6,'📚 Мои заметки',99));self.assertNotIn('Моя новая',replies[-1][1])
   self.post('/api/telegram/unlink',{});bot.handle(msg(7,'Не записывать'));self.assertEqual(self.client.get('/api/notes').json['total'],1)
 def test_miniapp_signed_login_and_revocation(self):
  import hmac,time
  from urllib.parse import urlencode
  from unittest.mock import patch
  token='123:test-token-not-real'
  def signed(uid,stamp=None):
   fields={'auth_date':str(int(time.time()) if stamp is None else stamp),'user':json.dumps({'id':uid})}
   secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest();fields['hash']=hmac.new(secret,'\n'.join(k+'='+v for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest();return urlencode(fields)
  mini=app.app.test_client()
  def login(raw):return mini.post('/api/telegram/login',json={'init_data':raw},headers={'Origin':'http://localhost'})
  with patch.dict(os.environ,{'TELEGRAM_BOT_TOKEN':token}):
   self.assertEqual(login(signed(42)).status_code,403)
   with app.database() as db:db.execute('INSERT INTO telegram VALUES(?)',('42',))
   self.assertEqual(login(signed(42)+'&user=forged').status_code,401)
   self.assertEqual(login(signed(42,int(time.time())-3601)).status_code,401)
   self.assertEqual(login(signed(42).replace('hash=','hash=0')).status_code,401)
   self.assertEqual(login(signed(99)).status_code,403)
   self.assertEqual(login(signed(42)).status_code,200);self.assertEqual(mini.get('/api/notes').status_code,200)
   self.post('/api/telegram/unlink',{});self.assertEqual(mini.get('/api/notes').status_code,401)
 def test_limits_and_missing(self):
  n=self.create();self.assertEqual(self.save(n,body='a'*200001).status_code,400)
  self.assertEqual(self.client.get('/api/note/absent').status_code,404)
  self.assertEqual(self.save(n,folder_id=999).status_code,400)
  for path in ['/','/app.js','/style.css','/icon-192.png','/manifest.webmanifest','/notes-desktop_1.0.0_all.deb']:
   r=self.client.get(path);self.assertEqual(r.status_code,200,path);r.close()
if __name__=='__main__':unittest.main()
