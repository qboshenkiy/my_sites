import hashlib,json,os,sys,tempfile,unittest
from datetime import date,timedelta
from pathlib import Path
TEMP=tempfile.TemporaryDirectory();os.environ['DATA_DIR']=TEMP.name;os.environ['COOKIE_SECURE']='0'
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import app,bot
class FinanceTests(unittest.TestCase):
 def setUp(self):
  with app.database() as db:
   for t in ['transactions','transfers','goals','contributions','settings','attempts','links','telegram','bot_updates']:db.execute('DELETE FROM '+t)
   db.execute('DELETE FROM wallets WHERE id!=1');db.execute("UPDATE wallets SET opening=0,name='Основной' WHERE id=1")
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
  self.post('/api/wallet',dict(name='Тестовая карта'));wid=self.state()['wallets'][1]['id']
  msg(30,f'/income 50 @{wid} Подработка');self.assertEqual(self.state()['wallets'][1]['balance'],5000)
  msg(31,'/wallets');self.assertIn('Тестовая карта',replies[-1])
  msg(4,'/start '+code,43);self.assertIn('недействителен',replies[-1])
  msg(5,'/balance',43);self.assertIn('Подключите',replies[-1])
  self.post('/api/telegram/unlink',{});msg(6,'/expense 50 Тест');self.assertEqual(self.state()['expense'],1025)
  msg(7,'/expense 50 Тест',42,'group');self.assertEqual(self.state()['expense'],1025)
 def test_wallet_transfers_and_history(self):
  self.post('/api/wallet',dict(name='Наличные',opening='500'))
  cash=self.state()['wallets'][1]['id']
  self.assertEqual(self.state()['balance'],50000);self.assertEqual(self.state()['income'],0)
  self.post('/api/transaction',dict(kind='income',amount='1000',category='Доход'))
  self.post('/api/transaction',dict(kind='expense',amount='20',category='Продукты',wallet_id=cash))
  before=self.state()
  self.assertEqual(self.post('/api/transfer',dict(from_wallet=1,to_wallet=cash,amount='300')).status_code,200)
  after=self.state();self.assertEqual((after['balance'],after['income'],after['expense']),(before['balance'],before['income'],before['expense']))
  self.assertEqual([w['balance'] for w in after['wallets']],[70000,78000])
  self.assertEqual(after['transfers'][0]['from_name'],'Основной')
  self.assertEqual(self.post('/api/transfer',dict(from_wallet=1,to_wallet=cash,amount='701')).status_code,400)
  self.assertEqual(self.post('/api/transfer',dict(from_wallet=1,to_wallet=1,amount='1')).status_code,400)
  self.assertEqual(self.post('/api/transaction',dict(amount='1',wallet_id=999)).status_code,400)
  self.assertEqual(len(self.state()['transfers']),1)
  self.post('/api/delete',dict(type='transfer',id=after['transfers'][0]['id']))
  self.assertEqual([w['balance'] for w in self.state()['wallets']],[100000,48000])
  exported=self.client.get('/api/export').json;self.assertEqual(exported['version'],2);self.assertEqual(len(exported['wallets']),2)
 def test_wallet_edit_delete_and_currency(self):
  self.assertEqual(self.post('/api/wallet/delete',dict(id=1)).status_code,400)
  self.post('/api/wallet',dict(name='Карта',opening='0'));wid=self.state()['wallets'][1]['id']
  self.post('/api/wallet',dict(id=wid,name='Зарплатная',opening='50'))
  self.assertEqual(self.state()['wallets'][1]['name'],'Зарплатная');self.assertEqual(self.state()['balance'],5000)
  self.assertEqual(self.post('/api/settings',dict(currency='USD')).status_code,400)
  self.assertEqual(self.post('/api/wallet/delete',dict(id=wid)).status_code,400)
  self.post('/api/wallet',dict(id=wid,name='Зарплатная',opening='0'))
  self.assertEqual(self.post('/api/wallet/delete',dict(id=wid)).status_code,200)
 def test_wallet_migration_preserves_legacy_records(self):
  import sqlite3
  from unittest.mock import patch
  with tempfile.TemporaryDirectory() as folder:
   with sqlite3.connect(Path(folder)/'finance.sqlite') as db:
    db.execute('CREATE TABLE transactions(id INTEGER PRIMARY KEY,kind TEXT,amount INTEGER,category TEXT,day TEXT,note TEXT,source TEXT,external TEXT UNIQUE)')
    db.execute("INSERT INTO transactions VALUES(1,'income',12345,'Доход',?,'старый доход','web',NULL)",(date.today().isoformat(),))
    db.execute("INSERT INTO transactions VALUES(2,'expense',2345,'Другое',?,'старый расход','telegram','42')",(date.today().isoformat(),))
   with patch.object(app,'DATA',Path(folder)):
    for _ in range(2):
     with app.database() as db:
      result=app.overview(db,date.today().strftime('%Y-%m'))
      self.assertEqual(result['balance'],10000);self.assertEqual(len(result['wallets']),1)
      self.assertTrue(all(t['wallet_id']==1 for t in result['transactions']))
      self.assertEqual(db.execute('SELECT external FROM transactions WHERE id=2').fetchone()[0],'42')
 def test_concurrent_transfers_cannot_overdraw(self):
  from concurrent.futures import ThreadPoolExecutor
  self.post('/api/wallet',dict(id=1,name='Основной',opening='100'))
  self.post('/api/wallet',dict(name='Карта'));wid=self.state()['wallets'][1]['id']
  def send():
   try:
    with app.database() as db:
     db.execute('BEGIN IMMEDIATE');app.transfer(db,dict(from_wallet=1,to_wallet=wid,amount='80'))
    return True
   except ValueError:return False
  with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(lambda _:send(),range(2)))
  self.assertEqual(sum(results),1);self.assertEqual([w['balance'] for w in self.state()['wallets']],[2000,8000])
 def test_assets_and_private_cache(self):
  for url in ['/','/app.js','/style.css','/manifest.webmanifest','/icon-192.png','/sw.js']:
   r=self.client.get(url);self.assertEqual(r.status_code,200,url);r.close()
  self.assertEqual(self.client.get('/api/state').headers['Cache-Control'],'no-store')
if __name__=='__main__':unittest.main()
