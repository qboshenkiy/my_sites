"""Private Telegram long polling, sharing the web database; never logs tokens or messages."""
import json,os,time,urllib.request,urllib.error
from datetime import date
from app import database
from core import operation,overview
TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','')
def call(method,data):
    req=urllib.request.Request('https://api.telegram.org/bot'+TOKEN+'/'+method,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(req,timeout=40) as r:result=json.load(r)
    if not result.get('ok'):raise ValueError('Telegram API error')
    return result['result']
def respond(chat,text):call('sendMessage',{'chat_id':chat,'text':text})
def handle(update):
    m=update.get('message',{});chat=m.get('chat',{})
    if chat.get('type')!='private':return
    cid=str(chat['id']);text=m.get('text','').strip();uid=update['update_id']
    with database() as db:
        if db.execute('SELECT 1 FROM bot_updates WHERE id=?',(uid,)).fetchone():return
        # Pairing is one-time and possible only with a code generated in an authenticated web session.
        if text.startswith('/start '):
            code=text.split(maxsplit=1)[1]
            db.execute('BEGIN IMMEDIATE')
            match=db.execute('SELECT * FROM links WHERE code=? AND expires>?',(code,time.time())).fetchone()
            if not match:reply='Код недействителен. Получите новый в Копилке → Настройки.'
            else:
                db.execute('DELETE FROM telegram');db.execute('INSERT INTO telegram VALUES(?)',(cid,));db.execute('DELETE FROM links');reply='Копилка подключена!\n/expense 250 Продукты\n/income 50000 Зарплата\n/balance — итоги\n/goals — цели\nОткрыть: https://finance.vano.sbena.net'
        elif not db.execute('SELECT 1 FROM telegram WHERE chat=?',(cid,)).fetchone():reply='Подключите личный чат через Настройки на https://finance.vano.sbena.net'
        elif text.startswith(('/expense ','/income ')):
            parts=text.split(maxsplit=2);kind='expense' if parts[0]=='/expense' else 'income'
            try:
                wid=1;note=parts[2] if len(parts)>2 else ''
                if note.startswith('@'):
                    selected,*rest=note.split(maxsplit=1);wid=selected[1:];note=rest[0] if rest else ''
                operation(db,{'kind':kind,'amount':parts[1],'category':'Другое' if kind=='expense' else 'Доход','note':note,'wallet_id':wid},'telegram',str(uid));reply='Операция сохранена. Она уже доступна в приложении.'
            except ValueError as e:reply=str(e)
        elif text in ('/balance','/goals','/tips','/wallets'):
            result=overview(db,date.today().strftime('%Y-%m'));currency=result['settings'].get('currency','KGS')
            if text=='/balance':reply=f'Баланс: {result["balance"]/100:,.2f} {currency}\nДоходы месяца: {result["income"]/100:,.2f}\nРасходы месяца: {result["expense"]/100:,.2f}'
            elif text=='/wallets':reply='\n'.join(f'@{w["id"]} · {w["name"]}: {w["balance"]/100:,.2f} {currency}' for w in result['wallets'])+'\n\nПример: /expense 250 @1 Продукты. Без @номера используется основной кошелёк.'
            elif text=='/tips':reply='\n\n'.join(result['tips']) or 'Добавьте операции для анализа.'
            else:reply='\n'.join(f'{g["name"]}: {g["saved"]/100:,.2f} / {g["target"]/100:,.2f} {currency}' for g in result['goals']) or 'Пока нет целей. Создайте их в приложении.'
        else:reply='/expense 250 Продукты — расход\n/income 50000 Зарплата — доход\n/balance — баланс\n/goals — цели\n/wallets — кошельки\n/tips — рекомендации\nhttps://finance.vano.sbena.net'
        db.execute('INSERT OR IGNORE INTO bot_updates VALUES(?)',(uid,));db.execute('DELETE FROM bot_updates WHERE id<?',(uid-10000,))
    respond(cid,reply)
def main():
    offset=0
    while True:
        if not TOKEN:time.sleep(30);continue
        try:
            for update in call('getUpdates',{'offset':offset,'timeout':25,'allowed_updates':['message']}):
                handle(update);offset=update['update_id']+1
        except (OSError,ValueError,KeyError):
            print('Telegram temporarily unavailable; retrying.',flush=True);time.sleep(5)
if __name__=='__main__':main()
