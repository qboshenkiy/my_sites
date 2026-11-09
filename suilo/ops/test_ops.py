import unittest
from unittest.mock import patch

from bot import respond
from install import BEGIN, END, HOST, route


class GuardRouteTest(unittest.TestCase):
    existing = 'example.com {\n    import /data/guard-sensitive.caddy # Guard sensitive files\n    reverse_proxy example-web:80\n}\n'

    def test_keeps_guard_and_routes_idempotently(self):
        result = route(self.existing)
        self.assertTrue(result.startswith(self.existing))
        self.assertIn('reverse_proxy suilo-web:8080', result)
        self.assertEqual(result.count('import /data/guard-sensitive.caddy'), 2)
        self.assertEqual(result, route(result))

    def test_rejects_unguarded_and_conflicting_routes(self):
        for original in ('example.com {}', self.existing + f'{HOST} {{}}', self.existing + BEGIN,
                         self.existing + END + '\n' + END):
            with self.subTest(original=original), self.assertRaises(ValueError):
                route(original)


class BotTest(unittest.TestCase):
    def test_private_start_opens_mini_app_and_throttles_replies(self):
        url = f'https://{HOST}/'
        private = {'message': {'text': '/start', 'chat': {'id': 17, 'type': 'private'}}}
        public = {'message': {'text': '/start', 'chat': {'id': -99, 'type': 'group'}}}
        sent = {}
        with patch('bot.api') as api:
            respond('placeholder', url, public, sent)
            respond('placeholder', url, private, sent)
            respond('placeholder', url, private, sent)
        api.assert_called_once()
        keyboard = api.call_args.kwargs['reply_markup']['inline_keyboard']
        self.assertEqual(keyboard[0][0]['web_app']['url'], url)


if __name__ == '__main__':
    unittest.main()
