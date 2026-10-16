"""Private Telegram admin flows with disposable data and no Telegram API calls."""
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
with tempfile.TemporaryDirectory(prefix='marathon-admin-bot-') as folder:
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2026-10-22')
    def php(code,body=''):
        return json.loads(subprocess.check_output([PHP,'-r','require $argv[1];'+code,str(ROOT/'lib/telegram.php')],input=body,text=True,encoding='utf-8',env=env))
    php('''db();foreach([['adminone','Admin One','admin','111'],['admintwo','Admin Two','admin','222'],['reader','Reader Target','participant','333'],['moderator','Moderator','moderator','444']] as $u)sql('INSERT INTO users(id,name,role,telegram_id,created_at) VALUES (?,?,?,?,?)',array_merge($u,[time()]));for($i=0;$i<12;$i++)sql('INSERT INTO users(id,name,role,created_at) VALUES (?,?,?,?)',['extra'.$i,'Extra '.$i,'participant',time()]);db()->exec('BEGIN IMMEDIATE');addReading('reader','reader',3,'2026-10-22','','','site','daily_fixture');db()->exec('COMMIT');echo '{}';''')
    sequence=1000
    def bot(text,sender=111,callback=False,group=False):
        global sequence
        sequence+=1
        message={'chat':{'id':-123 if group else sender,'type':'group' if group else 'private'},'message_id':sequence}
        update={'update_id':sequence}
        if callback:update['callback_query']={'id':str(sequence),'from':{'id':sender},'message':message,'data':text}
        else:update['message']={**message,'from':{'id':sender},'text':text}
        result=php('echo json_encode(telegramUpdate(json_decode(stream_get_contents(STDIN),true)),JSON_UNESCAPED_UNICODE);',json.dumps(update))
        for r in result:
            if r['method']=='sendMessage':assert len(r['args']['text'].encode())<=3500
            for row in r['args'].get('reply_markup',{}).get('inline_keyboard',[]):
                for b in row:assert len(b.get('callback_data','').encode())<=64
        return result
    def words(result):return '\n'.join(x['args'].get('text','') for x in result)
    def button(result,label):
        for r in result:
            for row in r['args'].get('reply_markup',{}).get('inline_keyboard',[]):
                for b in row:
                    if label in b['text']:return b['callback_data']
        raise AssertionError((label,result))
    def week(n=2,id='reader'):return php('echo json_encode(weekResults("'+id+'")['+str(n-1)+']);')
    def sql(query,args=()):
        with sqlite3.connect(Path(folder)/'marathon.sqlite') as db:db.execute(query,args)
        db.close()
    assert '👥 Участники' in str(bot('/start')) and '📋 Общий отчёт' in str(bot('/start'))
    assert '👥 Участники' not in str(bot('/start',333))
    for sender in [333,444,999]:
        assert 'только' in words(bot('👥 Участники',sender))
        assert 'только' in words(bot('ad:e:reader:2',sender,True))
    assert not bot('📋 Общий отчёт',111,group=True)
    report=bot('📋 Общий отчёт');assert 'Всего: 16' in words(report)
    page2=bot(button(report,'Далее'),callback=True);assert 'Страница 2' in words(page2)
    assert 'Круг 1' in words(bot('ad:u:reader:2',callback=True))
    bot('ad:e:reader:2',callback=True)
    assert 'от 0 до 7' in words(bot('8 2'))
    preview=bot('5 2');confirm=button(preview,'Сохранить');assert week()['chapters']==3
    assert 'Подтверждение' in words(bot(confirm,222,True))
    result=bot(confirm,callback=True);assert 'Сохранено' in words(result)
    w=week();assert w['chapters']==5 and w['days']==2 and w['chaptersDaily']==3
    assert week(id='adminone')['chapters']==0
    bot(confirm,callback=True);assert week()['chapters']==5
    bot('ad:e:reader:2',callback=True);preview=bot('2');bot(button(preview,'Отмена'),callback=True);assert week()['chapters']==5
    bot('ad:e:reader:2',callback=True);preview=bot('2 1');bot(button(preview,'Сохранить'),callback=True)
    assert week()['chapters']==2 and week()['chaptersDaily']==3
    preview=bot('ad:c:reader:2',callback=True);bot(button(preview,'Сохранить'),callback=True);assert week()['completed']
    assert 'закрыта' in words(bot('ad:e:reader:1',callback=True))
    preview=bot('ad:c:reader:1',callback=True);bot(button(preview,'Сохранить'),callback=True);assert week(1)['late']
    assert 'ещё не началась' in words(bot('ad:c:reader:3',callback=True))
    # Reject changed plans/results, expired sessions and account changes.
    bot('ad:e:reader:2',callback=True);preview=bot('4 2');confirm=button(preview,'Сохранить')
    sql('UPDATE week_plans SET chapters=8 WHERE week=2')
    assert 'изменился' in words(bot(confirm,callback=True));assert week()['chapters']==7
    sql('UPDATE week_plans SET chapters=7 WHERE week=2')
    bot('ad:e:reader:2',callback=True);preview=bot('4 2');confirm=button(preview,'Сохранить')
    sql('UPDATE telegram_admin_states SET expires_at=0');bot(confirm,callback=True);assert week()['chapters']==7
    bot('ad:e:reader:2',callback=True);preview=bot('4 2');confirm=button(preview,'Сохранить')
    sql("UPDATE users SET active=0 WHERE id='reader'");bot(confirm,callback=True);assert week()['chapters']==7
    sql("UPDATE users SET active=1 WHERE id='reader'")
    bot('ad:e:reader:2',callback=True);preview=bot('4 2');confirm=button(preview,'Сохранить')
    sql("UPDATE users SET role='moderator',session_epoch=session_epoch+1 WHERE id='adminone'")
    assert 'только' in words(bot(confirm,callback=True));assert week()['chapters']==7
    sql("UPDATE users SET role='admin' WHERE id='adminone'")
    bot('ad:e:reader:2',callback=True);bot('📊 Мой прогресс');bot('4 2');assert week()['chapters']==7
    bot('ad:e:reader:2',callback=True);first=button(bot('4 2'),'Сохранить');bot('ad:e:reader:2',callback=True);second=button(bot('6 2'),'Сохранить')
    bot(first,callback=True);assert week()['chapters']==7
    bot(second,callback=True);assert week()['chapters']==6
    assert '6/7' in words(bot('ad:u:reader:2',callback=True))
    print('PASS: admin keyboard, paginated all-user report, edit/complete with confirmation, manual days and daily history, private admin-only access, forged/old/expired callbacks, revoked roles, changed plans and menu cancellation.')
