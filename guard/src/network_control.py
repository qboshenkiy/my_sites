import json
import socket
from firewall_agent import canonical


def request(action='status',**data):
    with socket.socket(socket.AF_UNIX,socket.SOCK_STREAM) as client:
        client.settimeout(12)
        try:
            client.connect('/run/guard-firewall/api.sock');client.sendall(json.dumps({'action':action,**data}).encode()+b'\n')
            with client.makefile('rb') as source:result=json.loads(source.readline(2097153))
        except (OSError,ValueError):raise ValueError('Служба сетевой защиты недоступна. Проверьте её установку и запуск.') from None
    if not result.get('ok'):raise ValueError(result.get('error','Не удалось применить блокировку'))
    return result['result']
