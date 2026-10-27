import sys
from pathlib import Path
import unittest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from connect_https import route

class ProxyTests(unittest.TestCase):
    def test_own_block_is_idempotent(self):
        source='vano.sbena.net {\n reverse_proxy gitdeck-primary-marathon:80\n}\n'
        updated=route(source,'milk.vano.sbena.net')
        self.assertIn(source.strip(),updated)
        self.assertEqual(route(updated,'milk.vano.sbena.net'),updated)
        self.assertIn('reverse_proxy milk-duty-web:8130',updated)
    def test_occupied_and_ambiguous_routes_are_rejected(self):
        for source in ['milk.vano.sbena.net {\n respond ok\n}', 'vano.sbena.net {\n reverse_proxy web:80\n}']:
            with self.assertRaises(ValueError):route(source,'milk.vano.sbena.net')
