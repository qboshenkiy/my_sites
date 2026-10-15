"""JSON import checks using a disposable PHP server and database."""
import copy
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
BASE='http://127.0.0.1:8107/api.php?action='
class Client:
    def __init__(self):self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()));self.csrf='';self.token=''
    def call(self,action,data=None,status=200,suffix=''):
        headers={'Content-Type':'application/json','X-CSRF-Token':self.csrf}
        if self.token:headers['X-Player-Token']=self.token
        request=urllib.request.Request(BASE+action+suffix,data=json.dumps(data).encode() if data is not None else None,headers=headers)
        try:r=self.opener.open(request,timeout=15)
        except urllib.error.HTTPError as e:r=e
        with r:
            result=json.load(r);assert r.status==status,(action,r.status,result);return result
    def boot(self):self.csrf=self.call('bootstrap')['csrf']
def fixture():
    return {'title':'Викторина из JSON','translation':'Учебный перевод','testament':'Раздел','book':'Книга','totalQuestions':25,'categories':[
        {'id':c,'title':'Категория '+str(c),'questions':[
            {'id':(c-1)*5+q,'question':'Вопрос '+str(q)+' из категории '+str(c),'options':[
                {'id':letter,'text':'Вариант '+letter,'isCorrect':i==q%4} for i,letter in enumerate('abcd')],
             'correctAnswer':'abcd'[q%4],'reference':'Источник '+str(c)+':'+str(q)} for q in range(1,6)]} for c in range(1,6)]}
with tempfile.TemporaryDirectory(prefix='pulse-import-') as folder:
    server=subprocess.Popen([PHP,'-S','127.0.0.1:8107','-t',str(ROOT),str(ROOT/'router.php')],env=dict(os.environ,QUIZ_DATA_DIR=folder),stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    try:
        host=Client();guest=Client()
        for _ in range(70):
            try:host.boot();break
            except OSError:time.sleep(.1)
        host.call('setup',{'password':'test-password-2026'});host.boot();guest.boot()
        source=fixture();payload={'json':json.dumps(source,ensure_ascii=False)}
        guest.call('import_preview',payload,401)
        before=len(host.call('quizzes')['quizzes'])
        preview=host.call('import_preview',payload)
        quiz=preview['quiz'];assert quiz['mode']=='board' and quiz['scoring']=='fixed'
        assert preview['summary']['count']==25 and len(preview['summary']['categories'])==5
        assert [q['points'] for q in quiz['questions'][:5]]==[10,20,30,40,50]
        assert quiz['questions'][0]['correct']==1 and quiz['questions'][0]['reference']=='Источник 1:1'
        assert 'Учебный перевод' in quiz['description'] and 'id' not in quiz
        assert len(host.call('quizzes')['quizzes'])==before, 'Preview must never create records'
        created=host.call('save',quiz)['id']
        saved=next(q for q in host.call('quizzes')['quizzes'] if q['id']==created)
        assert saved['questions']==quiz['questions']
        # Imported questions remain editable using the ordinary manual save endpoint.
        saved['questions'][0]['text']='Исправленный вопрос';host.call('save',saved)
        assert next(q for q in host.call('quizzes')['quizzes'] if q['id']==created)['questions'][0]['text']=='Исправленный вопрос'
        room=host.call('create_room',{'id':created});player=guest.call('join',{'code':room['code'],'name':'Игрок'});guest.token=player['token']
        second=Client();second.boot();second.call('join',{'code':room['code'],'name':'Игрок 2'})
        host.call('control',{'room':room['id'],'command':'next'})
        host.call('control',{'room':room['id'],'command':'select','index':0})
        question=guest.call('state')['question'];assert 'reference' not in question and 'correct' not in question
        host.call('control',{'room':room['id'],'command':'reveal'})
        question=guest.call('state')['question'];assert question['reference']=='Источник 1:1' and question['correct']==1
        native={'id':created,'title':'Native format','questions':[{'text':'Question','type':'quiz','options':['First','Second','Third'],'correct':0,'seconds':7,'reference':'Source'}]}
        flat=host.call('import_preview',{'json':json.dumps(native)})['quiz'];assert flat['mode']=='classic' and flat['questions'][0]['seconds']==7 and len(flat['questions'][0]['options'])==3 and 'id' not in flat
        assert host.call('save',flat)['id']!=created, 'External ids must not overwrite existing quizzes'
        classic=host.call('import_preview',{**payload,'mode':'classic','seconds':30})['quiz'];assert classic['mode']=='classic' and classic['questions'][0]['seconds']==30
        flags=fixture();del flags['categories'][0]['questions'][0]['correctAnswer'];host.call('import_preview',{'json':json.dumps(flags)})
        explicit=fixture();explicit['categories'][0]['questions'][0]['points']=99
        assert host.call('import_preview',{'json':json.dumps(explicit)})['quiz']['questions'][0]['points']==99
        mismatch=fixture();mismatch['totalQuestions']=99
        assert any('99' in w for w in host.call('import_preview',{'json':json.dumps(mismatch)})['warnings'])
        assert host.call('import_preview',{'json':'\ufeff```json\n'+json.dumps(source)+'\n```'})['summary']['count']==25
        bad=[]
        x=fixture();x['categories'][0]['questions'][0]['correctAnswer']='z';bad.append(x)
        x=fixture();x['categories'][0]['questions'][0]['correctAnswer']='a';bad.append(x)
        x=fixture();x['categories'][0]['questions'][0]['options'][0]['isCorrect']=True;bad.append(x)
        x=fixture();x['categories'][0]['questions'][0]['options'][0]['id']='b';bad.append(x)
        x=fixture();x['categories'][0]['questions'][0]['options'][0]['text']='x'*121;bad.append(x)
        x=fixture();x['categories'][0]['questions'][0]['points']=20;bad.append(x)
        x=fixture();x['categories'][0]['questions'][0]['seconds']=2;bad.append(x)
        x=fixture();x['categories'][0]['questions']*=11;bad.append(x)
        x=fixture();x['questions']=[];bad.append(x)
        for source_bad in bad:
            error=host.call('import_preview',{'json':json.dumps(source_bad)},400);assert error['error']
        count=len(host.call('quizzes')['quizzes'])
        error=host.call('import_preview',{'json':'{"title":"Оборвано","options":'},400);assert 'неполный JSON' in error['error']
        host.call('import_preview',{'json':'[]'},400)
        assert len(host.call('quizzes')['quizzes'])==count
        print('PASS: categorized/native JSON, mapping answers and points, preview without writes, manual editing, new ids, invalid/truncated data, metadata and references hidden until reveal.')
    finally:server.terminate();server.wait(timeout=10)
