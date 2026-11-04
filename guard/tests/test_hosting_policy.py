import sys,tempfile,json,unittest,time
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import hosting_policy as hp
from request_gate import Gate

class HostingTests(unittest.TestCase):
 def setUp(self):
  self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
  self.state=root/'policy.json';self.exc=root/'exceptions.json';self.protected=root/'protected.json'
  self.state.write_text(json.dumps({'enabled':True,'ipv4_prefixes':2,'ipv6_prefixes':1,'resources':{'ipv4':['34.15.128.0/17','149.154.160.0/20'],'ipv6':['2600:1900::/28']}}))
  self.exc.write_text(json.dumps({'allowed_ips':['34.15.162.37']}));self.protected.write_text(json.dumps({'protected_ips':['34.15.162.38']}))
  self.registry=hp.Registry(self.state,self.exc,self.protected)
 def test_ipv4_ipv6_edges_and_trusted_service_exceptions(self):
  for ip in ['34.15.128.0','34.15.255.255','2600:1900::1']:self.assertTrue(self.registry.blocked(ip),ip)
  for ip in ['34.15.127.255','5.59.101.12','34.15.162.37','34.15.162.38','149.154.160.1']:self.assertFalse(self.registry.blocked(ip),ip)
 def test_exception_reload_and_missing_policy(self):
  self.assertTrue(self.registry.blocked('34.15.162.36'))
  self.exc.write_text(json.dumps({'allowed_ips':['34.15.162.36']}));self.registry.checked=-100
  self.assertFalse(self.registry.blocked('34.15.162.36'))
  self.assertFalse(hp.Registry(self.state.parent/'missing',self.exc,self.protected).blocked('34.15.162.36'))
 def test_first_hosting_request_is_denied_and_permanently_banned(self):
  jobs=[];gate=Gate(lambda *args:jobs.append(args),provider=self.registry.blocked)
  self.assertEqual(gate.check('34.15.162.36','/'),(403,0));self.assertEqual(jobs,[('34.15.162.36',0,'cloud_provider')])
  self.assertEqual(gate.check('5.59.101.12','/'),(204,0))
 def test_own_admin_hosting_ip_is_protected(self):
  jobs=[];gate=Gate(lambda *args:jobs.append(args),provider=lambda ip:True,protected=lambda:{'5.59.101.12'})
  self.assertEqual(gate.check('5.59.101.12','/'),(204,0));self.assertFalse(jobs)
 def test_rules_keep_outbound_replies_acme_and_http_gate_access(self):
  with patch.object(hp,'allowed_ips',return_value=['5.59.101.12']):rules=hp.rules(json.loads(self.state.read_text()),True)
  for value in ['hook input priority -180','hook forward priority -180','ct direction reply return','ct state related return','tcp dport { 80, 443 } return','ip saddr @hosting4 counter drop','ip6 saddr @hosting6 counter drop','5.59.101.12/32','149.154.160.0/20']:self.assertIn(value,rules)
  self.assertNotIn('flush ruleset',rules);self.assertNotIn('hook output',rules)
 def test_invalid_or_overbroad_feeds_rejected(self):
  for values,version in [([],4),(['0.0.0.0/0'],4),(['::/0'],6),(['127.0.0.1/32'],4),(['2600:1900::/28'],4)]:
   with self.assertRaises(ValueError):hp.validate(values,version)
 def test_public_metadata_hides_full_dataset_and_inspects_address(self):
  data=self.registry.public('34.15.162.36')
  self.assertNotIn('resources',data);self.assertTrue(data['inspected']['listed']);self.assertTrue(data['inspected']['denied'])

 def test_manual_unblock_persists_exception_and_rolls_back_on_failure(self):
  with patch.object(hp,'EXCEPTIONS',self.exc),patch.object(hp,'STATE',self.state),patch.object(hp.Registry,'contains',return_value=True),patch.object(hp,'apply') as apply:
   hp.allow_ip('34.15.162.36');self.assertIn('34.15.162.36',json.loads(self.exc.read_text())['allowed_ips']);apply.assert_called_once()
   apply.side_effect=ValueError('kernel failure')
   with self.assertRaises(ValueError):hp.allow_ip('34.15.162.39')
   self.assertNotIn('34.15.162.39',json.loads(self.exc.read_text())['allowed_ips'])

 def test_normalized_adjacent_ranges_remain_valid_on_restore(self):
  for values,version in [(['34.0.0.0/8','35.0.0.0/8'],4),(['2600::/16','2601::/16'],6)]:
   normalized=hp.validate(values,version)
   self.assertEqual(hp.validate(normalized,version),normalized)
