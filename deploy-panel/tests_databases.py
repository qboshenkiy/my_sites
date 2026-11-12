from contextlib import closing
import http.client
import http.server
import json
import os
from pathlib import Path
import sqlite3
import stat
import tempfile
import threading
import time
import unittest
from unittest.mock import patch
import app


class DatabaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name);self.file=self.root/'sample.sqlite'
        with closing(sqlite3.connect(self.file)) as db, db:
            db.execute('CREATE TABLE records(id INTEGER PRIMARY KEY, name TEXT, password_hash TEXT, payload BLOB, optional TEXT)')
            db.executemany('INSERT INTO records VALUES(?,?,?,?,?)',[(i,'Иван '+str(i),'private-secret',b'blob',None) for i in range(1,62)])
            db.execute('CREATE TABLE "odd""table" ("a""column" TEXT)')
            db.execute('INSERT INTO "odd""table" VALUES(?)',("literal % _ ' text",))
        self.explorer=app.DatabaseExplorer()
        self.source={'id':'fixture','kind':'sqlite','project':'demo','project_name':'Fixture','name':self.file.name,'path':str(self.file),'root':str(self.root),'bytes':self.file.stat().st_size}
        self.config={'state_dir':str(self.root/'state'),'projects':[{'id':'demo','name':'Fixture','directory':str(self.root),'kind':'docker'}]}
        Path(self.config['state_dir']).mkdir()

    def test_select_pages_types_and_redaction(self):
        result=self.explorer.rows(self.source,'records')
        self.assertEqual(len(result['rows']),25);self.assertTrue(result['has_more'])
        self.assertEqual(result['rows'][0],['1','Иван 1','•••','[двоичные данные]',None])
        self.assertNotIn('private-secret',json.dumps(result))
        self.assertEqual(self.explorer.rows(self.source,'records',offset=50)['rows'][-1][0],'61')
        self.assertFalse(self.explorer.rows(self.source,'records',offset=50)['has_more'])

    def test_cyrillic_search_and_literal_sql_punctuation(self):
        self.assertEqual(len(self.explorer.rows(self.source,'records','иВаН 61')['rows']),1)
        result=self.explorer.rows(self.source,'odd"table',"% _ ' text")
        self.assertEqual(result['rows'],[["literal % _ ' text"]])
        self.assertEqual(self.explorer.rows(self.source,'records',"' OR 1=1 --")['rows'],[])
        self.assertEqual(self.explorer.rows(self.source,'records','private-secret')['rows'],[])
        self.assertEqual(len(self.explorer.tables(self.source)),2)

    def test_rejects_unknown_tables_bad_offsets_and_symlink_replacement(self):
        for table,search,offset in [('records; DROP TABLE records','',0),('records','x'*201,0),('records','',-1),('records','',True)]:
            with self.assertRaises(ValueError):self.explorer.rows(self.source,table,search,offset)
        other=self.root/'other.sqlite';other.write_bytes(self.file.read_bytes())
        self.file.unlink();self.file.symlink_to(other)
        with self.assertRaises(ValueError):self.explorer.tables(self.source)

    def test_sqlite_connection_is_read_only(self):
        db=self.explorer.connect(self.source)
        try:
            with self.assertRaises(sqlite3.OperationalError):db.execute('DELETE FROM records')
        finally:db.close()
        self.assertEqual(len(self.explorer.rows(self.source,'records')['rows']),25)

    def test_catalog_deduplicates_sources_skips_backups_and_never_returns_container_env(self):
        (self.root/'backups').mkdir();(self.root/'backups/old.sqlite').write_bytes(self.file.read_bytes())
        (self.root/'alias.sqlite').symlink_to(self.file)
        container={'Id':'container','Config':{'Image':'python:3','Env':['SECRET=not-for-client'],'Labels':{'com.docker.compose.project.working_dir':str(self.root)}},'State':{'Running':True},'Name':'/demo-web','Mounts':[{'Type':'volume','Source':str(self.root)}]}
        def command(args,**_):return 'container' if args[1:3]==['ps','-aq'] else json.dumps([container])
        with patch.object(self.explorer,'command',side_effect=command):catalog=self.explorer.catalog(self.config,True)
        self.assertEqual(len(catalog['sources']),1)
        self.assertNotIn('not-for-client',json.dumps(catalog));self.assertNotIn('user',catalog['sources'][0])
        self.assertEqual(self.explorer.source(self.config,catalog['sources'][0]['id'])['path'],str(self.file))
        with self.assertRaises(ValueError):self.explorer.source(self.config,str(self.file))

    def test_backup_is_consistent_with_live_wal_and_source_stays_unchanged(self):
        live=sqlite3.connect(self.file);self.addCleanup(live.close)
        live.execute('PRAGMA journal_mode=WAL');live.execute("INSERT INTO records VALUES(99,'Новая запись','secret',NULL,NULL)");live.commit()
        copy=self.explorer.backup(self.config,self.source)
        file,name=self.explorer.download(self.config,copy['id'])
        with closing(sqlite3.connect(file)) as db:
            self.assertEqual(db.execute('select name from records where id=99').fetchone()[0],'Новая запись')
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0],'ok')
        self.assertEqual(stat.S_IMODE(file.stat().st_mode),0o600)
        self.assertEqual(live.execute('select count(*) from records').fetchone()[0],62)
        self.assertEqual(len(self.explorer.backups(self.config)),1)
        with self.assertRaises(ValueError):self.explorer.download(self.config,'../../etc/passwd')
        file.unlink();file.symlink_to(self.file)
        with self.assertRaises(ValueError):self.explorer.download(self.config,copy['id'])

    def test_backup_failure_removes_partial_files(self):
        with patch.object(self.explorer,'connect',side_effect=RuntimeError('fixture failure')):
            with self.assertRaises(RuntimeError):self.explorer.backup(self.config,self.source)
        self.assertEqual(list((Path(self.config['state_dir'])/'database-backups').iterdir()),[])

    def test_pg_read_only_transaction_and_argv(self):
        source={'container':'abc','user':'postgres','database':'chrono'}
        with patch.object(self.explorer,'command',return_value='[]') as run:
            self.assertEqual(self.explorer.pg(source,'SELECT 1'),[])
        sql=run.call_args.kwargs['text'];args=run.call_args.args[0]
        self.assertIn('BEGIN READ ONLY',sql);self.assertIn('statement_timeout',sql);self.assertIn('ROLLBACK',sql)
        self.assertEqual(args[3:6],['abc','psql','-X']);self.assertIn('chrono',args)

    def test_pg_identifier_and_filter_quoting(self):
        source={'kind':'postgres'}
        columns=[{'name':'id','type':'integer'},{'name':'a"name','type':'text'},{'name':'api_token','type':'text'}]
        with patch.object(self.explorer,'table',return_value={'schema':'public','name':'odd"table'}),patch.object(self.explorer,'pg',side_effect=[columns,[]]) as pg:
            self.explorer.rows(source,'id',"x' OR true --")
        sql=pg.call_args.args[1]
        self.assertIn('"public"."odd""table"',sql)
        self.assertIn("x'' OR true --",sql)
        self.assertIn("'•••'",sql)
        self.assertNotIn('api_token"::text ILIKE',sql)


