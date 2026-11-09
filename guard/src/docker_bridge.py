"""Local, allowlisted operations for the Guard web container."""
import json
import os
from pathlib import Path
import socket
import socketserver
import time

SOCKET = '/run/guard-docker/api.sock'
MAX_REQUEST = 16 * 1024
MAX_RESPONSE = 12 * 1024 * 1024


def enabled():
    return 'GUARD_DOCKER_BRIDGE' in os.environ


def request(operation, **arguments):
    payload = json.dumps({'operation': operation, **arguments}, ensure_ascii=False).encode() + b'\n'
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as client:
        client.settimeout(65)
        client.connect(os.environ['GUARD_DOCKER_BRIDGE'])
        client.sendall(payload)
        with client.makefile('rb') as stream:
            response = stream.readline(MAX_RESPONSE + 1)
    if len(response) > MAX_RESPONSE:
        raise ValueError('Журнал слишком большой. Уменьшите период.')
    if not response:
        raise OSError('Служба диагностики Guard недоступна')
    result = json.loads(response)
    if not result['ok']:
        raise ValueError(result['error'])
    return result['result']


def start_time(value):
    if type(value) not in (int, float):
        raise ValueError('Некорректный период')
    if not time.time() - 8 * 86400 <= value <= time.time() + 60:
        raise ValueError('Некорректный период')
    return value


def dispatch(message):
    # Only the host service reaches this code. No Docker paths, commands,
    # container names or environment lookups are accepted from the web app.
    import monitor

    if not isinstance(message, dict):
        raise ValueError('Некорректный запрос')
    operation = message.get('operation')
    if operation == 'proxy_logs':
        tail = message.get('tail')
        if type(tail) is not int or not 1 <= tail <= 10000:
            raise ValueError('Некорректный размер журнала')
        return monitor.proxy_logs(start_time(message.get('since')), tail)
    if operation == 'ssh':
        return monitor.ssh(start_time(message.get('since')))
    if operation == 'bots':
        return monitor.bots()
    if operation == 'installed_bot_ids':
        return sorted(monitor.installed_bot_ids())
    bot = message.get('bot')
    if not isinstance(bot, str) or bot not in monitor.BOTS:
        raise ValueError('Неизвестная операция или бот')
    if operation == 'inspect_bot':
        return monitor.inspect_bot(bot)
    if operation == 'bot_control':
        return monitor.bot_control(bot, message.get('action'))
    if operation == 'bot_action':
        action = message.get('action')
        data = message.get('data')
        if not isinstance(data, dict):
            raise ValueError('Некорректные параметры бота')
        if action == 'people':
            return monitor.bot_action(bot, action)
        if action == 'activity':
            cursor = data.get('after')
            if cursor is not None and (type(cursor) is not int or not 0 <= cursor < 2**63):
                raise ValueError('Некорректный курсор')
            return monitor.bot_action(bot, action, {'after': cursor})
        if action in ('history', 'block', 'unblock', 'send'):
            person = data.get('person')
            if not isinstance(person, str) or not person.isascii() or not person.isdecimal() or not 1 <= len(person) <= 20:
                raise ValueError('Выберите участника')
            arguments = {'person': person}
            if action == 'send':
                text = data.get('text')
                if not isinstance(text, str) or not text.strip() or len(text) > 3500:
                    raise ValueError('Введите сообщение до 3500 символов')
                arguments['text'] = text
            return monitor.bot_action(bot, action, arguments)
    raise ValueError('Неизвестная операция')


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(5)
        try:
            line = self.rfile.readline(MAX_REQUEST + 1)
            if len(line) > MAX_REQUEST or not line.endswith(b'\n'):
                raise ValueError('Некорректный размер запроса')
            result = {'ok': True, 'result': dispatch(json.loads(line))}
            response = json.dumps(result, ensure_ascii=False).encode() + b'\n'
            if len(response) > MAX_RESPONSE:
                raise ValueError('Журнал слишком большой. Уменьшите период.')
        except ValueError as error:
            response = json.dumps({'ok': False, 'error': str(error)[:300]}).encode() + b'\n'
        except (OSError, TimeoutError):
            response = b'{"ok":false,"error":"Guard host service unavailable"}\n'
        try:
            self.wfile.write(response)
        except OSError:
            pass


class Server(socketserver.ThreadingUnixStreamServer):
    daemon_threads = True


def serve():
    if enabled():
        raise SystemExit('The bridge must run on the Docker host')
    path = Path(SOCKET)
    path.unlink(missing_ok=True)
    with Server(str(path), Handler) as server:
        path.chmod(0o600)
        server.serve_forever()


if __name__ == '__main__':
    serve()
