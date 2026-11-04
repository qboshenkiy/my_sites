import hashlib,json,os,sys,tempfile,unittest
from pathlib import Path
TEMP=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=TEMP.name;os.environ['COOKIE_SECURE']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import app
class NotesTests(unittest.TestCase):
 def setUp(self):
  with app.database() as db:
   for t in ['notes','folders','versions','attempts']:db.execute('DELETE FROM '+t)
  salt='ef'*16;Path(TEMP.name,'password.json').write_text(json.dumps({'salt':salt,'digest':hashlib.scrypt(b'notes-test-password',salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()}))
  self.client=app.app.test_client();self.csrf=self.post('/api/login',{'password':'notes-test-password'}).json['csrf']
 def post(self,url,data):return self.client.post(url,json={'csrf':getattr(self,'csrf',''),**data},headers={'Origin':'http://localhost'})
 def create(self,folder=None):return self.post('/api/note/create',{'folder_id':folder}).json
 def save(self,n,**patch):return self.post('/api/note/save',{**n,**patch})
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
 def test_limits_and_missing(self):
  n=self.create();self.assertEqual(self.save(n,body='a'*200001).status_code,400)
  self.assertEqual(self.client.get('/api/note/absent').status_code,404)
  self.assertEqual(self.save(n,folder_id=999).status_code,400)
  for path in ['/','/app.js','/style.css','/icon-192.png','/manifest.webmanifest','/notes-desktop_1.0.0_all.deb']:
   r=self.client.get(path);self.assertEqual(r.status_code,200,path);r.close()
if __name__=='__main__':unittest.main()
