import sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import unittest
from unittest.mock import patch
import request_gate
import monitor
import json

class GateTests(unittest.TestCase):
 def setUp(self):
  self.now=100.;self.bans=[];self.g=request_gate.Gate(lambda ip,duration,reason:self.bans.append((ip,duration,reason)),clock=lambda:self.now)
 def test_31st_request_bans_for_exactly_five_minutes(self):
  for _ in range(30):self.assertEqual(self.g.check('8.8.8.8'),(204,0))
  self.assertEqual(self.g.check('8.8.8.8'),(429,300));self.assertEqual(self.bans,[('8.8.8.8',300,'rate_limit')])
  self.now+=299;self.assertEqual(self.g.check('8.8.8.8'),(429,1))
  self.now+=1;self.assertEqual(self.g.check('8.8.8.8'),(204,0));self.assertEqual(len(self.bans),1)
 def test_sliding_window_and_independent_ips(self):
  for _ in range(30):self.g.check('8.8.8.8')
  self.assertEqual(self.g.check('1.1.1.1'),(204,0))
  self.now+=10;self.assertEqual(self.g.check('8.8.8.8'),(204,0));self.assertFalse(self.bans)
 def test_admin_rate_limited_without_firewall_lockout(self):
  self.g.protected=lambda:{'8.8.8.8'}
  for _ in range(30):self.g.check('8.8.8.8')
  self.assertEqual(self.g.check('8.8.8.8')[0],429);self.assertFalse(self.bans)
 def test_first_secret_probe_permanently_banned_and_unblock_works(self):
  self.assertEqual(self.g.check('8.8.8.8','/.env'),(403,0))
  self.assertEqual(self.bans,[('8.8.8.8',0,'secret_probe')])
  self.g.clear_block('8.8.8.8')
  self.assertEqual(self.g.check('8.8.8.8','/'),(204,0))
  for _ in range(100):self.assertEqual(self.g.check('127.0.0.1'),(204,0))
 def test_high_confidence_paths_encoding_and_ordinary_requests(self):
  for path in ['/a/.git/config','/%252eenv','/.config/gcloud/application_default_credentials.json','/.docker/config.json','/a/../../etc/passwd','/vendor/phpunit/phpunit/src/Util/PHP/eval-stdin.php','/wp-login.php']:
   self.assertIsNotNone(request_gate.classify(path),path)
  for path in ['/api/results','/missing-page','/books/.environment','/?search=/.env','/api/export?name=.env','/app.js']:
   self.assertIsNone(request_gate.classify(path),path)
 def test_protected_admin_secret_request_denied_without_ban(self):
  self.g.protected=lambda:{'8.8.8.8'}
  self.assertEqual(self.g.check('8.8.8.8','/.git/config'),(403,0));self.assertFalse(self.bans)
 def test_bounded_memory_and_ipv6(self):
  with patch.object(request_gate,'MAX_IPS',2):
   for ip in ('1.1.1.1','8.8.8.8','2001:4860:4860::8888'):self.g.check(ip)
   self.assertEqual(len(self.g.clients),2)
 def test_ssh_log_success_failure_ipv6_and_malformed_timestamp(self):
  def row(m,t='1000000'):return json.dumps({'MESSAGE':m,'__REALTIME_TIMESTAMP':t})
  events=monitor.ssh_events('\n'.join([row('Accepted publickey for root from 1.1.1.1 port 2222 ssh2'),row('Failed password for invalid user admin from 2001:4860:4860::8888 port 4567 ssh2'),row('Accepted password for root from 1.1.1.1 port 123 ssh2','bad')]))
  self.assertEqual(len(events),2);self.assertEqual(events[0]['result'],'success');self.assertEqual(events[0]['port'],2222);self.assertEqual(events[1]['user'],'admin');self.assertEqual(events[1]['result'],'failed')

 def test_auth_subrequest_keeps_query_without_breaking_site(self):
  import tempfile,socket,threading
  with tempfile.TemporaryDirectory() as folder:
   path=folder+'/gate.sock'
   with request_gate.Server(path,request_gate.Handler) as server:
    server.gate=self.g
    thread=threading.Thread(target=server.handle_request);thread.start()
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
     client.settimeout(2);client.connect(path)
     client.sendall(b'GET /check?key=private HTTP/1.1\r\nHost: guard\r\nX-Guard-IP: 8.8.8.8\r\nConnection: close\r\n\r\n')
     self.assertIn(b' 204 ',client.recv(4096))
    thread.join(timeout=2)
