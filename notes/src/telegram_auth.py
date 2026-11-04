"""Validate Telegram Mini App initData; no unsigned Telegram identifiers are trusted."""
import hashlib,hmac,json,time,re
from urllib.parse import parse_qsl

def validate(raw,token,now=None):
    if not token or not isinstance(raw,str) or len(raw)>16384:raise ValueError('Откройте приложение через подключённого Telegram-бота')
    pairs=parse_qsl(raw,keep_blank_values=True)
    if len({k for k,v in pairs})!=len(pairs):raise ValueError('Некорректные данные Telegram')
    fields=dict(pairs);signature=fields.pop('hash','')
    if not re.fullmatch('[a-f0-9]{64}',signature):raise ValueError('Некорректная подпись Telegram')
    secret=hmac.new(b'WebAppData',token.encode(),hashlib.sha256).digest()
    expected=hmac.new(secret,'\n'.join(f'{k}={v}' for k,v in sorted(fields.items())).encode(),hashlib.sha256).hexdigest()
    if not hmac.compare_digest(signature,expected):raise ValueError('Некорректная подпись Telegram')
    now=time.time() if now is None else now
    try:
        stamp=int(fields.get('auth_date','0'));user=json.loads(fields.get('user','{}'));uid=user['id']
        if isinstance(uid,bool) or not isinstance(uid,int) or uid<=0 or uid>2**52:raise ValueError()
    except (ValueError,TypeError,KeyError):raise ValueError('Некорректный пользователь Telegram')
    if not -30<=now-stamp<=3600:raise ValueError('Повторно откройте Mini App из бота')
    return str(uid)
