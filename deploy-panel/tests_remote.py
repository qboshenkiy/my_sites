"""Vano Remote integration, using isolated files and mocked Docker only."""
import contextlib
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch
import app


class RemoteModuleTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.source = Path(__file__).resolve().parent.parent / 'vano_remote'
        self.p = dict(id='vano-remote', name='Vano Remote', kind='remote',
                      repo='https://github.com/qboshenkiy/my_sites.git', branch='main', subdir='vano_remote',
                      directory=str(self.root / 'remote'), compose='compose.yaml', services=['web'], profiles=[])

    def test_bootstrap_and_code_update_preserve_settings(self):
        app.validate_project(self.p)
        app.bootstrap_chrono(self.p, self.source)
        dest=Path(self.p['directory'])
        self.assertIn('127.0.0.1', app.env_text(self.p))
        self.assertIn('connect.vano.sbena.net', app.env_text(self.p))
        original=(dest/'compose.yaml').read_bytes()
        app.copy_code(self.source,dest,self.p)
        self.assertTrue((dest/'server/app.py').is_file())
        self.assertEqual((dest/'compose.yaml').read_bytes(),original)
        self.assertFalse((dest/'android').exists())
        (dest/'compose.gitdeck-https.yaml').write_text('existing route')
        (dest/'.env').write_text('KEEP_SERVER_SETTING=1\n')
        app.copy_code(self.source,dest,self.p)
        self.assertEqual(app.env_text(self.p),'KEEP_SERVER_SETTING=1\n')
        self.assertEqual((dest/'compose.gitdeck-https.yaml').read_text(),'existing route')
        with self.assertRaises(ValueError):app.bootstrap_chrono(self.p,self.source)

    def test_first_install_deploy_records_version_and_waits_for_web(self):
        config=dict(state_dir=str(self.root/'state'),projects=[self.p])
        app.db_open(config).close()
        job='c'*24
        folder=self.root/'state/jobs'/job
        folder.mkdir(parents=True)
        with app.db_open(config) as db:
            db.execute('INSERT INTO jobs(id,project,status,created,updated) VALUES(?,?,?,?,?)',
                       (job,self.p['id'],'queued',time.time(),time.time()))
        def checkout(p,c,d,log):
            shutil.copytree(self.source,d)
            return '1'*40
        with patch.object(app,'checkout',side_effect=checkout), patch.object(app,'compose',return_value=b'') as compose:
            app.deploy(config,self.p,job,io.StringIO())
        self.assertTrue(any(call.args[1][:2]==['up','-d'] and '--wait' in call.args[1] and call.args[1][-1]=='web' for call in compose.call_args_list))
        with app.db_open(config) as db:
            self.assertEqual(db.execute('SELECT status FROM jobs WHERE id=?',(job,)).fetchone()[0],'success')
            self.assertEqual(db.execute('SELECT commit_sha FROM versions WHERE project=?',(self.p['id'],)).fetchone()[0],'1'*40)

    def test_https_uses_relay_port_preserves_other_routes_and_undo(self):
        dest=Path(self.p['directory']);dest.mkdir()
        proxy_dir=self.root/'marathon';(proxy_dir/'deploy').mkdir(parents=True)
        (proxy_dir/'.env').write_text('DOMAIN=vano.sbena.net\n')
        caddy=proxy_dir/'deploy/Caddyfile'
        old='{$DOMAIN} {\n reverse_proxy web:80\n}\npulse.vano.sbena.net {\n reverse_proxy keep-pulse:80\n}\n'
        caddy.write_text(old)
        proxy=dict(id='marathon',kind='marathon',directory=str(proxy_dir),compose='compose.https.yaml')
        config=dict(projects=[self.p,proxy])
        env='APP_URL=https://connect.vano.sbena.net/\nHTTPS_PROXY_PROJECT=marathon\n'
        def docker(p,args,log):
            if args==['config','--format','json']:return json.dumps({'networks':{'default':{'name':'marathon_default'}}}).encode()
            return b''
        with patch.object(app,'compose',side_effect=docker):
            _,undo=app.prepare_chrono_https(config,self.p,env,io.StringIO())
            app.prepare_chrono_https(config,self.p,env,io.StringIO())
        self.assertEqual(caddy.read_text().count('https://connect.vano.sbena.net {'),1)
        self.assertIn('reverse_proxy gitdeck-vano-remote:8080',caddy.read_text())
        self.assertIn('reverse_proxy keep-pulse:80',caddy.read_text())
        local=(dest/'compose.gitdeck-https.yaml').read_text()
        self.assertIn('ports: !reset []',local)
        self.assertNotIn('TELEGRAM',local)
        self.assertNotIn('cookie_',local)
        with self.assertRaises(ValueError):app.prepare_chrono_https(config,self.p,env.replace('.net/','.net:8083/'),io.StringIO())
        undo()
        self.assertEqual(caddy.read_text(),old)
        self.assertFalse((dest/'compose.gitdeck-https.yaml').exists())

    def test_real_sqlite_backup_and_restore_scripts(self):
        volume=self.root/'volume';volume.mkdir()
        backup=self.root/'backup';backup.mkdir()
        db_path=volume/'rooms.sqlite'
        with contextlib.closing(sqlite3.connect(db_path)) as db:
            db.execute('CREATE TABLE rooms(room TEXT,token TEXT)');db.execute('INSERT INTO rooms VALUES(?,?)',('test-room','original-token'));db.commit()
        calls=[]
        def docker(p,args,log):
            calls.append(args)
            script=args[-1].replace('/gitdeck-backup/',backup.as_posix()+'/').replace('/data/',volume.as_posix()+'/')
            if os.name=='nt':script=script.replace('import sqlite3,os;','import sqlite3,os; os.chown=lambda *args:None;')
            subprocess.run([sys.executable,'-c',script],check=True,capture_output=True)
            return b''
        with patch.object(app,'compose',side_effect=docker):
            app.database_backup(self.p,backup,io.StringIO())
            with contextlib.closing(sqlite3.connect(db_path)) as db:
                db.execute('UPDATE rooms SET token="changed"');db.commit()
            app.database_restore(self.p,backup,io.StringIO())
        with contextlib.closing(sqlite3.connect(db_path)) as db:
            self.assertEqual(db.execute('SELECT token FROM rooms').fetchone()[0],'original-token')
        self.assertIn('--entrypoint',calls[0]);self.assertIn('python',calls[0]);self.assertTrue(any(x.endswith(':/gitdeck-backup:ro') for x in calls[1]))


if __name__=='__main__':unittest.main()
