import json
from pathlib import Path
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import app
import alerts
import monitor

TOKEN='999999:ABCDEFGHIJKLMNOPQRSTUVWXYZ_12345'


class Transport:
    def __init__(self):self.sent=[];self.updates=[];self.member='creator';self.fail=False
    def __call__(self,token,method,args=None):
        if method=='getMe':return {'id':999999,'is_bot':True,'username':'guard_test_bot'}
        if method=='getWebhookInfo':return {'url':''}
        if method=='getUpdates':
            result=self.updates;self.updates=[];return result
        if method=='getChatMember':return {'status':self.member}
        if method=='sendMessage':
            if self.fail:raise alerts.TelegramError(429,90)
            self.sent.append(dict(args));return {'message_id':len(self.sent)}
        raise AssertionError(method)


class AlertsTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.old=app.DATA;app.DATA=Path(self.tmp.name);self.addCleanup(setattr,app,'DATA',self.old)
        self.fake=Transport();self.service=alerts.Service(app.database,self.fake)
        self.ids=patch.object(monitor,'installed_bot_ids',return_value=set());self.ids.start();self.addCleanup(self.ids.stop)
        self.now=time.time()
    def configure(self):self.service.save({'bot_token':TOKEN,'telegram_enabled':True})
    def bind(self,member='creator'):
        self.fake.member=member;command=self.service.pair()['command']
        self.fake.updates=[{'update_id':1,'message':{'from':{'id':123},'chat':{'id':-100123,'type':'supergroup','title':'Защита'},'text':command}}]
        self.service.poll();return command
    def request(self,i,status=200,peer='1.2.3.4',stamp=None):
        stamp=self.now if stamp is None else stamp
        return json.dumps({'logger':'http.log.access.log0','ts':stamp+i/10000,'status':status,'request':{'remote_ip':peer,'host':'pulse.vano.sbena.net','uri':'/api/test?token=PRIVATE','method':'POST'}})
    def samples(self,n=10,status=200,start=0):return alerts.http_samples('\n'.join(self.request(i,status) for i in range(start,start+n)),self.now-1)
    def test_rolling_spam_dedup_and_restart(self):
        self.service.save({'http_limit':10});samples=self.samples()
        self.service.ingest(samples,self.now+1);self.service.ingest(samples,self.now+2)
        listing=self.service.listing();self.assertEqual(len(listing['alerts']),1);self.assertEqual(listing['alerts'][0]['count'],10)
        self.service.acknowledge(0);self.assertEqual(self.service.listing()['unread'],0)
        restarted=alerts.Service(app.database,self.fake);restarted.ingest(self.samples(1,start=20),self.now+3)
        self.assertEqual(restarted.listing()['alerts'][0]['count'],11);self.assertEqual(restarted.listing()['unread'],1)
    def test_5xx_alerts_without_query_or_duplicate_spam_count(self):
        self.service.save({'http_limit':10})
        self.service.ingest(self.samples(5,status=502),self.now+1)
        self.service.ingest(self.samples(3,status=404,start=30),self.now+2)
        result=self.service.listing()['alerts'];self.assertEqual(len(result),1);self.assertEqual(result[0]['count'],5);self.assertEqual(result[0]['kind'],'error')
        self.assertNotIn('PRIVATE',json.dumps(result));self.assertIn('502',result[0]['body'])
    def test_bot_errors_do_not_count_as_extra_messages(self):
        self.service.save({'bot_limit':5})
        feed=[{'id':i,'person':'123','name':'Иван','direction':'in','created':self.now,'text':'private'} for i in range(1,5)]
        feed += [{'id':i,'person':'123','name':'Иван','direction':'error','created':self.now,'text':'Ошибка обработки сообщения.'} for i in range(10,14)]
        samples=alerts.bot_samples('marathon',feed);self.service.ingest(samples,self.now+1)
        result=self.service.listing()['alerts'];self.assertEqual(len(result),1);self.assertEqual(result[0]['kind'],'error');self.assertEqual(result[0]['count'],4)
        self.assertNotIn('private',json.dumps(result))
        extra={'id':20,'person':'123','direction':'in','created':self.now+2}
        self.service.ingest(alerts.bot_samples('marathon',[extra]),self.now+3)
        self.assertEqual(len(self.service.listing()['alerts']),2)
    def test_bot_token_is_write_only_and_existing_app_bot_rejected(self):
        with patch.object(monitor,'installed_bot_ids',return_value={'999999'}):
            with self.assertRaises(ValueError):self.configure()
        self.configure();self.assertTrue(self.service.public()['token_set']);self.assertNotIn(TOKEN,json.dumps(self.service.public()))
    def test_group_pair_requires_valid_code_and_group_admin(self):
        self.configure();command=self.bind(member='member');self.assertFalse(self.service.public()['group_id']);self.assertEqual(len(self.fake.sent),0)
        self.fake.member='creator'
        self.fake.updates=[{'update_id':2,'message':{'from':{'id':123},'chat':{'id':-100123,'type':'supergroup','title':'Защита'},'text':command}}]
        self.service.poll();self.assertEqual(self.service.public()['group_id'],'-100123');self.assertEqual(len(self.fake.sent),1)
        # A consumed command cannot replace the group.
        self.fake.updates=[{'update_id':3,'message':{'from':{'id':123},'chat':{'id':-100999,'type':'supergroup'},'text':command}}]
        self.service.poll();self.assertEqual(self.service.public()['group_id'],'-100123')
    def test_pair_expiry_and_wrong_bot_mention(self):
        self.configure();command=self.service.pair()['command']
        self.fake.updates=[{'update_id':1,'message':{'from':{'id':123},'chat':{'id':-1001,'type':'group'},'text':command.replace('@guard_test_bot','@another_bot')}}]
        self.service.poll();self.assertFalse(self.service.public()['group_id'])
        with app.database() as db:db.execute('UPDATE notification_pair SET expires=0')
        self.fake.updates=[{'update_id':2,'message':{'from':{'id':123},'chat':{'id':-1001,'type':'group'},'text':command}}]
        self.service.poll();self.assertFalse(self.service.public()['group_id'])
    def test_cooldown_delivery_and_rate_limit_retry(self):
        self.configure();self.bind();self.fake.sent=[]
        self.service.ingest(self.samples(1,500),self.now+1)
        self.fake.fail=True
        with self.assertRaises(alerts.TelegramError):self.service.deliver()
        self.assertEqual(self.service.public()['pending'],1);self.assertNotIn(TOKEN,self.service.public()['delivery_error'])
        self.fake.fail=False;self.service.deliver();self.assertEqual(self.fake.sent,[])
        with patch.object(alerts.time,'time',return_value=self.now+100):self.service.deliver()
        self.assertEqual(len(self.fake.sent),1);self.assertEqual(self.service.public()['pending'],0)
        self.service.ingest(self.samples(1,500,start=2),self.now+150);self.assertEqual(self.service.public()['pending'],0)
        self.service.ingest(self.samples(1,500,start=3),self.now+700);self.assertEqual(self.service.public()['pending'],1)
    def test_new_group_and_token_do_not_receive_old_backlog(self):
        self.service.ingest(self.samples(1,500),self.now)
        self.configure();self.bind();self.assertEqual(self.service.public()['pending'],0)
        self.service.ingest(self.samples(1,503,start=5),self.now+1);self.assertEqual(self.service.public()['pending'],1)
        self.service.save({'telegram_enabled':False});self.assertEqual(self.service.public()['pending'],0)
    def test_feed_baselines_and_cursors_persist(self):
        def feed(bot,action,data):
            return {'events':[],'cursor':50} if data['after'] is None else {'events':[{'id':51,'person':'123','direction':'error','created':self.now,'text':'Ошибка'}],'cursor':51}
        with patch.object(monitor.docker_api,'logs',return_value=''),patch.object(monitor,'bot_action',side_effect=feed):
            self.service.collect();self.assertEqual(len(self.service.listing()['alerts']),0)
            restarted=alerts.Service(app.database,self.fake);restarted.collect();self.assertEqual(len(restarted.listing()['alerts']),3)
            restarted.collect();self.assertEqual([r['count'] for r in restarted.listing()['alerts']],[1,1,1])

if __name__=='__main__':unittest.main()
