from pathlib import Path
import tempfile
from unittest import TestCase
from unittest.mock import MagicMock, patch

import enable_telegram as upgrade


class UpgradeTests(TestCase):
    def fixture(self, directory):
        target = directory / 'installed'; source = directory / 'source'; proxy = directory / 'proxy'
        for d in (target / 'ops', source / 'ops', proxy / 'deploy'):
            d.mkdir(parents=True)
        (target / 'compose.yaml').write_text('existing compose')
        (target / '.env').write_text('private fixture value')
        (proxy / 'deploy/Caddyfile').write_text('suilo.vano.sbena.net {\n import /data/guard-sensitive.caddy\n}')
        actual = Path(__file__).parent
        for name in ('server.py', 'Dockerfile.telegram', 'compose.telegram.yaml'):
            (source / 'ops' / name).write_text((actual / name).read_text())
        project = {'id':'suilo','kind':'docker','directory':str(target),'subdir':'suilo','repo':'https://github.com/qboshenkiy/my_sites.git','services':['web','bot'],'branch':'suilo'}
        config = {'projects':[project,{'id':'proxy','kind':'marathon','compose':'compose.https.yaml','directory':str(proxy)}]}
        panel = MagicMock(); panel.load_config.return_value = config
        panel.db_open.return_value.__enter__.return_value.execute.return_value.fetchone.return_value = None
        panel.project_from_form.side_effect = lambda p,*_:p
        panel.valid_ref.side_effect = lambda ref:ref
        return target,source,proxy,panel

    def test_upgrade_preserves_secrets_base_compose_and_guard_routes(self):
        with tempfile.TemporaryDirectory() as tmp:
            target,source,proxy,panel=self.fixture(Path(tmp))
            before=(proxy / 'deploy/Caddyfile').read_text()
            with patch.object(upgrade,'TARGET',target),patch('enable_telegram.subprocess.run'):
                project=upgrade.prepare(panel,source,'release-test')
            self.assertEqual((target / '.env').read_text(),'private fixture value')
            self.assertEqual((target / 'compose.yaml').read_text(),'existing compose')
            self.assertEqual((proxy / 'deploy/Caddyfile').read_text(),before)
            self.assertEqual(project['services'],['web','bot','api'])
            self.assertEqual(project['branch'],'release-test')
            overlay=(target / 'compose.gitdeck-telegram.yaml').read_text()
            self.assertNotIn('ports:',overlay)
            self.assertIn('telegram-data:/data',overlay)
            self.assertTrue((target / '.telegram-infrastructure-before.json').is_file())
            panel.save_config.assert_called_once()

    def test_invalid_compose_rolls_back_infrastructure_before_config_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            target,source,_,panel=self.fixture(Path(tmp))
            panel.compose.side_effect = [b'',RuntimeError('invalid compose')]
            with patch.object(upgrade,'TARGET',target),patch('enable_telegram.subprocess.run'),self.assertRaises(RuntimeError):
                upgrade.prepare(panel,source)
            self.assertFalse((target / 'compose.gitdeck-telegram.yaml').exists())
            self.assertFalse((target / 'ops/server.py').exists())
            panel.save_config.assert_not_called()

    def test_does_not_replace_an_unmanaged_overlay(self):
        with tempfile.TemporaryDirectory() as tmp:
            target,source,_,panel=self.fixture(Path(tmp))
            overlay=target / 'compose.gitdeck-telegram.yaml';overlay.write_text('a different overlay')
            with patch.object(upgrade,'TARGET',target),patch('enable_telegram.subprocess.run'),self.assertRaises(ValueError):
                upgrade.prepare(panel,source)
            self.assertEqual(overlay.read_text(),'a different overlay')
            panel.save_config.assert_not_called()
