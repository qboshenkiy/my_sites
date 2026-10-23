"""Opaque WebSocket relay. Never receives the E2E pairing secret."""
import asyncio
import hmac
import os
import re
import sqlite3
import time
from aiohttp import web, WSMsgType

DATA = os.environ.get('DATA_DIR', '/data')
os.makedirs(DATA, exist_ok=True)
db = sqlite3.connect(os.path.join(DATA, 'rooms.sqlite'))
db.execute('CREATE TABLE IF NOT EXISTS rooms (room TEXT PRIMARY KEY, token TEXT NOT NULL)')
peers = {}
locks = {}
attempts = {}

async def health(request):
    return web.json_response({'service': 'Vano Remote', 'version': 1})

async def socket(request):
    room, role = request.match_info['room'], request.match_info['role']
    if not re.fullmatch(r'[a-f0-9]{32}', room) or role not in ('windows', 'android'):
        raise web.HTTPBadRequest()
    token = request.headers.get('Authorization', '').removeprefix('Bearer ')
    if not re.fullmatch(r'[a-f0-9]{64}', token):
        raise web.HTTPUnauthorized()
    # Registration is limited per TCP peer; reverse proxy IP headers are not trusted.
    now = time.monotonic()
    for addr in list(attempts):
        if now - attempts[addr][0] > 60:
            attempts.pop(addr, None)
    addr = request.remote or ''
    start, count = attempts.get(addr, (now, 0))
    if count >= 60:
        raise web.HTTPTooManyRequests()
    attempts[addr] = (start, count + 1)
    row = db.execute('SELECT token FROM rooms WHERE room=?', (room,)).fetchone()
    if row is None:
        if role != 'windows':
            raise web.HTTPUnauthorized(text='Start the Windows app first')
        db.execute('INSERT INTO rooms VALUES (?, ?)', (room, token))
        db.commit()
    elif not hmac.compare_digest(row[0], token):
        raise web.HTTPUnauthorized()
    ws = web.WebSocketResponse(heartbeat=20, max_msg_size=4_000_000)
    async with locks.setdefault(room, asyncio.Lock()):
        group = peers.setdefault(room, {})
        if role in group:
            raise web.HTTPConflict(text='Device already connected')
        await ws.prepare(request)
        group[role] = ws
        if len(group) == 2:
            for peer in group.values():
                await peer.send_json({'event': 'paired'})
    try:
        async for message in ws:
            if message.type == WSMsgType.BINARY:
                other = peers.get(room, {}).get('android' if role == 'windows' else 'windows')
                if other and not other.closed:
                    await other.send_bytes(message.data)
            elif message.type in (WSMsgType.ERROR, WSMsgType.CLOSE):
                break
    finally:
        remaining = []
        async with locks[room]:
            group = peers.get(room, {})
            if group.get(role) is ws:
                group.pop(role, None)
                # End both transports, so a returning Android must authenticate again.
                remaining = list(group.values())
                if not group:
                    peers.pop(room, None)
                    locks.pop(room, None)
        for other in remaining:
            await other.close(code=1000, message=b'Peer disconnected')
    return ws

app = web.Application(client_max_size=4_000_000)
app.router.add_get('/health', health)
app.router.add_get('/ws/{room}/{role}', socket)
if __name__ == '__main__':
    web.run_app(app, host='0.0.0.0', port=8080, access_log=None)
