"""Called by deploy_smoke.py against its disposable PostgreSQL and HTTP server."""
import http.cookiejar
import json
from pathlib import Path
import re
import urllib.error
import urllib.parse
import urllib.request


class Browser:
    def __init__(self, base, client=None, token=None):
        self.base = base
        self.client = client or urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.token = token

    def get(self, path, expected=200):
        try:
            response = self.client.open(self.base + path)
        except urllib.error.HTTPError as error:
            response = error
        assert response.code == expected, (path, response.code)
        return response.read().decode()

    def post(self, path, data, expected=200, as_json=True):
        body = urllib.parse.urlencode(dict(data, **{self.token[0]: self.token[1]})).encode()
        request = urllib.request.Request(self.base + path, data=body, headers={'X-Requested-With': 'XMLHttpRequest'})
        try:
            response = self.client.open(request)
        except urllib.error.HTTPError as error:
            response = error
        text = response.read().decode()
        assert response.code == expected, (path, response.code, text[:1000])
        if not as_json:
            return text
        result = json.loads(text)
        if result.get('csrfHash'):
            self.token = (result['csrfName'], result['csrfHash'])
        assert result.get('success') is (expected == 200), (path, result)
        return result

    def login(self, username, password):
        html = self.get('/auth/login-page')
        match = re.search(r'<input[^>]*name="(csrf_[^"]+)"[^>]*value="([^"]+)"', html)
        self.token = (match[1], match[2])
        self.post('/auth/login-page', {'login': username, 'password': password})


def run_timeline_checks(base, admin_client, admin_token, env, sql):
    for name in ('reader_a', 'reader_b'):
        sql(f"INSERT INTO users(username,password_hash,role_id) SELECT '{name}',password_hash,(SELECT id FROM roles WHERE code='USER') FROM users WHERE username='deployadmin'")
    owner, other = Browser(base), Browser(base)
    for client, name in ((owner, 'reader_a'), (other, 'reader_b')):
        client.login(name, env['ADMIN_PASSWORD'])
    owner.get('/creator/import-json?preset=genesis')
    sample = (Path(__file__).parents[1] / 'app/Data/genesis-50.json').read_text(encoding='utf-8')
    before = sql('SELECT count(*) FROM cards').strip()
    result = owner.post('/creator/import-json', {'json': sample, 'preview': '1'})
    assert len(result['cards']) == 50
    assert sql('SELECT count(*) FROM cards').strip() == before
    result = owner.post('/creator/import-json', {'json': sample})
    game = int(result['editor_url'].rsplit('/', 1)[1])
    assert sql(f"SELECT status FROM game_templates WHERE id={game}").strip() == 'DRAFT'
    assert sql(f'SELECT count(*) FROM cards WHERE game_template_id={game}').strip() == '50'
    ids = [int(v) for v in sql(f'SELECT id FROM cards WHERE game_template_id={game} ORDER BY editor_position').splitlines()]
    owner.get(f'/creator/edit/{game}')
    owner.post('/creator/import-json', {'game_id': game, 'json': '{'}, 422)
    owner.post('/creator/select-cards', {'game_id': game, 'ids': json.dumps(ids[:5]), 'enabled':'0'})
    exported = json.loads(owner.get(f'/creator/export-json/{game}'))
    assert len(exported['cards']) == 50 and sum(not c['is_enabled'] for c in exported['cards']) == 5
    other.post('/creator/import-json', {'game_id': game, 'json': sample}, 404)
    other.post('/creator/select-cards', {'game_id': game, 'ids': json.dumps(ids[:1]), 'enabled':'1'}, 404)
    other.get(f'/creator/export-json/{game}', 404)
    other.post('/creator/save-card', {'card_id': ids[0], 'title': 'Unauthorized'}, 403)
    before_count = sql(f'SELECT count(*) FROM cards WHERE game_template_id={game}').strip()
    broken = {'title':'Broken', 'cards':[{'title':'Valid','sort_order':1},{'title':'','sort_order':2}]}
    owner.post('/creator/import-json', {'game_id':game, 'json':json.dumps(broken)}, 422)
    assert sql(f'SELECT count(*) FROM cards WHERE game_template_id={game}').strip() == before_count
    separate = {'title':'Other book','cards':[{'title':'First event','sort_order':1}]}
    result = other.post('/creator/import-json', {'json':json.dumps(separate)})
    other_game = int(result['editor_url'].rsplit('/',1)[1])
    other_id = int(sql(f'SELECT id FROM cards WHERE game_template_id={other_game}').strip())
    owner.post('/creator/select-cards', {'game_id':game,'ids':json.dumps([ids[0],other_id]),'enabled':'1'}, 403)
    assert sql(f'SELECT is_enabled FROM cards WHERE id={ids[0]}').strip() == 'f'
    after_preview = other.post('/creator/import-json', {'game_id':other_game,'json':json.dumps(separate),'order_mode':'after','preview':'1'})
    assert after_preview['cards'][0]['sort_order'] == '2'
    other.post('/creator/import-json', {'game_id':other_game,'json':json.dumps(separate),'order_mode':'after'})
    assert [c['sort_order'] for c in json.loads(other.get(f'/creator/export-json/{other_game}'))['cards']] == ['1.000000','2.000000']
    append = {'title':'Исход', 'book':'Исход', 'cards':[{'title':'Призвание Моисея','sort_order':1001,'reference':'Исход 3:1–12'}]}
    owner.post('/creator/import-json', {'game_id':game,'json':json.dumps(append)})
    assert sql(f'SELECT count(*) FROM cards WHERE game_template_id={game}').strip() == '51'
    owner.post('/creator/save-card', {'card_id': ids[5], 'title':'Сохранённая карточка','sort_order':'6','difficulty':'NORMAL'})
    assert sql(f'SELECT title FROM cards WHERE id={ids[5]}').strip() == 'Сохранённая карточка'
    blank = owner.post('/creator/add-card', {'game_id':game})['card']['id']
    owner.post('/creator/select-cards', {'game_id':game,'ids':json.dumps([int(blank)]),'enabled':'0'})
    admin = Browser(base, admin_client, (admin_token['csrfName'], admin_token['csrfHash']))
    admin.post('/admin/set-game-status', {'game_id':game,'status':'PRODUCTION'}, as_json=False)
    assert sql(f'SELECT status FROM game_templates WHERE id={game}').strip() == 'PRODUCTION'
    owner.post('/rooms/create', {'game_id':game,'max_players':4,'cards_per_player':3,'game_mode':'NORMAL'})
    room = int(sql(f'SELECT id FROM game_rooms WHERE game_template_id={game}').strip())
    code = sql(f'SELECT code FROM game_rooms WHERE id={room}').strip()
    other.post('/rooms/join', {'code':code})
    owner.post('/rooms/start', {'room_id':room})
    assert sql(f'SELECT count(*) FROM game_room_cards WHERE room_id={room}').strip() == '46'
    excluded = ','.join(map(str,ids[:5] + [int(blank)]))
    assert sql(f'SELECT count(*) FROM game_room_cards WHERE room_id={room} AND source_card_id IN ({excluded})').strip() == '0'
    owner.post('/creator/select-cards', {'game_id':game,'ids':json.dumps(ids),'enabled':'0'})
    assert sql(f'SELECT count(*) FROM game_room_cards WHERE room_id={room}').strip() == '46'
    print('PASS: import/preview/append/export, ownership, card edits, publication and selected room snapshot')
