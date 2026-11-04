"""Private note capture with buttons and Mini App. Token and note text are never logged."""
import json,os,time,secrets,urllib.request
from app import database
TOKEN=os.getenv('TELEGRAM_BOT_TOKEN','');URL='https://notes.vano.sbena.net/'
HOME={'keyboard':[[{'text':'📝 Новая заметка'},{'text':'📚 Мои заметки'}],[{'text':'🔍 Найти'},{'text':'⭐ Закреплённые'}],[{'text':'🌐 Открыть приложение'}]],'resize_keyboard':True,'is_persistent':True,'input_field_placeholder':'Напиши текст — сохраню как заметку'}
def call(method,data):
    r=urllib.request.Request('https://api.telegram.org/bot'+TOKEN+'/'+method,data=json.dumps(data).encode(),headers={'Content-Type':'application/json'})
    with urllib.request.urlopen(r,timeout=40) as response:value=json.load(response)
    if not value.get('ok'):raise ValueError('Telegram API unavailable')
    return value['result']
def send(chat,text,markup=None):call('sendMessage',{'chat_id':chat,'text':text[:4096],'reply_markup':markup or HOME})
def buttons_for(n):return {'inline_keyboard':[[{'text':'✏ Дописать','callback_data':'append:'+n['id']},{'text':'☆ Открепить' if n['pinned'] else '⭐ Закрепить','callback_data':'pin:'+n['id']}],[{'text':'🗑 В корзину','callback_data':'trash:'+n['id']}],[{'text':'Открыть в приложении','web_app':{'url':URL+'?note='+n['id']}}]]}
def listing(db,q='',pinned=False,page=0):
    where='deleted IS NULL';args=[]
    if pinned:where+=' AND pinned=1'
    if q:where+=' AND (instr(fold(title),fold(?))>0 OR instr(fold(body),fold(?))>0)';args.extend([q,q])
    rows=[dict(r) for r in db.execute('SELECT id,title FROM notes WHERE '+where+' ORDER BY pinned DESC,updated DESC LIMIT 9 OFFSET ?',args+[page*8])]
    keyboard=[[{'text':(r['title'] or 'Без названия')[:55],'callback_data':'note:'+r['id']}] for r in rows[:8]]
    if len(rows)>8 and not q:keyboard.append([{'text':'Дальше →','callback_data':('stars:' if pinned else 'list:')+str(page+1)}])
    keyboard.append([{'text':'Открыть все заметки','web_app':{'url':URL}}])
    return ('Выбери заметку:' if rows else 'Заметок пока нет. Отправь мне текст — сохраню.'),{'inline_keyboard':keyboard}
