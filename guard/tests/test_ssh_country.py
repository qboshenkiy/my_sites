import sys,json,unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import ssh_country
class CountryTests(unittest.TestCase):
 def resources(self):return {'ipv4':['31.29.'+str(i)+'.0/24' for i in range(0,100,4)],'ipv6':['2a00:4180::/32']}
 def test_ipv4_ipv6_ports_and_independent_firewall_table(self):
  rules=ssh_country.rules({'resources':self.resources(),'ports':[22,22222]},True)
  for required in ['delete table inet guard_ssh_country','flags interval','ip saddr != @kg4 counter drop','ip6 saddr != @kg6 counter drop','tcp dport { 22, 22222 }','iifname "lo" return']:self.assertIn(required,rules)
  for other in ['flush ruleset','guard_protection','dport 443','dport 80']:self.assertNotIn(other,rules)
 def test_empty_invalid_and_overbroad_feeds_rejected(self):
  for resources in [{},{'ipv4':['0.0.0.0/0'],'ipv6':['::/0']},{'ipv4':['127.0.0.0/8'],'ipv6':['2a00::/16']}]:
   with self.assertRaises(ValueError):ssh_country.networks(resources)
