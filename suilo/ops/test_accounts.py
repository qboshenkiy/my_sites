import hashlib
import hmac
import http.client
import json
from pathlib import Path
import tempfile
import threading
import time
import unittest
from urllib.parse import urlencode

from server import COOKIE, Store, clean_progress, make_server, verify_telegram

TOKEN = '123456:fake-test-token'
ORIGIN = 'https://suilo.example.test'


def signed(user_id=17, stamp=None, token=TOKEN):
    fields = {'auth_date': str(int(time.time()) if stamp is None else stamp), 'query_id': 'test',
              'user': json.dumps({'id': user_id, 'first_name': 'Test', 'username': 'student'}, separators=(',', ':'))}
    secret = hmac.new(b'WebAppData', token.encode(), hashlib.sha256).digest()
    fields['hash'] = hmac.new(secret, '\n'.join(f'{k}={v}' for k, v in sorted(fields.items())).encode(), hashlib.sha256).hexdigest()
    return urlencode(fields)


class SignatureTests(unittest.TestCase):
    def test_valid_signature_and_rejects_tampering_wrong_bot_expiry_and_duplicates(self):
        raw = signed(stamp=10000)
        self.assertEqual(verify_telegram(raw, TOKEN, 10000)['id'], 17)
        for bad in (raw.replace('10000', '10001'), signed(stamp=6000), signed(stamp=10031), raw + '&query_id=other', '', signed(stamp=10000, token='wrong')):
            with self.subTest(bad=bad[:25]), self.assertRaises((ValueError, TypeError)):
                verify_telegram(bad, TOKEN, 10000)

    def test_invalid_user_cannot_register(self):
        for user in (-1, 0, True, '17', 2**53):
            with self.subTest(user=user), self.assertRaises(ValueError):
                verify_telegram(signed(user), TOKEN)


class AccountTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.server = make_server(('127.0.0.1', 0), Path(self.tmp.name) / 'learning.sqlite', TOKEN, ORIGIN)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown(); self.server.server_close(); self.thread.join(); self.tmp.cleanup()

    def request(self, method, path, body=None, cookie='', origin=ORIGIN):
        connection = http.client.HTTPConnection(*self.server.server_address, timeout=3)
        headers = {'Origin': origin, 'Content-Type': 'application/json', 'X-Suilo-Request': '1', 'Cookie': cookie}
        connection.request(method, path, json.dumps(body) if body is not None else None, headers)
        response = connection.getresponse()
        result = response.status, json.loads(response.read()), response.getheader('Set-Cookie')
        connection.close()
        return result

    def login(self, user=17):
        status, data, cookie = self.request('POST', '/api/auth/telegram', {'initData': signed(user)})
        self.assertEqual(status, 200); self.assertEqual(data['user']['id'], user)
        for flag in ('HttpOnly', 'Secure', 'SameSite=Lax', 'Path=/'):
            self.assertIn(flag, cookie)
        self.session=data['session']
        return cookie.split(';')[0]

    def test_signed_registration_and_account_cookie_survive_new_connections(self):
        cookie = self.login()
        status, data, _ = self.request('GET', '/api/me', cookie=cookie)
        self.assertEqual(status, 200); self.assertEqual(data['user']['id'], 17)
        self.assertEqual(self.request('GET', '/api/me')[0], 401)
        self.assertEqual(self.request('GET', '/api/progress', cookie=COOKIE + '=invented')[0], 401)

    def test_bearer_session_supports_webviews_without_cookies_and_expires(self):
        self.login()
        connection=http.client.HTTPConnection(*self.server.server_address,timeout=3)
        connection.request('GET','/api/me',headers={'Authorization':'Bearer '+self.session})
        response=connection.getresponse()
        self.assertEqual(response.status,200);response.read();connection.close()
        with self.server.store.connect() as db:
            db.execute('UPDATE sessions SET expires=0')
        self.assertIsNone(self.server.store.user(self.session))

    def test_accounts_are_isolated_and_revisions_prevent_overwrite(self):
        a, b = self.login(17), self.login(18)
        progress = {'cards': {'окуу': {'box': 1, 'due': 123, 'at': 100}}}
        self.assertEqual(self.request('PUT', '/api/progress', {'revision': 0, 'progress': progress}, a)[0], 200)
        self.assertEqual(self.request('PUT', '/api/progress', {'revision': 0, 'progress': {}}, a)[0], 409)
        _, data, _ = self.request('GET', '/api/progress', cookie=b)
        self.assertEqual(data, {'revision': 0, 'progress': None})
        _, data, _ = self.request('GET', '/api/progress', cookie=a)
        self.assertEqual(data['progress']['cards'], progress['cards'])
        self.assertEqual(self.request('PUT', '/api/progress', {'revision': 1, 'progress': progress}, a)[0], 200)
        reopened = Store(Path(self.tmp.name) / 'learning.sqlite')
        self.assertEqual(reopened.get(17)['revision'], 2)

    def test_csrf_tampered_login_and_invalid_documents_do_not_mutate(self):
        cookie = self.login()
        self.assertEqual(self.request('POST', '/api/auth/telegram', {'initData': signed()}, origin='https://evil.example')[0], 403)
        self.assertEqual(self.request('POST', '/api/auth/telegram', {'initData': 'user=forged'})[0], 401)
        self.assertEqual(self.request('PUT', '/api/progress', {'revision': 0, 'progress': {'cards': []}}, cookie)[0], 400)
        self.assertEqual(self.request('PUT', '/api/progress', {'revision': -1, 'progress': {}}, cookie)[0], 400)
        self.assertEqual(self.server.store.get(17)['revision'], 0)

    def test_device_drafts_and_active_queue_are_not_shared(self):
        result = clean_progress({'draft': {'id': 'private'}, 'vocabulary': {'cards': {}, 'activity': {}, 'dailyNew': 5, 'topic': '', 'settingsAt': 1, 'session': {'cursor': 3}}})
        self.assertNotIn('draft', result)
        self.assertNotIn('session', result['vocabulary'])
        self.assertEqual(result['vocabulary']['dailyNew'], 5)


if __name__ == '__main__':
    unittest.main()
