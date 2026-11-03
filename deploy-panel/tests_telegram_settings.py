import json,unittest,urllib.error
from unittest.mock import patch,MagicMock
import app
TOKEN='123456789:fixture-credential-xyz9876'
class TelegramSettings(unittest.TestCase):
 def test_hint_identifies_key_without_returning_it(self):
  hint=app.telegram_token_hint(TOKEN)
  self.assertIn('123456789',hint);self.assertTrue(hint.endswith('9876'));self.assertNotIn('fixture',hint)
 def test_success_uses_fixed_tls_endpoint(self):
  response=MagicMock();response.__enter__.return_value=response;response.read.return_value=json.dumps({'ok':True,'result':{'is_bot':True,'username':'fixture_bot'}}).encode()
  with patch('urllib.request.urlopen',return_value=response) as request:
   result=app.check_telegram_token(TOKEN)
  self.assertTrue(result['ok']);self.assertEqual(result['username'],'fixture_bot')
  self.assertNotIn(TOKEN,json.dumps(result));self.assertEqual(request.call_args.kwargs['timeout'],10)
 def test_network_error_does_not_leak_url_or_mark_key_invalid(self):
  with patch('urllib.request.urlopen',side_effect=RuntimeError('https://api.telegram.org/bot'+TOKEN+'/getMe')):
   result=app.check_telegram_token(TOKEN)
  self.assertFalse(result['ok']);self.assertNotIn(TOKEN,json.dumps(result));self.assertIn('сохранить',result['message'])
 def test_502_is_not_bad_token(self):
  with patch('urllib.request.urlopen',side_effect=urllib.error.HTTPError('redacted',502,'Bad Gateway',{},None)):
   result=app.check_telegram_token(TOKEN)
  self.assertEqual(result['http'],502);self.assertIn('не подтверждает',result['message'])
if __name__=='__main__':unittest.main()
