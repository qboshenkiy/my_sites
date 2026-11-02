"""Provisioning contracts, without Docker or a remote server."""
import io
import json
from pathlib import Path
import tempfile
import types
import unittest
from unittest.mock import patch
import app


class BookVoiceTests(unittest.TestCase):
    def test_registration_is_persistent_and_idempotent(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            config = {'projects': [], 'state_dir': str(root/'state'), 'projects_root': str(root)}
            server = types.SimpleNamespace(config=config, config_path=str(root/'config.json'))
            project = dict(app.BOOKVOICE, directory=str(root/'bookvoice'))
            with patch.object(app, 'BOOKVOICE', project):
                app.register_bookvoice(server)
                revision = app.config_revision(server.config)
                app.register_bookvoice(server)
            self.assertEqual(len(server.config['projects']), 1)
            self.assertEqual(revision, app.config_revision(server.config))
            self.assertEqual(app.load_config(server.config_path)['projects'][0]['id'], 'bookvoice')

    def test_setup_preserves_existing_files_and_hides_password(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            p = dict(app.BOOKVOICE, directory=str(root/'site'))
            dest = Path(p['directory']); dest.mkdir()
            (dest/'.env').write_text('private settings')
            (dest/'compose.yaml').write_text('existing compose')
            folder = root/'jobs'/'test'; folder.mkdir(parents=True)
            payload = folder/'environment.json'; payload.write_text(json.dumps({'password':'private-test-password'}))
            def checkout(project, config, source, log):
                source.mkdir()
                for name in project['paths']:
                    if name in ('src', 'web'):
                        (source/name).mkdir()
                    else:
                        (source/name).write_text('source')
                return 'a'*40
            log = io.StringIO()
            with patch.object(app, 'BOOKVOICE', p), patch.object(app, 'checkout', side_effect=checkout), patch.object(app, 'compose'), patch.object(app, 'run'), patch.object(app, 'status_update'), patch.object(app.subprocess, 'run', return_value=types.SimpleNamespace(returncode=0)) as execute:
                app.setup_bookvoice({'state_dir':temp}, p, 'test', log)
            self.assertEqual((dest/'compose.yaml').read_text(), 'existing compose')
            self.assertEqual((dest/'.env').read_text(), 'private settings')
            self.assertEqual(execute.call_args.kwargs['input'], b'private-test-password')
            self.assertNotIn('private-test-password', str(execute.call_args.args))
            self.assertNotIn('private-test-password', log.getvalue())
            self.assertFalse(payload.exists())

    def test_failure_cleans_credential_payload(self):
        with tempfile.TemporaryDirectory() as temp:
            folder=Path(temp)/'jobs'/'test';folder.mkdir(parents=True)
            payload=folder/'environment.json';payload.write_text('{"password":"private-test-password"}')
            with patch.object(app, 'checkout', side_effect=RuntimeError('network unavailable')):
                with self.assertRaises(RuntimeError):
                    app.setup_bookvoice({'state_dir':temp}, dict(app.BOOKVOICE), 'test', io.StringIO())
            self.assertFalse(payload.exists())

if __name__ == '__main__':
    unittest.main()
