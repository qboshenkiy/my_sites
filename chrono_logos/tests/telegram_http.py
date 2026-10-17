"""Signed Telegram requests against the disposable PostgreSQL/HTTP deployment."""
import hashlib
import hmac
import http.cookiejar
import json
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from timeline_http import Browser


def run_telegram_checks(base, env, sql):
    token = env['TELEGRAM_BOT_TOKEN']

    def proof(identity=10101, age=0, signing_token=token):
        values = {'auth_date': str(int(time.time()) - age), 'query_id': 'fixture',
                  'user': json.dumps({'id': identity, 'first_name': '<script>fake</script>', 'role': 'ADMIN'}, separators=(',', ':'))}
        secret = hmac.new(b'WebAppData', signing_token.encode(), hashlib.sha256).digest()
        values['hash'] = hmac.new(secret, '\n'.join(k + '=' + values[k] for k in sorted(values)).encode(), hashlib.sha256).hexdigest()
        return urllib.parse.urlencode(values)

    def visitor():
        client = Browser(base)
        html = client.get('/telegram/app')
        match = re.search(r'<input[^>]*name="(csrf_[^"]+)"[^>]*value="([^"]+)"', html)
        assert match
        client.token = (match[1], match[2])
        return client

    client = visitor()
    before = sql('SELECT count(*) FROM users').strip()
    for invalid in ('', proof(age=3601), proof(age=-60), proof(signing_token='other-bot-token'), proof() + '&auth_date=0', proof().replace('10101', '20202')):
        client.post('/telegram/login', {'initData': invalid, 'create': '1'}, expected=401)
    assert sql('SELECT count(*) FROM users').strip() == before
    # A signed new identity still requires an explicit registration choice.
    assert client.post('/telegram/login', {'initData': proof()})['needsRegistration']
    assert sql('SELECT count(*) FROM users').strip() == before
    client.post('/telegram/login', {'initData': proof(), 'create': '1'})
    assert sql("SELECT r.code FROM users u JOIN roles r ON r.id=u.role_id WHERE telegram_id='10101'").strip() == 'USER'
    assert client.get('/rooms')
    client.post('/telegram/configure', {}, expected=403)
    count = sql('SELECT count(*) FROM users').strip()
    second = visitor()
    second.post('/telegram/login', {'initData': proof(), 'create': '1'})
    assert sql('SELECT count(*) FROM users').strip() == count
    second.post('/telegram/unlink', {}, expected=422)
    second.post('/account/change-password', {'new_password': 'native-test-password', 'password_confirm': 'native-test-password'})
    password_user = Browser(base)
    password_user.login('tg_10101', 'native-test-password')
    assert sql("SELECT telegram_only FROM users WHERE telegram_id='10101'").strip() == 'f'
    # An established password must still be required after the first setup.
    second.post('/account/change-password', {'new_password': 'stolen-new-password', 'password_confirm': 'stolen-new-password'}, expected=422)
    print('PASS: signed Mini App login, expiry, wrong bot, tampering, explicit creation and server-owned role')

    sql("INSERT INTO users(username,password_hash,role_id) SELECT 'telegram_linker',password_hash,(SELECT id FROM roles WHERE code='USER') FROM users WHERE username='deployadmin'")
    linker = Browser(base)
    linker.login('telegram_linker', env['ADMIN_PASSWORD'])
    linker.post('/telegram/link', {'initData': proof(20202)})
    assert sql("SELECT telegram_id FROM users WHERE username='telegram_linker'").strip() == '20202'
    second.post('/telegram/link', {'initData': proof(20202)}, expected=409)
    returning = visitor()
    returning.post('/telegram/login', {'initData': proof(20202)})
    assert 'telegram_linker' in returning.get('/account/settings')
    returning.post('/telegram/unlink', {})
    assert sql("SELECT telegram_id IS NULL FROM users WHERE username='telegram_linker'").strip() == 't'
    linker.login('telegram_linker', env['ADMIN_PASSWORD'])
    print('PASS: explicit existing-account linking, collision protection, unlink and password login')

    def hook(headers, payload):
        req = urllib.request.Request(base + '/telegram/webhook', data=json.dumps(payload).encode(), headers=dict({'Content-Type': 'application/json'}, **headers))
        try: response = urllib.request.urlopen(req)
        except urllib.error.HTTPError as error: response = error
        return response.code
    assert hook({}, {}) == 403
    secret = hmac.new(token.encode(), b'chrono-logos-webhook', hashlib.sha256).hexdigest()
    assert hook({'X-Telegram-Bot-Api-Secret-Token': secret}, {'update_id': 1, 'message': {'text': 'ignore'}}) == 200
    # Login remains CSRF protected, although the signed webhook has an exact exception.
    request = urllib.request.Request(base + '/telegram/login', data=urllib.parse.urlencode({'initData': proof()}).encode(), headers={'X-Requested-With': 'XMLHttpRequest'})
    try: response = urllib.request.urlopen(request)
    except urllib.error.HTTPError as error: response = error
    assert response.code == 403
    print('PASS: webhook secret header and CSRF boundary')