def handle(update):
    callback=update.get('callback_query');message=callback.get('message',{}) if callback else update.get('message',{})
    chat=message.get('chat',{});sender=(callback or message).get('from',{})
    if chat.get('type')!='private' or str(sender.get('id'))!=str(chat.get('id')):return
    cid=str(chat['id']);uid=update['update_id'];text=str(message.get('text','')).strip();reply=None;markup=None
    with database() as db:
        db.execute('BEGIN IMMEDIATE')
        if db.execute('SELECT 1 FROM bot_updates WHERE id=?',(uid,)).fetchone():return
        linked=bool(db.execute('SELECT 1 FROM telegram WHERE chat=?',(cid,)).fetchone())
        if not callback and text.startswith('/start '):
            code=text.split(maxsplit=1)[1]
            if db.execute('SELECT 1 FROM links WHERE code=? AND expires>?',(code,time.time())).fetchone():
                db.execute('DELETE FROM telegram');db.execute('INSERT INTO telegram VALUES(?)',(cid,));db.execute('DELETE FROM links');db.execute('DELETE FROM bot_state');reply='Готово, Telegram подключён! Отправь текст — я сохраню его как заметку. Или открой Mini App кнопкой ниже.'
            else:reply='Код недействителен или истёк. Получи новый в Заметках → Настройки → Telegram.'
        elif not linked:reply='Сначала войди на '+URL+' и открой Настройки → Telegram → Получить код. Отправь мне полученную команду /start КОД.';markup={'inline_keyboard':[[{'text':'Открыть Заметки','web_app':{'url':URL}}]]}
        elif callback:
            data=str(callback.get('data',''));action,_,argument=data.partition(':')
            if action in ('list','stars'):
                try:page=max(0,min(10000,int(argument)))
                except ValueError:page=0
                reply,markup=listing(db,pinned=action=='stars',page=page)
            else:
                row=db.execute('SELECT * FROM notes WHERE id=? AND deleted IS NULL',(argument,)).fetchone();n=dict(row) if row else None
                if not n:reply='Заметка не найдена или перемещена в корзину.'
                elif action=='note':reply=(n['title'] or 'Без названия')+'\n\n'+n['body'][:3500]+('\n\nПродолжение — в приложении.' if len(n['body'])>3500 else '');markup=buttons_for(n)
                elif action=='append':db.execute('INSERT OR REPLACE INTO bot_state VALUES(?,?,?)',(cid,'append',n['id']));reply='Отправь текст, который нужно дописать. /cancel — отмена.'
                elif action=='pin':db.execute('UPDATE notes SET pinned=?,revision=revision+1,updated=? WHERE id=?',(0 if n['pinned'] else 1,time.time(),n['id']));reply='Закрепление обновлено.'
                elif action=='trash':db.execute('UPDATE notes SET deleted=?,revision=revision+1,updated=? WHERE id=?',(time.time(),time.time(),n['id']));reply='Заметка в корзине. Её можно восстановить в приложении.'
        elif text in ('/start','/help','/app','🌐 Открыть приложение'):markup={'inline_keyboard':[[{'text':'Открыть Mini App','web_app':{'url':URL}}]]};reply='Отправь любой текст — сохраню как заметку. Кнопки помогут найти и открыть записи. Mini App работает с той же базой.'
        elif text in ('/notes','📚 Мои заметки'):db.execute('DELETE FROM bot_state WHERE chat=?',(cid,));reply,markup=listing(db)
        elif text in ('/pinned','⭐ Закреплённые'):db.execute('DELETE FROM bot_state WHERE chat=?',(cid,));reply,markup=listing(db,pinned=True)
        elif text in ('/search','🔍 Найти'):db.execute('INSERT OR REPLACE INTO bot_state VALUES(?,?,?)',(cid,'search',''));reply='Что найти в заметках? Отправь слово или фразу. /cancel — отмена.'
        elif text in ('/new','📝 Новая заметка'):db.execute('INSERT OR REPLACE INTO bot_state VALUES(?,?,?)',(cid,'new',''));reply='Отправь текст заметки. Первая строка станет названием. /cancel — отмена.'
        elif text=='/cancel':db.execute('DELETE FROM bot_state WHERE chat=?',(cid,));reply='Отменено. Можно отправить новую заметку.'
        elif text and not text.startswith('/'):
            state=db.execute('SELECT mode,argument FROM bot_state WHERE chat=?',(cid,)).fetchone()
            if state and state['mode']=='search':reply,markup=listing(db,q=text[:200])
            elif state and state['mode']=='append':
                n=db.execute('SELECT * FROM notes WHERE id=? AND deleted IS NULL',(state['argument'],)).fetchone()
                if not n:reply='Заметка больше недоступна. Сохрани текст как новую заметку.'
                elif len(n['body'])+len(text)+2>200000:reply='Заметка слишком большая для дополнения.'
                else:
                    db.execute('INSERT INTO versions(note_id,title,body,revision,created) VALUES(?,?,?,?,?)',(n['id'],n['title'],n['body'],n['revision'],time.time()))
                    db.execute('DELETE FROM versions WHERE note_id=? AND id NOT IN (SELECT id FROM versions WHERE note_id=? ORDER BY id DESC LIMIT 20)',(n['id'],n['id']))
                    db.execute('UPDATE notes SET body=?,revision=revision+1,updated=? WHERE id=?',(n['body']+'\n\n'+text,time.time(),n['id']));reply='Текст дописан и уже доступен в приложении.'
                db.execute('DELETE FROM bot_state WHERE chat=?',(cid,))
            else:
                nid=secrets.token_hex(12);now=time.time();title=text.splitlines()[0][:200]
                db.execute('INSERT INTO notes(id,title,body,created,updated) VALUES(?,?,?,?,?)',(nid,title,text,now,now));reply='✅ Сохранено: '+title;markup={'inline_keyboard':[[{'text':'Открыть заметку','web_app':{'url':URL+'?note='+nid}}]]};db.execute('DELETE FROM bot_state WHERE chat=?',(cid,))
        else:reply='Пришли текст заметки или воспользуйся кнопками.'
        db.execute('INSERT OR IGNORE INTO bot_updates VALUES(?)',(uid,));db.execute('DELETE FROM bot_updates WHERE id<?',(uid-20000,))
    if callback:
        try:call('answerCallbackQuery',{'callback_query_id':callback['id']})
        except (OSError,ValueError):pass
    if reply:send(cid,reply,markup)
def main():
    offset=0;configured=False
    while True:
        if not TOKEN:time.sleep(30);continue
        try:
            if not configured:
                me=call('getMe',{});call('setChatMenuButton',{'menu_button':{'type':'web_app','text':'Заметки','web_app':{'url':URL}}})
                call('setMyCommands',{'commands':[{'command':'new','description':'Новая заметка'},{'command':'notes','description':'Мои заметки'},{'command':'search','description':'Поиск'},{'command':'app','description':'Открыть приложение'}]})
                with database() as db:db.execute('INSERT OR REPLACE INTO bot_info VALUES(?,?)',('username',me.get('username','')))
                configured=True
            for update in call('getUpdates',{'offset':offset,'timeout':25,'allowed_updates':['message','callback_query']}):handle(update);offset=update['update_id']+1
        except (OSError,ValueError,KeyError):print('Telegram temporarily unavailable; retrying.',flush=True);time.sleep(5)
if __name__=='__main__':main()
