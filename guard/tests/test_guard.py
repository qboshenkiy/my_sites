import contextlib
import http.cookiejar
import http.server
import importlib.util
import json
import os
from pathlib import Path
import sqlite3
import struct
import sys
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch,Mock

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'guard/src'))
import app
import docker_api
import monitor
spec=importlib.util.spec_from_file_location('guard_setup',ROOT/'guard/src/setup.py');setup=importlib.util.module_from_spec(spec);spec.loader.exec_module(setup)
spec=importlib.util.spec_from_file_location('milk_guard',ROOT/'milk_duty/src/bot_guard.py');milk=importlib.util.module_from_spec(spec);spec.loader.exec_module(milk)


class MonitorTests(unittest.TestCase):
    def test_ssh_parser_preserves_ip_and_result(self):
        lines=[json.dumps({'__REALTIME_TIMESTAMP':'123000000','MESSAGE':m}) for m in ['Accepted publickey for root from 5.59.101.12 port 3489 ssh2','Failed password for invalid user admin from 2001:db8::1 port 322 ssh2','Invalid user bob from 1.2.3.4 port 300','unrelated secret-looking message']]
        events=monitor.ssh_events('\n'.join(lines));self.assertEqual(len(events),3);self.assertEqual([r['result'] for r in events],['success','failed','failed']);self.assertEqual(events[0]['user'],'root');self.assertEqual(events[1]['ip'],'2001:db8::1')
    def test_http_rate_counts_status_and_removes_query(self):
        rows=[{'logger':'http.log.access.log0','ts':120+i,'status':s,'request':{'remote_ip':'1.2.3.4','host':'pulse.vano.sbena.net','uri':'/api/'+('a'*48)+'?token=SECRET','method':'GET'}} for i,s in enumerate([200,404,502])]
        result=monitor.traffic('\n'.join(json.dumps(r) for r in rows),100)
        self.assertEqual(result['requests'],3);self.assertEqual(result['errors'],2);self.assertEqual(result['ips'][0]['peak_per_minute'],3);self.assertNotIn('SECRET',json.dumps(result));self.assertNotIn('a'*48,json.dumps(result))
    def test_totals_include_addresses_beyond_display_limit(self):
        rows=[{'logger':'http.log.access.x','ts':120,'status':200,'request':{'remote_ip':'192.0.2.'+str(i),'uri':'/','method':'GET'}} for i in range(1,151)]
        result=monitor.traffic('\n'.join(json.dumps(r) for r in rows),100)
        self.assertEqual(len(result['ips']),100);self.assertEqual(result['unique_ips'],150);self.assertEqual(result['requests'],150)
    def test_docker_multiplexed_output(self):
        raw=b'\x01\x00\x00\x00'+struct.pack('>I',3)+b'one'+b'\x02\x00\x00\x00'+struct.pack('>I',3)+b'two'
        self.assertEqual(docker_api.demux(raw),'onetwo')
    def test_no_arbitrary_docker_or_commands(self):
        with self.assertRaises(ValueError):monitor.bot_control('marathon;reboot','restart')
        with self.assertRaises(ValueError):monitor.bot_control('milk','stop')
        with self.assertRaises(ValueError):monitor.bot_action('pulse','exec',{})
    def test_https_routes_idempotent_and_all_hosts_logged(self):
        source='{$DOMAIN} {\n reverse_proxy web:80\n}\n\nhttps://pulse.vano.sbena.net {\n log {\n output stdout\n }\n reverse_proxy pulse:80\n}\n'
        once=setup.route(source,'');twice=setup.route(once,'')
        self.assertEqual(once,twice);self.assertEqual(once.count('# Guard HTTPS BEGIN'),1);self.assertEqual(once.count('log {'),3)
    def test_php_audit_sources_identical(self):
        self.assertEqual((ROOT/'marathon/lib/bot-guard.php').read_bytes(),(ROOT/'assets/bot-guard.php').read_bytes())


class ModerationTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.env=patch.dict(os.environ,{'DATA_DIR':self.tmp.name});self.env.start();self.addCleanup(self.env.stop)
        self.update={'message':{'from':{'id':123,'first_name':'Alice','username':'alice'},'chat':{'id':123,'type':'private'},'text':'/start join_'+'a'*48}}
    def test_participant_redaction_history_and_blocking(self):
        self.assertTrue(milk.incoming(self.update));people=milk.cli('people',{})['people'];self.assertEqual(people[0]['name'],'Alice')
        history=milk.cli('history',{'person':'123'})['events'];self.assertNotIn('a'*48,history[0]['text'])
        milk.cli('block',{'person':'123'});self.assertFalse(milk.incoming(self.update));milk.cli('unblock',{'person':'123'});self.assertTrue(milk.incoming(self.update))
    def test_update_replays_and_incremental_errors(self):
        self.update['update_id']=500
        milk.incoming(self.update);milk.incoming(self.update)
        self.assertEqual(len(milk.cli('history',{'person':'123'})['events']),1)
        cursor=milk.cli('activity',{'after':None})['cursor'];milk.failure(self.update)
        feed=milk.cli('activity',{'after':cursor});self.assertEqual(len(feed['events']),1);self.assertEqual(feed['events'][0]['direction'],'error')
        self.assertEqual(milk.cli('activity',{'after':feed['cursor']})['events'],[])
    def test_unknown_people_cannot_be_messaged(self):
        with self.assertRaises(ValueError):milk.cli('send',{'person':'888','text':'hello'})
    def test_retention_and_no_group_history(self):
        self.update['message']['chat']['type']='group';milk.incoming(self.update)
        self.assertEqual(milk.cli('history',{'person':'123'})['events'],[])
        with milk.database() as db:
            db.execute('INSERT INTO events(person,direction,text,created) VALUES(?,?,?,?)',('123','in','old',1))
            milk.event(db,'123','out','new')
            self.assertEqual(db.execute('SELECT count(*) FROM events').fetchone()[0],1)


class HttpTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp=tempfile.TemporaryDirectory();cls.old=app.DATA;app.DATA=Path(cls.tmp.name)
        app.set_password('guard-test-password-2026')
        cls.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),app.Handler)
        cls.thread=threading.Thread(target=cls.server.serve_forever,daemon=True);cls.thread.start()
        cls.url='http://127.0.0.1:'+str(cls.server.server_port)
    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown();cls.server.server_close();app.DATA=cls.old;cls.tmp.cleanup()
    def setUp(self):
        self.client=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def req(self,path,data=None,host='localhost:8150',origin='http://localhost:8150'):
        headers={'Host':host,'Origin':origin,'Content-Type':'application/json'}
        req=urllib.request.Request(self.url+path,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:
            with self.client.open(req) as response:return response.status,json.load(response)
        except urllib.error.HTTPError as error:
            with error:return error.code,json.load(error)
    def test_auth_host_csrf_and_logout(self):
        self.assertEqual(self.req('/api/bots')[0],401)
        self.assertEqual(self.req('/health',host='evil.test')[0],403)
        self.assertEqual(self.req('/api/login',{'password':'guard-test-password-2026'},origin='http://evil.test')[0],403)
        status,auth=self.req('/api/login',{'password':'guard-test-password-2026'});self.assertEqual(status,200)
        with patch.object(monitor,'bot_control',return_value={'ok':True}) as control:
            self.assertEqual(self.req('/api/bot/action',{'bot':'pulse','action':'stop'})[0],403);control.assert_not_called()
            self.assertEqual(self.req('/api/bot/action',{'bot':'pulse','action':'stop','csrf':auth['csrf']})[0],200)
        self.assertEqual(self.req('/api/logout',{'csrf':auth['csrf']})[0],200);self.assertEqual(self.req('/api/session')[0],401)
    def test_alert_settings_and_test_delivery_require_auth_and_csrf(self):
        self.assertEqual(self.req('/api/alerts')[0],401)
        _,auth=self.req('/api/login',{'password':'guard-test-password-2026'})
        service=Mock();service.save.return_value={'token_set':True};service.listing.return_value={'alerts':[]};service.pair.return_value={'command':'/guard secret','expires':1}
        with patch.object(self.server,'alerts',service,create=True):
            self.assertEqual(self.req('/api/alerts/config',{'telegram_enabled':True})[0],403);service.save.assert_not_called()
            self.assertEqual(self.req('/api/alerts/test',{'csrf':auth['csrf']},origin='https://evil.test')[0],403);service.deliver.assert_not_called()
            self.assertEqual(self.req('/api/alerts/config',{'telegram_enabled':True,'csrf':auth['csrf']})[0],200)
            self.assertEqual(self.req('/api/alerts/pair',{'csrf':auth['csrf']})[0],200)
            self.assertEqual(self.req('/api/alerts/test',{'csrf':auth['csrf']})[0],200);service.deliver.assert_called_once_with(test=True)
    def test_password_reset_revokes_session(self):
        status,_=self.req('/api/login',{'password':'guard-test-password-2026'});self.assertEqual(status,200)
        app.set_password('guard-test-password-2026');self.assertEqual(self.req('/api/session')[0],401)

if __name__=='__main__':unittest.main()
