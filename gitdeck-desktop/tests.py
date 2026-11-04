import importlib.util,json,os,tempfile,unittest
from pathlib import Path
import settings
class Preferences(unittest.TestCase):
    def test_all_fields_survive_restart(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';v=dict(settings.DEFAULTS,host='example.test',user='dev',ssh_port=2222,local_port=18120,remote_port=8121,remember=True)
            settings.save(path,v);self.assertEqual(settings.load(path),v)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            self.assertNotIn('password',json.loads(path.read_text()))
    def test_old_preferences_migrate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';path.write_text('{"host":"old.example","user":"dev"}')
            v=settings.load(path);self.assertEqual(v['host'],'old.example');self.assertEqual(v['remote_port'],8120);self.assertEqual(v['ssh_port'],22)
    def test_invalid_changes_preserve_saved_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';settings.save(path,settings.DEFAULTS)
            with self.assertRaises(ValueError):settings.save(path,dict(settings.DEFAULTS,ssh_port='invalid'))
            self.assertEqual(settings.load(path),settings.DEFAULTS)
    def test_known_server_legacy_root_and_closed_port_migrate(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';path.write_text('{"host":"2.28.57.159","user":"root","ssh_port":22,"local_port":8122,"remember":false}')
            value=settings.load(path)
            self.assertEqual((value['user'],value['ssh_port'],value['local_port']),('vano-admin',22222,8122))
            self.assertFalse(value['remember'])
    def test_other_servers_keep_explicit_root_and_port(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';path.write_text('{"host":"example.test","user":"root","ssh_port":22}')
            value=settings.load(path);self.assertEqual((value['user'],value['ssh_port']),('root',22))
if __name__=='__main__':unittest.main()
