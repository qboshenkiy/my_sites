"""Disposable preview of the reading plan. No real Telegram or user database."""
import os
from pathlib import Path
import subprocess
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
PHP='C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
with tempfile.TemporaryDirectory(prefix='reading-books-preview-') as folder:
    env=dict(os.environ,MARATHON_DATA_DIR=folder,MARATHON_TEST_TODAY='2026-10-22',
             TELEGRAM_BOT_TOKEN='fake-preview-token',TELEGRAM_BOT_USERNAME='fixture_bot')
    seed='''require $argv[1];db();
    sql("INSERT INTO users(id,name,login,password,role,created_at) VALUES (?,?,?,?,?,?)",['qaadmin','Администратор','admin',password_hash('preview-password-2026',PASSWORD_DEFAULT),'admin',time()]);
    sql("INSERT INTO users(id,name,role,telegram_id,created_at) VALUES (?,?,?,?,?)",['qareader','Алина Иванова','participant','123456',time()]);
    sql("UPDATE week_plans SET chapters=14 WHERE week IN (1,2)");
    sql("INSERT INTO week_plan_books VALUES (?,?,?,?,?,?)",['book1',1,0,'Матфей',1,14]);
    sql("INSERT INTO week_plan_books VALUES (?,?,?,?,?,?)",['book2',2,0,'Марк',1,7]);
    sql("INSERT INTO week_plan_books VALUES (?,?,?,?,?,?)",['book3',2,1,'Лука',1,7]);
    db()->exec('BEGIN IMMEDIATE');addReading('qareader','qareader',3,'2026-10-22','Марк, главы 1–3','','site','preview_entry');db()->exec('COMMIT');'''
    subprocess.run([PHP,'-r',seed,str(ROOT/'lib/core.php')],env=env,check=True)
    process=subprocess.Popen([PHP,'-S','127.0.0.1:8112','-t',str(ROOT),str(ROOT/'router.php')],env=env,
                             stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    print('Reading preview: http://127.0.0.1:8112/\nAdmin: admin / preview-password-2026\nData: '+folder,flush=True)
    try:
        while process.poll() is None:time.sleep(1)
    finally:
        process.terminate();process.wait(timeout=10)
