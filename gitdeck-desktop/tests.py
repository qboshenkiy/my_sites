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
            v=settings.load(path);self.assertEqual(v['host'],'old.example');self.assertEqual(v['remote_port'],8120)
    def test_invalid_changes_preserve_saved_settings(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/'settings.json';settings.save(path,settings.DEFAULTS)
            with self.assertRaises(ValueError):settings.save(path,dict(settings.DEFAULTS,ssh_port='invalid'))
            self.assertEqual(settings.load(path),settings.DEFAULTS)
if __name__=='__main__':unittest.main()
