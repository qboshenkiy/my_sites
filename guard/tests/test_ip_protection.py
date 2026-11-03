import copy
import json
from pathlib import Path
import re
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
import app
import firewall_agent as fw
import ip_activity
import ip_geo
import proxy_protection


class FakeNft:
    def __init__(self):self.exists=False;self.ips=set();self.fail=False;self.scripts=[]
    def __call__(self,args,script=None):
        if args[0]=='-j':
            if not self.exists:raise ValueError('not found')
            return json.dumps({'nftables':[{'set':{'name':'deny4','elem':[{'elem':{'val':ip}} for ip in self.ips if ':' not in ip]}},{'set':{'name':'deny6','elem':[{'elem':{'val':ip}} for ip in self.ips if ':' in ip]}}]})
        self.scripts.append(script)
        if self.fail:self.fail=False;raise ValueError('nft failed')
        self.exists=True;self.ips=set(re.findall(r'([0-9a-fA-F:.]+) timeout [0-9]+s',script));return ''


class FirewallTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);root=Path(self.tmp.name)
        (root/'config.json').write_text(json.dumps({'protected_ips':['8.8.4.4']}));self.nft=FakeNft();self.c=fw.Controller(root/'state.json',root/'config.json',self.nft)
    def test_full_scope_ipv4_ipv6_and_reboot_restore(self):
        self.c.change('block','1.1.1.1','9.9.9.9',3600);self.c.change('block','2001:4860:4860::8888','9.9.9.9',900)
        rules=fw.rules(self.c.active(),time.time())
        for text in ['hook input priority -200','hook forward priority -200','ip saddr @deny4 counter drop','ip6 saddr @deny6 counter drop']:self.assertIn(text,rules)
        self.assertNotIn('dport',rules)
        restored=fw.Controller(self.c.state,self.c.config,self.nft);self.assertEqual(len(restored.status()['blocked']),2)
        self.c.change('unblock','1.1.1.1','9.9.9.9');self.assertNotIn('1.1.1.1',self.nft.ips)
    def test_own_server_admin_private_and_invalid_ip_protected(self):
        for ip in ['9.9.9.9','8.8.4.4','127.0.0.1','172.18.0.1','0.0.0.0','::1','1.1.1.1/24','1.1.1.1; reboot']:
            with self.assertRaises(ValueError):self.c.change('block',ip,'9.9.9.9',3600)
        self.assertEqual(self.nft.ips,set())
        for duration in [True,3600.0,'3600',1,999999]:
            with self.assertRaises(ValueError):self.c.change('block','1.1.1.1','9.9.9.9',duration)
    def test_failed_kernel_change_preserves_state(self):
        self.c.change('block','1.1.1.1','9.9.9.9',3600);before=self.c.state.read_text();self.nft.fail=True
        with self.assertRaises(ValueError):self.c.change('block','8.8.8.8','9.9.9.9',3600)
        self.assertEqual(self.c.state.read_text(),before);self.assertEqual(self.nft.ips,{'1.1.1.1'})
    def test_expiry_and_mapped_ipv4(self):
        self.c.change('block','::ffff:1.1.1.1','9.9.9.9',900)
        expiry=self.c.entries['1.1.1.1']['expires']
        with patch.object(fw.time,'time',return_value=expiry+1):self.assertEqual(self.c.status()['blocked'],[])
    def test_proxy_imports_preserve_routes_idempotently(self):
        source='{$DOMAIN} {\n reverse_proxy marathon:80\n}\nfinance.example.com {\n reverse_proxy finance:8160\n}\n'
        updated,count=proxy_protection.install_imports(source)
        self.assertEqual(count,2);self.assertIn('reverse_proxy finance:8160',updated);self.assertEqual(updated.count('/data/guard-sensitive.caddy'),2)
        self.assertEqual(proxy_protection.install_imports(updated)[0],updated)


class EvidenceTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup);self.old=app.DATA;app.DATA=Path(self.tmp.name);self.addCleanup(setattr,app,'DATA',self.old)
    def raw(self,path='/.env',status=404,stamp=None):
        return json.dumps({'logger':'http.log.access.log0','ts':stamp or time.time(),'status':status,'size':12,'duration':.01,'request':{'remote_ip':'34.15.162.36','host':'connect.vano.sbena.net','uri':path,'method':'GET','proto':'HTTP/2.0','headers':{'User-Agent':['curl/8.0'],'Cookie':['SECRET_COOKIE'],'Authorization':['SECRET_AUTH']},'body':'SECRET_BODY'}})
    def test_full_paths_metadata_and_secret_redaction(self):
        raw=self.raw('/var/www/private/.env?token=SECRET_TOKEN&action=get_results');entries=list(ip_activity.events(raw))
        self.assertEqual(entries[0]['path'],'/var/www/private/.env');self.assertTrue(entries[0]['probe']);self.assertEqual(entries[0]['action'],'get_results')
        self.assertNotIn('SECRET',json.dumps(entries));self.assertEqual(entries[0]['duration_ms'],10)
    def test_277_requests_full_totals_timeline_and_replay_dedup(self):
        now=time.time();raw='\n'.join(self.raw('/.git/config',stamp=now+i/10) for i in range(277));ip_activity.record_raw(app.database,raw);ip_activity.record_raw(app.database,raw)
        report=ip_activity.report(app.database,'34.15.162.36',86400)
        self.assertEqual(report['total'],277);self.assertEqual(report['peak_per_minute'],277);self.assertEqual(report['statuses'],{'404':277});self.assertEqual(len(report['events']),277)
        self.assertTrue(any('404' in text for text in report['findings']))
    def test_many_query_fields_do_not_drop_evidence(self):
        entries=list(ip_activity.events(self.raw('/.env?'+'&'.join('key'+str(i)+'=secret' for i in range(110)))))
        self.assertEqual(len(entries),1);self.assertTrue(entries[0]['query_truncated'])
    def test_sensitive_200_is_flagged_without_claiming_compromise(self):
        ip_activity.record_raw(app.database,self.raw('/.env',200));report=ip_activity.report(app.database,'34.15.162.36')
        self.assertTrue(any('сам код ещё не доказывает' in text for text in report['findings']))
    def test_geo_cached_and_cloud_region_fallback(self):
        def fetch(url):
            if 'ipinfo' in url:raise OSError('offline')
            return {'prefixes':[{'ipv4Prefix':'34.15.128.0/17','scope':'asia-southeast3','service':'Google Cloud'}]}
        with patch.object(ip_geo,'fetch',side_effect=fetch) as remote:
            result=ip_geo.lookup(app.database,'34.15.162.36');count=remote.call_count
            self.assertEqual(result['city'],'Bangkok');self.assertTrue(result['available']);self.assertIn('не местонахождение человека',result['note'])
            self.assertEqual(ip_geo.lookup(app.database,'34.15.162.36'),result);self.assertEqual(remote.call_count,count)
        with patch.object(ip_geo,'fetch') as remote:
            self.assertFalse(ip_geo.lookup(app.database,'127.0.0.1')['available']);remote.assert_not_called()

if __name__=='__main__':unittest.main()
