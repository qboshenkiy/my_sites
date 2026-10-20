"""Completed-game reports: real PHP/SQLite, access control and atomic reassignment."""
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import sqlite3
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
class Client:
    def __init__(self,base):
        self.base=base;self.csrf='';self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
    def call(self,action,body=None,status=200):
        request=urllib.request.Request(self.base+'/api.php?action='+action,data=json.dumps(body).encode() if body is not None else None,headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf})
        try:response=self.opener.open(request,timeout=15)
        except urllib.error.HTTPError as error:response=error
        with response:
            data=json.load(response);assert response.status==status,(action,response.status,data);return data
    def boot(self):
        data=self.call('bootstrap');self.csrf=data['csrf'];return data
    def register(self,name,login):
        self.boot();self.call('register',{'name':name,'login':login,'password':'testing-password'});return self.boot()['user']['id']

with tempfile.TemporaryDirectory(prefix='pulse-report-') as tmp:
    with socket.socket() as sock:sock.bind(('127.0.0.1',0));port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}';env=dict(os.environ,QUIZ_DATA_DIR=tmp)
    server=subprocess.Popen([PHP,'-S',f'127.0.0.1:{port}','-t',str(ROOT),str(ROOT/'router.php')],env=env,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        admin=Client(url)
        for _ in range(80):
            try:admin.boot();break
            except OSError:time.sleep(.1)
        admin.call('setup',{'password':'testing-admin-password'});admin.boot()
        readers=[Client(url) for _ in range(3)]
        ids=[r.register(name,'reader_'+str(i)) for i,(r,name) in enumerate(zip(readers,['Анна','Борис','Вера']))]
        fixture={'title':'Бытие · итоговая викторина','questions':[
            {'text':'Первый вопрос','type':'quiz','seconds':20,'points':500,'options':['Да','Нет'],'correct':0},
            {'text':'Ваше мнение','type':'poll','seconds':20,'points':1000,'options':['Да','Нет'],'correct':0},
            {'text':'Последний вопрос','type':'quiz','seconds':20,'points':500,'options':['Да','Нет'],'correct':0}]}
        quiz=admin.call('save',fixture)['id'];room=admin.call('create_room',{'id':quiz})
        for name in ['Гость А','Гость Б','Гость В']:Client(url).call('join',{'code':room['code'],'name':name})
        db=sqlite3.connect(Path(tmp)/'quiz.sqlite')
        players=db.execute('SELECT id FROM players WHERE room_id=? ORDER BY name',(room['id'],)).fetchall()
        for player,score in zip(players,[750,650,0]):db.execute('UPDATE players SET score=? WHERE id=?',(score,player[0]))
        db.execute("UPDATE rooms SET status='finished',current_index=2 WHERE id=?",(room['id'],))
        db.execute('INSERT INTO answers VALUES (?,?,?,?,?,?)',(players[0][0],room['id'],0,0,500,time.time()));db.commit()
        original=db.execute('SELECT * FROM answers').fetchall()
        snapshot=admin.call('room_participants&room='+room['id']);assert snapshot['maximum']['points']==1000
        links=[{'player_id':p['id'],'user_id':uid} for p,uid in zip(snapshot['players'],ids)]
        def save(links=links,maximum=None,revision=None,status=200):
            revision=admin.call('room_participants&room='+room['id'])['room']['revision'] if revision is None else revision
            return admin.call('link_room_players',{'room':room['id'],'revision':revision,'max_points':maximum,'links':links},status)
        created=save();report=created['assessment'];assert report
        assert [r.call('assessments')['assessments'][0]['scores'][0]['percent'] for r in readers]==[75,65,0]
        for r in readers:
            own=r.call('assessments')['assessments'][0];assert len(own['scores'])==1
            r.call('room_participants&room='+room['id'],status=403)
            r.call('link_room_players',{'room':room['id'],'links':links},403)
        assert save()['assessment']==report
        assert db.execute('SELECT count(*) FROM assessments WHERE source_room_id=?',(room['id'],)).fetchone()[0]==1
        save(revision=0,status=409)
        duplicate=[dict(x) for x in links];duplicate[1]['user_id']=ids[0];save(duplicate,status=409)
        save(maximum=700,status=400)
        assert db.execute('SELECT count(*) FROM assessment_scores WHERE assessment_id=?',(report,)).fetchone()[0]==3
        save(maximum=1500);assert readers[0].call('assessments')['assessments'][0]['scores'][0]['percent']==50
        save();assert readers[0].call('assessments')['assessments'][0]['scores'][0]['percent']==75
        swapped=[dict(x) for x in links];swapped[0]['user_id'],swapped[1]['user_id']=ids[1],ids[0];save(swapped)
        assert readers[0].call('assessments')['assessments'][0]['scores'][0]['percent']==65
        swapped[1]['user_id']=None;save(swapped);assert readers[0].call('assessments')['assessments']==[]
        save();assert db.execute('SELECT * FROM answers').fetchall()==original
        assert [row[0] for row in db.execute('SELECT score FROM players WHERE room_id=? ORDER BY name',(room['id'],))]==[750,650,0]
        grade=admin.call('assessments')['assessments'][0]
        admin.call('save_assessment',dict(grade,scores=[]),409)
        foreign=readers[0].call('create_room',{'id':readers[0].call('save',fixture)['id']})
        admin.call('room_participants&room='+foreign['id'],status=404)
        admin.call('link_room_players',{'room':foreign['id'],'revision':0,'links':[]},404)
        # Early finish only counts questions actually reached; boards only count chosen cells.
        early=admin.call('create_room',{'id':quiz})
        db.execute("UPDATE rooms SET status='finished',current_index=0 WHERE id=?",(early['id'],));db.commit()
        assert admin.call('room_participants&room='+early['id'])['maximum']['points']==500
        board=dict(fixture,mode='board',questions=[dict(q,category='Раздел '+str(i)) for i,q in enumerate(fixture['questions'])]);board_id=admin.call('save',board)['id'];board_room=admin.call('create_room',{'id':board_id})
        db.execute("UPDATE room_meta SET played='[1,2]' WHERE room_id=?",(board_room['id'],));db.commit()
        assert admin.call('room_participants&room='+board_room['id'])['maximum']['points']==500
        # Linked players get a report on normal host finish as well.
        live=admin.call('create_room',{'id':quiz});reader=readers[0].call('join',{'code':live['code'],'name':'Анна'})
        admin.call('control',{'room':live['id'],'command':'next'});admin.call('control',{'room':live['id'],'command':'finish'})
        assert admin.call('room_participants&room='+live['id'])['report']
        print('PASS: completed-game reports, 750/650/0 -> 75/65/0%, privacy, ownership, atomic swap/unlink, stale edits, unique report and preserved answers')
        print('PASS: played-question maximum, poll exclusion, early finish, selected board cells and automatic report on finish')
        if os.environ.get('REPORT_UI')=='1':
            subprocess.run(['node',str(ROOT/'tests/room_reports_ui.cjs')],env=dict(env,REPORT_TEST_URL=url,REPORT_ROOM_ID=room['id']),check=True,timeout=90)
        db.close()
    finally:
        if 'db' in locals():db.close()
        server.terminate();server.wait(timeout=10)