class DatabaseHTTPTests(unittest.TestCase):
    def setUp(self):
        self.fixture=DatabaseTests();self.fixture.setUp();self.addCleanup(self.fixture.doCleanups)
        self.server=http.server.ThreadingHTTPServer(('127.0.0.1',0),app.Panel)
        self.server.config=self.fixture.config;self.server.demo=False;self.server.explorer=self.fixture.explorer
        self.server.explorer.sources={'fixture':self.fixture.source};self.server.explorer.stamp=time.time()
        self.previous=app.Panel.sessions
        app.Panel.sessions={'test':{'csrf':'csrf-fixture','expires':time.time()+60}}
        self.thread=threading.Thread(target=self.server.serve_forever,daemon=True);self.thread.start()
        self.addCleanup(self.cleanup)

    def cleanup(self):
        self.server.shutdown();self.server.server_close();self.thread.join();app.Panel.sessions=self.previous

    def request(self,method,path,body=None,cookie=True,csrf='csrf-fixture',origin=None):
        c=http.client.HTTPConnection(*self.server.server_address,timeout=5)
        host='127.0.0.1:'+str(self.server.server_port)
        headers={'Origin':origin or 'http://'+host,'Content-Type':'application/json'}
        if cookie:headers['Cookie']='gitdeck=test'
        if body is not None:body=dict(body,csrf=csrf)
        c.request(method,path,json.dumps(body) if body is not None else None,headers)
        r=c.getresponse();status=r.status;content=r.read();c.close();return status,content

    def test_unauthenticated_catalog_rows_and_download_are_rejected(self):
        for path in ('/api/databases','/api/databases/rows?source=fixture&table=records','/api/databases/download?id='+'0'*32):
            self.assertEqual(self.request('GET',path,cookie=False)[0],401)
        status,raw=self.request('GET','/api/databases/rows?source=fixture&table=records')
        self.assertEqual(status,200);self.assertEqual(len(json.loads(raw)['rows']),25)

    def test_backups_require_origin_csrf_and_no_active_job(self):
        self.assertEqual(self.request('POST','/api/databases/backup',{'source':'fixture'},csrf='wrong')[0],403)
        self.assertEqual(self.request('POST','/api/databases/backup',{'source':'fixture'},origin='http://evil.test')[0],403)
        with app.db_open(self.server.config) as db:
            db.execute("INSERT INTO jobs(id,project,action,status,created,updated) VALUES('fixture','demo','update','queued',0,0)")
        self.assertEqual(self.request('POST','/api/databases/backup',{'source':'fixture'})[0],409)

    def test_create_and_authenticated_download(self):
        status,raw=self.request('POST','/api/databases/backup',{'source':'fixture'})
        self.assertEqual(status,200);token=json.loads(raw)['backup']['id']
        status,raw=self.request('GET','/api/databases/download?id='+token)
        self.assertEqual(status,200);self.assertTrue(raw.startswith(b'SQLite format 3'))

    def test_demo_does_not_connect_to_real_sources_and_blocks_backups(self):
        self.server.demo=True
        with patch.object(self.server.explorer,'catalog',side_effect=AssertionError('no real database')):
            self.assertEqual(self.request('GET','/api/databases')[0],200)
            self.assertEqual(self.request('POST','/api/databases/backup',{'source':'fixture'})[0],403)


if __name__=='__main__':unittest.main()
