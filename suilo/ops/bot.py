"""Dedicated long-polling Telegram launcher. Credentials are read at startup."""
import json
import os
import re
import time
from urllib.error import HTTPError
from urllib.parse import urlsplit
from urllib.request import Request, urlopen


class TelegramError(Exception):
    def __init__(self, status, delay=0):
        self.status = status
        self.delay = delay


def api(token, method, **payload):
    request = Request(
        f'https://api.telegram.org/bot{token}/{method}',
        json.dumps(payload).encode(),
        {'Content-Type': 'application/json'},
    )
    try:
        with urlopen(request, timeout=40) as response:
            data = json.load(response)
    except HTTPError as error:
        with error:
            try:
                delay = json.load(error).get('parameters', {}).get('retry_after', 0)
            except (ValueError, OSError):
                delay = 0
        raise TelegramError(error.code, delay) from None
    if not data.get('ok'):
        raise TelegramError(data.get('error_code', 500))
    return data['result']


def respond(token, app_url, update, last_reply):
    message = update.get('message', {})
    chat = message.get('chat', {})
    text = message.get('text', '')
    if chat.get('type') != 'private' or not re.match(r'^/(start|app|help)(?:@[a-zA-Z0-9_]+)?(?:\s|$)', text):
        return
    chat_id = chat['id']
    now = time.monotonic()
    if now - last_reply.get(chat_id, -10) < 5:
        return
    if len(last_reply) >= 4096:
        last_reply.clear()
    api(token, 'sendMessage', chat_id=chat_id,
        text='Салам! Учите кыргызский по 5 слов в день. Откройте «Сүйлө»: вход через Telegram, слова и ваш прогресс.',
        reply_markup={'inline_keyboard': [[{'text': 'Открыть Сүйлө', 'web_app': {'url': app_url}}]]})
    last_reply[chat_id] = now


def run(token, app_url, username):
    offset = 0
    last_reply = {}
    configured = False
    delay = 2
    while True:
        try:
            if not configured:
                identity = api(token, 'getMe')
                if identity.get('username', '').casefold() != username.casefold():
                    print('Токен принадлежит другому боту. Проверьте TELEGRAM_BOT_USERNAME в GitDeck.')
                    time.sleep(3600)
                    continue
                if api(token, 'getWebhookInfo').get('url'):
                    print('У этого бота уже настроен webhook. Используйте отдельного бота для «Сүйлө».')
                    time.sleep(120)
                    continue
                api(token, 'setChatMenuButton', menu_button={'type': 'web_app', 'text': 'Сүйлө', 'web_app': {'url': app_url}})
                print('Меню Mini App настроено, бот ожидает команды.')
                configured = True
            for update in api(token, 'getUpdates', offset=offset, timeout=25, allowed_updates=['message']):
                try:
                    respond(token, app_url, update, last_reply)
                except TelegramError as error:
                    if error.status not in (400, 403):
                        raise
                offset = update['update_id'] + 1
            delay = 2
        except TelegramError as error:
            print(f'Ошибка Telegram HTTP {error.status}.')
            time.sleep(max(delay, min(600, error.delay), 120 if error.status in (401, 404, 409) else 0))
            delay = min(60, delay * 2)
        except (OSError, ValueError):
            print('Telegram временно недоступен.')
            time.sleep(delay)
            delay = min(60, delay * 2)


def main():
    token = os.environ.get('TELEGRAM_BOT_TOKEN', '')
    app_url = os.environ.get('APP_URL', '')
    target = urlsplit(app_url)
    if not re.fullmatch(r'\d+:[A-Za-z0-9_-]+', token) or target.scheme != 'https' or not target.hostname or target.username:
        print('Ожидание настройки TELEGRAM_BOT_TOKEN и HTTPS APP_URL в GitDeck.')
        while True:
            time.sleep(3600)
    run(token, app_url, os.environ.get('TELEGRAM_BOT_USERNAME', 'duolingo_by_vano_bot').lstrip('@'))


if __name__ == '__main__':
    main()
