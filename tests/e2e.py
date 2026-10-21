"""End-to-end checks against a real PHP server and an isolated database."""
import http.cookiejar
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
PHP = shutil.which('php') or 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
EXTERNAL_BASE = os.environ.get('QUIZ_TEST_BASE')
BASE = EXTERNAL_BASE or 'http://127.0.0.1:8099/'

class Client:
    def __init__(self):
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.csrf = ''
        self.token = ''

    def call(self, action, payload=None, expected=200, suffix=''):
        headers = {'Content-Type': 'application/json', 'X-CSRF-Token': self.csrf}
        if self.token:
            headers['X-Player-Token'] = self.token
        req = urllib.request.Request(BASE + 'api.php?action=' + action + suffix,
            data=json.dumps(payload).encode() if payload is not None else None, headers=headers)
        try:
            response = self.opener.open(req, timeout=5)
        except urllib.error.HTTPError as error:
            response = error
        result = json.loads(response.read())
        assert response.status == expected, (action, response.status, result)
        return result

if not EXTERNAL_BASE:
    with socket.socket() as probe:
        probe.bind(('127.0.0.1', 8099))

with tempfile.TemporaryDirectory(prefix='pulse-test-') as tmp:
    env = dict(os.environ, QUIZ_DATA_DIR=tmp)
    server = None if EXTERNAL_BASE else subprocess.Popen([PHP, '-S', '127.0.0.1:8099', '-t', str(ROOT), str(ROOT / 'router.php')], env=env,
                                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    try:
        host, guest, stranger = Client(), Client(), Client()
        for _ in range(60):
            try:
                initial = host.call('bootstrap')
                break
            except (urllib.error.URLError, ConnectionError):
                time.sleep(.1)
        else:
            raise AssertionError('PHP server did not start')
        assert not initial['configured'] and not initial['admin']
        host.csrf = initial['csrf']
        try:
            host.opener.open(BASE + 'storage/quiz.sqlite')
            raise AssertionError('Database must not be served over HTTP')
        except urllib.error.HTTPError as error:
            assert error.code in (403, 404)
        host.call('setup', {'password': 'test-password-123'})
        host.call('setup', {'password': 'another-password'}, expected=409)
        stranger.call('quizzes', expected=401)
        stranger.call('save', {}, expected=403)
        data = host.call('quizzes')
        assert len(data['quizzes']) == 3
        questions = [
            {'text': '2 + 2?', 'type': 'quiz', 'options': ['4', '5'], 'correct': 0, 'seconds': 5},
            {'text': 'Как дела?', 'type': 'poll', 'options': ['Хорошо', 'Отлично'], 'correct': None, 'seconds': 5},
        ]
        quiz = host.call('save', {'title': 'E2E викторина', 'description': 'Тест', 'questions': questions})
        host.call('save', {'title': '', 'questions': questions}, expected=400)
        room = host.call('create_room', {'id': quiz['id']})
        join = guest.call('join', {'code': room['code'], 'name': '<Игрок>'})
        guest.token = join['token']
        stranger.call('join', {'code': room['code'], 'name': '<Игрок>'}, expected=400)
        assert guest.call('state')['status'] == 'lobby'
        host.call('control', {'room': room['id'], 'command': 'next'})
        host.call('control', {'room': room['id'], 'command': 'next'}, expected=400)
        playing = guest.call('state')
        assert playing['status'] == 'question' and 'correct' not in playing['question']
        guest.call('answer', {'choice': 0, 'index': 1}, expected=400)
        guest.call('answer', {'choice': 0, 'index': 0})
        guest.call('answer', {'choice': 1, 'index': 0}, expected=409)
        before = guest.call('state')
        assert before['status']=='results' and before['question']['correct']==0 and before['answer']['points']>0
        host.call('control', {'room': room['id'], 'command': 'reveal'})
        results = guest.call('state')
        assert results['counts'] == [1, 0] and results['question']['correct'] == 0
        score = results['players'][0]['score']
        assert 500 <= score <= 1000
        guest.call('answer', {'choice': 0, 'index': 0}, expected=409)
        # Editing the template never changes an existing room's questions.
        host.call('save', {'id': quiz['id'], 'title': 'Изменено', 'questions': [questions[0]]})
        host.call('control', {'room': room['id'], 'command': 'next'})
        assert guest.call('state')['question']['type'] == 'poll'
        guest.call('answer', {'choice': 1, 'index': 1})
        time.sleep(5.2)
        expired = guest.call('state')
        assert expired['status'] == 'results' and expired['counts'] == [0, 1]
        assert expired['players'][0]['score'] == score
        guest.call('answer', {'choice': 0, 'index': 1}, expected=409)
        host.call('control', {'room': room['id'], 'command': 'next'})
        assert guest.call('state')['status'] == 'finished'
        assert guest.call('state')['title'] == 'E2E викторина'
        multi=host.call('save',{'title':'Несколько верных','scoring':'fixed','questions':[{'text':'Выберите оба числа','type':'quiz','seconds':30,'options':['2','3','5','7','11','13'],'correct':[0,4],'points':1000}]})
        room_multi=host.call('create_room',{'id':multi['id']});guest.token=guest.call('join',{'code':room_multi['code'],'name':'Анна'})['token'];stranger.token=stranger.call('join',{'code':room_multi['code'],'name':'Борис'})['token']
        host.call('control',{'room':room_multi['id'],'command':'next'});assert guest.call('state')['question']['multiple'] is True
        guest.call('answer',{'choices':[0,4],'index':0});stranger.call('answer',{'choices':[0],'index':0})
        multi_result=guest.call('state');assert multi_result['status']=='results' and multi_result['question']['correct']==[0,4] and multi_result['counts']==[2,0,0,0,1,0]
        points={p['name']:p['score'] for p in multi_result['players']};assert points['Анна']==1000 and points['Борис']==0
        stranger.call('join', {'code': room['code'], 'name': 'Поздний'}, expected=400)
        host.call('delete', {'id': quiz['id']})
        assert guest.call('state')['title'] == 'Несколько верных'
        host.call('logout', {})
        host.call('quizzes', expected=401)
        host.call('login', {'password': 'wrong-pass'}, expected=401)
        host.call('login', {'password': 'test-password-123'})
        assert len(host.call('quizzes')['rooms']) == 2
        print('PASS: admin auth, CSRF, quiz CRUD, room snapshot, join, hidden answers, duplicate protection, multi-answer scoring, polls, deadline, final results and persistence.')
    finally:
        if server:
            server.terminate()
            server.wait(timeout=10)
