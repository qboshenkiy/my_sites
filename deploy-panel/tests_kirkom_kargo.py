import io,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import app
class KirkomKargoTests(unittest.TestCase):
 def test_registration(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);server=types.SimpleNamespace(config={'projects':[],'state_dir':str(root/'state'),'projects_root':temp},config_path=str(root/'config.json'))
   with patch.object(app,'KIRKOM_KARGO',dict(app.KIRKOM_KARGO,directory=str(root/'kirkom_kargo'))):
    app.register_kirkom_kargo(server);app.register_kirkom_kargo(server)
   self.assertEqual([p['id'] for p in server.config['projects']],['kirkom-kargo'])
   self.assertEqual(['web'],server.config['projects'][0]['services'])
   self.assertEqual(app.load_config(server.config_path)['projects'][0]['subdir'],'kirkom_kargo')
 def test_setup_preserves_deployment(self):
  with tempfile.TemporaryDirectory() as temp:
   p=dict(app.KIRKOM_KARGO,directory=str(Path(temp)/'kirkom_kargo'));dest=Path(p['directory']);dest.mkdir();(dest/'.env').write_text('private');(dest/'compose.yaml').write_text('preserve')
   def checkout(project,config,source,log):
    source.mkdir(parents=True)
    for name in project['paths']:
     if name in ('ops','web'):(source/name).mkdir()
     else:(source/name).write_text('new')
    return 'a'*40
   with patch.object(app,'KIRKOM_KARGO',p),patch.object(app,'checkout',side_effect=checkout),patch.object(app,'run') as run,patch.object(app,'status_update'):
    app.setup_kirkom_kargo({'state_dir':temp},p,'test',io.StringIO())
   self.assertEqual((dest/'compose.yaml').read_text(),'preserve');self.assertEqual((dest/'.env').read_text(),'private')
   self.assertEqual(run.call_args.args[0][-1],str(dest/'ops/setup.py'))
 def test_first_install_from_update_uses_provisioning(self):
  with tempfile.TemporaryDirectory() as temp:
   project=dict(app.KIRKOM_KARGO,directory=str(Path(temp)/'new'),_target_ref='a'*40)
   with patch.object(app,'setup_kirkom_kargo') as setup,patch.object(app,'checkout') as checkout:
    app.deploy({'state_dir':temp},project,'job',io.StringIO())
   setup.assert_called_once();checkout.assert_not_called()

if __name__=='__main__':unittest.main()

class CargoProvisioningTests(unittest.TestCase):
 def test_disabled_card_stays_disabled(self):
  server=types.SimpleNamespace(config={'projects':[],'disabled_auto_projects':['kirkom-kargo']})
  app.register_kirkom_kargo(server)
  self.assertEqual(server.config['projects'],[])
 def test_retry_when_https_missing(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);(root/'compose.yaml').write_text('existing')
   with patch.object(app,'setup_kirkom_kargo') as setup:
    app.deploy({},dict(app.KIRKOM_KARGO,directory=temp),'retry',io.StringIO())
   setup.assert_called_once()
