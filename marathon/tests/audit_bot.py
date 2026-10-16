"""Upgrade-safe detailed history and private Telegram browsing, without contacting Telegram."""
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
with tempfile.TemporaryDirectory(prefix='marathon-audit-') as folder:
    # Start with the old journal schema and an existing record.
    with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:
        db.execute('CREATE TABLE audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id TEXT,event TEXT NOT NULL,target_id TEXT,details TEXT NOT NULL,created_at INTEGER NOT NULL)')
        db.execute("INSERT INTO audit VALUES (1,'old','reading','reader','Legacy record',1)")
    db.close()
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2026-10-22')
    def php(code,body=''):
        return json.loads(subprocess.check_output([PHP,'-r','require $argv[1];'+code,str(ROOT/'lib/telegram.php')],input=body,text=True,encoding='utf-8',env=env))
    php("""db();foreach([['admin','Admin','admin','111'],['reader','Reader','participant','222'],['mod','Moderator','moderator','333']] as $u)sql('INSERT INTO users(id,name,role,telegram_id,password,created_at) VALUES (?,?,?,?,?,?)',array_merge($u,['PRIVATE_PASSWORD_HASH',time()]));db()->exec('BEGIN IMMEDIATE');addReading('reader','reader',2,'2026-10-22','Book','Note','site','entry_one');addReading('reader','reader',2,'2026-10-22','Book','Note','site','entry_one');db()->exec('COMMIT');echo '{}';""")
    first=php('echo json_encode(auditEvents());')
    assert len(first['events'])==2  # replay did not add a journal record
    assert first['events'][-1]['details']=='Legacy record'
    m=first['events'][0]['metadata']
    assert m['week']==2 and m['cycle']==1 and m['before']['chapters']==0 and m['after']['chapters']==2
    assert m['source']=='site' and first['events'][0]['actor']=='Reader'
    php("sql(\"UPDATE users SET name='Renamed Reader' WHERE id='reader'\");echo '{}';")
    assert php('echo json_encode(auditEvents());')['events'][0]['actor']=='Reader'
    seq=100
    def bot(text,sender=111,callback=False,group=False):
        global seq
        seq+=1
        message={'chat':{'id':-1 if group else sender,'type':'group' if group else 'private'},'message_id':seq}
        update={'update_id':seq}
        if callback:update['callback_query']={'id':str(seq),'from':{'id':sender},'message':message,'data':text}
        else:update['message']={**message,'from':{'id':sender},'text':text}
        result=php('echo json_encode(telegramUpdate(json_decode(stream_get_contents(STDIN),true)),JSON_UNESCAPED_UNICODE);',json.dumps(update))
        for r in result:
            if r['method']=='sendMessage':assert len(r['args']['text'].encode())<=3500
            for row in r['args'].get('reply_markup',{}).get('inline_keyboard',[]):
                for b in row:assert len(b.get('callback_data','').encode())<=64
        return result
    def words(result):return '\n'.join(r['args'].get('text','') for r in result)
    def button(result,label):
        return next(b['callback_data'] for r in result for row in r['args'].get('reply_markup',{}).get('inline_keyboard',[]) for b in row if label in b['text'])
    assert '🧾 Журнал' in str(bot('/start'))
    for sender in [222,333,999]:
        assert 'только' in words(bot('/logs',sender))
        assert 'только' in words(bot('lg:e:2:-:0',sender,True))
    assert not bot('/logs',group=True)
    bot('ad:e:reader:2',callback=True)
    preview=bot('5 2');bot(button(preview,'Сохранить'),callback=True)
    latest=php('echo json_encode(auditEvents());')['events'][0]
    assert latest['event']=='week_result' and latest['metadata']['source']=='telegram'
    assert latest['metadata']['before']['chapters']==2 and latest['metadata']['after']['chapters']==5
    assert latest['metadata']['after']['daysManual']==2
    journal=bot('/logs');assert 'Telegram' in words(journal) and 'Главы: 2 → 5' in words(journal)
    detail=bot(button(journal,'Подробнее'),callback=True)
    assert 'Было → стало' in words(detail) and 'Операция:' in words(detail)
    assert 'PRIVATE_PASSWORD_HASH' not in str(journal)+str(detail)+json.dumps(latest)
    assert '🧾 История участника' in str(bot('ad:u:reader:2',callback=True))
    # Many records and cursor navigation remain stable when new events arrive.
    php("for($i=0;$i<12;$i++)audit('admin','fixture',$i%2?'reader':'mod','Event '.$i,['week'=>$i%2?2:1]);echo '{}';")
    page=php('echo json_encode(auditEvents(0,"b","reader",2,3));')
    assert len(page['events'])==3 and all(e['target_id']=='reader' and e['metadata']['week']==2 for e in page['events'])
    cursor=page['older'];assert cursor
    php("audit('admin','fixture','reader','New concurrent event',['week'=>2]);echo '{}';")
    older=php(f'echo json_encode(auditEvents({cursor},"b","reader",2,3));')
    assert not {e['id'] for e in page['events']} & {e['id'] for e in older['events']}
    newer=php(f'echo json_encode(auditEvents({older["newer"]},"n","reader",2,3));')
    assert [e['id'] for e in newer['events']]==[e['id'] for e in page['events']]
    journal=bot('lg:b:0:reader:2',callback=True)
    assert 'неделя 2' in words(journal) and 'Event 0' not in words(journal)
    assert 'Ранее' in str(journal)
    count=php('echo json_encode(sql("SELECT COUNT(*) FROM audit")->fetchColumn());')
    php("db()->exec('BEGIN IMMEDIATE');saveWeeklyResult('reader','admin',2,6,3,'','');db()->exec('ROLLBACK');echo '{}';")
    assert php('echo json_encode(sql("SELECT COUNT(*) FROM audit")->fetchColumn());')==count
    assert php('echo json_encode(weekResults("reader")[1]);')['chapters']==5
    php("sql(\"UPDATE users SET role='participant' WHERE id='admin'\");echo '{}';")
    assert 'только' in words(bot('lg:e:2:-:0',callback=True))
    if os.environ.get('AUDIT_UI')=='1':
        php("sql(\"UPDATE users SET role='admin',login='auditadmin',password=? WHERE id='admin'\",[password_hash('audit-test-password',PASSWORD_DEFAULT)]);echo '{}';")
        with socket.socket() as sock:
            sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
        with open(Path(folder)/'http.log','w',encoding='utf-8') as log:
            server=subprocess.Popen([PHP,'-S',f'127.0.0.1:{port}','-t',str(ROOT),str(ROOT/'router.php')],env=env,stdout=log,stderr=log)
            try:
                time.sleep(1)
                subprocess.run(['node',str(ROOT/'tests/audit_ui.cjs')],env=dict(env,AUDIT_TEST_URL=f'http://127.0.0.1:{port}'),check=True,timeout=45)
            finally:
                server.terminate();server.wait(timeout=10)
    print('PASS: old journal migration, detailed before/after, replay/rollback atomicity, frozen names, credential exclusion, stable cursors, target/week filters and private admin-only Telegram logs/details with role revocation.')
