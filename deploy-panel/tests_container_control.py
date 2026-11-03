import io,json,tempfile,unittest
from pathlib import Path
from unittest.mock import patch
import app
CID='a'*64
class ContainerControl(unittest.TestCase):
 def test_inspection_is_identity_bound_and_rejects_shell_or_delete(self):
  with patch.object(app,'monitor_command',return_value=(CID+'\n/bot-1\nrunning\n',False)) as read:
   self.assertEqual(app.inspect_container(CID[:12],'stop','bot-1')['id'],CID)
   with self.assertRaises(ValueError):app.inspect_container(CID,'stop','different-container')
   read.assert_called_with(['docker','inspect','--type','container','--format','{{.Id}}\n{{.Name}}\n{{.State.Status}}',CID],timeout=8)
  with patch.object(app,'monitor_command') as read:
   for identifier,command in [(CID,'rm'),('bot;reboot','stop'),('--all','restart')]:
    with self.assertRaises(ValueError):app.inspect_container(identifier,command)
   read.assert_not_called()
 def test_stop_targets_only_confirmed_id_and_checks_result(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'jobs'/'job';path.mkdir(parents=True)
   (path/'environment.json').write_text(json.dumps({'container':CID,'name':'bot-1','command':'stop'}))
   info={'id':CID,'name':'bot-1','state':'running'}
   with patch.object(app,'inspect_container',side_effect=[info,dict(info,state='exited')]),patch.object(app,'run') as run,patch.object(app,'status_update') as status:
    app.control_container({'state_dir':folder},'job',io.StringIO())
    run.assert_called_once_with(['docker','stop',CID],unittest.mock.ANY,timeout=90)
    self.assertEqual(status.call_args.args[2],'success')
 def test_crashing_container_is_not_reported_as_started(self):
  with tempfile.TemporaryDirectory() as folder:
   path=Path(folder)/'jobs'/'job';path.mkdir(parents=True)
   (path/'environment.json').write_text(json.dumps({'container':CID,'name':'bot-1','command':'start'}))
   info={'id':CID,'name':'bot-1','state':'exited'}
   with patch.object(app,'inspect_container',return_value=info),patch.object(app,'run'),patch.object(app,'status_update'):
    with self.assertRaises(RuntimeError):app.control_container({'state_dir':folder},'job',io.StringIO())
if __name__=='__main__':unittest.main()
