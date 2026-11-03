import hashlib,json,os,sys,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
TEMP=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=TEMP.name;os.environ['COOKIE_SECURE']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import app,bot
class FinanceTests(unittest.TestCase):
 def setUp(self):
  with app.database() as db:
   for t in ['transactions','goals','contributions','settings','attempts','links','telegram','bot_updates']:db.execute('DELETE FROM '+t)
  salt='ab'*16;Path(TEMP.name,'password.json').write_text(json.dumps({'salt':salt,'digest':hashlib.scrypt(b'finance-test-password',salt=bytes.fromhex(salt),n=16384,r=8,p=1).hex()}))
  self.client=app.app.test_client();self.csrf=self.post('/api/login',{'password':'finance-test-password'}).json['csrf']
 def post(self,url,data):return self.client.post(url,json={'csrf':getattr(self,'csrf',''),**data},headers={'Origin':'http://localhost'})
 def state(self):return self.client.get('/api/state').json
 def test_auth_and_csrf(self):
  other=app.app.test_client();self.assertEqual(other.get('/api/state').status_code,401)
  self.assertEqual(self.client.post('/api/transaction',json={'csrf':self.csrf}).status_code,403)
  self.assertEqual(self.post('/api/transaction',{'csrf':'wrong'}).status_code,403)
  for _ in range(5):self.post('/api/login',{'password':'wrong'})
  self.assertEqual(self.post('/api/login',{'password':'finance-test-password'}).status_code,429)
 def test_accounting_validation_export(self):
  self.assertEqual(self.post('/api/transaction',dict(kind='income',amount='100.10',category='Доход')).status_code,200)
  self.post('/api/transaction',dict(kind='expense',amount='20.05',category='Продукты',note='<script>'))
  self.assertEqual(self.state()['balance'],8005);self.assertEqual(self.state()['expense'],2005)
  for value in ['-1','NaN','Infinity','0.001','1000000001']:
   self.assertEqual(self.post('/api/transaction',dict(amount=value)).status_code,400)
  self.assertEqual(self.state()['balance'],8005)
  self.assertEqual(self.post('/api/settings',dict(currency='USD',budget='100')).status_code,400)
  data=self.client.get('/api/export').json;self.assertNotIn('telegram',data);self.assertEqual(len(data['transactions']),2)
  self.post('/api/delete',dict(type='transaction',id=self.state()['transactions'][0]['id']));self.assertEqual(self.state()['balance'],10010)
 def test_goals(self):
  self.post('/api/goal',dict(name='Отпуск',target='1200',deadline=str(date.today()+timedelta(days=100))))
  goal=self.state()['goals'][0];self.assertGreater(goal['monthly'],0)
  self.assertEqual(self.post('/api/contribute',dict(id=goal['id'],amount='200')).status_code,200)
  self.assertEqual(self.state()['goals'][0]['saved'],20000);self.assertEqual(self.state()['balance'],0)
  self.assertEqual(self.post('/api/contribute',dict(id=goal['id'],amount='1100')).status_code,400)
  self.assertEqual(self.state()['goals'][0]['saved'],20000)
 def test_bot_pairing_and_deduplication(self):
  replies=[];bot.respond=lambda chat,text:replies.append(text)
  def msg(uid,text,chat=42,kind='private'):bot.handle({'update_id':uid,'message':{'chat':{'id':chat,'type':kind},'text':text}})
  msg(1,'/balance');self.assertIn('Подключите',replies[-1])
  code=self.post('/api/telegram/link',{}).json['code'];msg(2,'/start '+code)
  msg(3,'/expense 10.25 Хлеб');msg(3,'/expense 10.25 Хлеб');self.assertEqual(self.state()['expense'],1025)
  msg(4,'/start '+code,43);self.assertIn('недействителен',replies[-1])
  msg(5,'/balance',43);self.assertIn('Подключите',replies[-1])
  self.post('/api/telegram/unlink',{});msg(6,'/expense 50 Тест');self.assertEqual(self.state()['expense'],1025)
  msg(7,'/expense 50 Тест',42,'group');self.assertEqual(self.state()['expense'],1025)
 def test_assets_and_private_cache(self):
  for url in ['/','/app.js','/style.css','/manifest.webmanifest','/icon-192.png','/sw.js']:
   r=self.client.get(url);self.assertEqual(r.status_code,200,url);r.close()
  self.assertEqual(self.client.get('/api/state').headers['Cache-Control'],'no-store')
if __name__=='__main__':unittest.main()
