import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch
import app


class AutoRegistrationTests(unittest.TestCase):
    def test_removed_projects_stay_removed_after_reloading_config(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            defaults = (app.BOOKVOICE, app.GUARD, app.KOPILKA, app.NOTES)
            projects = [dict(p, directory=str(root / p['id'])) for p in defaults]
            server = types.SimpleNamespace(
                config={'projects': projects, 'state_dir': str(root / 'state'), 'projects_root': temp},
                config_path=str(root / 'config.json'))
            app.save_config(server, [], app.config_revision(server.config))
            server.config = app.load_config(server.config_path)
            with patch.object(app, 'project_from_form') as create:
                for register in (app.register_bookvoice, app.register_guard, app.register_kopilka, app.register_notes):
                    register(server)
            create.assert_not_called()
            self.assertEqual(server.config['projects'], [])
            self.assertEqual(set(server.config['disabled_auto_projects']), {p['id'] for p in defaults})

    def test_explicit_readdition_clears_only_its_opt_out(self):
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            server = types.SimpleNamespace(
                config={'projects': [], 'disabled_auto_projects': ['bookvoice', 'notes'],
                        'state_dir': str(root / 'state'), 'projects_root': temp},
                config_path=str(root / 'config.json'))
            project = dict(app.NOTES, directory=str(root / 'notes'))
            app.save_config(server, [project], app.config_revision(server.config))
            self.assertEqual(app.load_config(server.config_path)['disabled_auto_projects'], ['bookvoice'])


if __name__ == '__main__':
    unittest.main()
