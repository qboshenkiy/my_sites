import io,json,tempfile,types,unittest
from pathlib import Path
from unittest.mock import patch
import app
class KopilkaTests(unittest.TestCase):
 def test_registration(self):
  with tempfile.TemporaryDirectory() as temp:
   root=Path(temp);server=types.SimpleNamespace(config={'projects':[],'state_dir':str(root/'state'),'projects_root':temp},config_path=str(root/'config.json'))
   with patch.object(app,'KOPILKA',dict(app.KOPILKA,directory=str(root/'kopilka'))):
    app.register_kopilka(server);app.register_kopilka(server)
   self.assertEqual([p['id'] for p in server.config['projects']],['kopilka'])
   self.assertIn('bot',server.config['projects'][0]['services'])
   self.assertEqual(app.load_config(server.config_path)['projects'][0]['subdir'],'kopilka')
 def test_setup_preserves_deployment(self):
  with tempfile.TemporaryDirectory() as temp:
   p=dict(app.KOPILKA,directory=str(Path(temp)/'kopilka'));dest=Path(p['directory']);dest.mkdir();(dest/'.env').write_text('private');(dest/'compose.yaml').write_text('preserve')
   def checkout(project,config,source,log):
    source.mkdir(parents=True)
    for name in project['paths']:
     if name in ('src','web'):(source/name).mkdir()
     else:(source/name).write_text('new')
    return 'a'*40
   with patch.object(app,'KOPILKA',p),patch.object(app,'checkout',side_effect=checkout),patch.object(app,'run') as run,patch.object(app,'status_update'):
    app.setup_kopilka({'state_dir':temp},p,'test',io.StringIO())
   self.assertEqual((dest/'compose.yaml').read_text(),'preserve');self.assertEqual((dest/'.env').read_text(),'private')
   self.assertEqual(run.call_args.args[0][-1],str(dest/'src/setup.py'))
if __name__=='__main__':unittest.main()
