"""Mixed website/Telegram live game path using an isolated SQLite database and fake Telegram transport."""
import json, os, sqlite3, subprocess, tempfile
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
PHP=shutil.which('php') if False else 'C:/laragon/bin/php/php-8.3.33-Win32-vs16-x64/php.exe'
CODE=r'''function query(string $s,array $a=[]):PDOStatement{global $db;$q=$db->prepare($s);$q->execute($a);return $q;}
function fail(string $m,int $s=400):never{throw new RuntimeException($m,$s);}
class PulseBotApiException extends RuntimeException{public function __construct(public string $telegramDescription){parent::__construct($telegramDescription);}}
$db=new PDO('sqlite:'.getenv('QUIZ_DATA_DIR').'/quiz.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);$db->exec('PRAGMA foreign_keys=ON;PRAGMA busy_timeout=10000;');
require $argv[1];require $argv[2];$input=json_decode(stream_get_contents(STDIN),true);$calls=[];
$pulseFormBotTransport=function($method,$args)use(&$calls){$calls[]=[$method,$args];if($method==='getChatMember')return ['status'=>(string)$args['user_id']==='101'?'creator':'member'];if($method==='sendMessage')return ['message_id'=>501];if($method==='editMessageText')return ['message_id'=>$args['message_id']];return [];};
if(isset($input['update']))pulseGameBotUpdate($input['update'],'999999');if(!empty($input['tick']))pulseGameBotTick();echo json_encode($calls,JSON_UNESCAPED_UNICODE);'''

def run(folder,payload):
    env=dict(os.environ,QUIZ_DATA_DIR=str(folder))
    return json.loads(subprocess.check_output([PHP,'-r',CODE,str(ROOT/'assets/forms-bot.php'),str(ROOT/'assets/pulse-game-bot.php')],env=env,input=json.dumps(payload),text=True,encoding='utf-8'))

with tempfile.TemporaryDirectory(prefix='pulse-group-game-') as tmp:
    folder=Path(tmp);db=sqlite3.connect(folder/'quiz.sqlite');db.executescript('''
    PRAGMA foreign_keys=ON;
    CREATE TABLE rooms(id TEXT PRIMARY KEY,code TEXT,quiz TEXT,status TEXT,current_index INTEGER,started_at REAL,deadline REAL,created_at INTEGER,control_version INTEGER DEFAULT 1);
    CREATE TABLE players(id TEXT PRIMARY KEY,room_id TEXT REFERENCES rooms(id),name TEXT,token TEXT,score INTEGER DEFAULT 0);
    CREATE TABLE answers(player_id TEXT,room_id TEXT,question_index INTEGER,choice INTEGER,points INTEGER,created_at REAL,PRIMARY KEY(player_id,question_index));
    CREATE TABLE settings(key TEXT PRIMARY KEY,value TEXT);
    CREATE TABLE pulse_bot_updates(bot_id TEXT,update_id INTEGER,processed_at INTEGER,PRIMARY KEY(bot_id,update_id));
    ''')
    room='0123456789abcdef';code='a'*32
    quiz={'title':'Общая игра','mode':'classic','scoring':'fixed','questions':[{'text':'Выберите правильный ответ','type':'quiz','seconds':60,'options':['Да','Нет'],'correct':0,'multiple':False,'points':500}]}
    db.execute('INSERT INTO rooms VALUES (?,?,?,?,?,?,?,?,1)',(room,'123456',json.dumps(quiz,ensure_ascii=False),'question',0,1,9999999999,1));db.execute('INSERT INTO pulse_room_groups(room_id,bind_code,created_at) VALUES (?,?,?)',(room,code,1)) if False else None
    db.commit();db.close()
    # Initialize the room-group schema and add the short-lived binding code.
    bootstrap_code=r'''function query(string $s,array $a=[]):PDOStatement{global $db;$q=$db->prepare($s);$q->execute($a);return $q;}$db=new PDO('sqlite:'.getenv('QUIZ_DATA_DIR').'/quiz.sqlite');require $argv[1];pulseGameBotSchema();query('INSERT INTO pulse_room_groups(room_id,bind_code,created_at) VALUES (?,?,?)',[$argv[2],$argv[3],time()]);'''
    subprocess.check_call([PHP,'-r',bootstrap_code,str(ROOT/'assets/pulse-game-bot.php'),room,code],env=dict(os.environ,QUIZ_DATA_DIR=str(folder)))
    def message(update,text,tg=101,chat=-100555,kind='supergroup'):
        return {'update_id':update,'message':{'message_id':90,'text':text,'from':{'id':tg,'first_name':'Иван'},'chat':{'id':chat,'type':kind,'title':'Команда'}}}
    def callback(update,tg,data,message_id,chat=-100555):
        return {'update_id':update,'callback_query':{'id':str(update),'from':{'id':tg,'first_name':'Иван'},'message':{'message_id':message_id,'chat':{'id':chat,'type':'supergroup'}},'data':data}}
    denied=run(folder,{'update':message(1,'/quiz '+code,202)})
    assert any(m=='sendMessage' and 'администратор' in args.get('text','') for m,args in denied)
    bound=run(folder,{'update':message(2,'/quiz '+code)})
    assert any(m=='sendMessage' for m,_ in bound)
    tick=run(folder,{'tick':True});assert any(m=='sendMessage' for m,_ in tick)
    db=sqlite3.connect(folder/'quiz.sqlite');d=db.execute('SELECT chat_id,revision,message_id FROM pulse_room_groups WHERE room_id=?',(room,)).fetchone();assert d[0]=='-100555' and d[2]
    message_id,revision=d[2],d[1]
    run(folder,{'update':callback(3,101,f'qv:{room}:{revision}:0:0',message_id)})
    # The explicit clear button cancels the draft before it is submitted.
    run(folder,{'update':callback(4,101,f'qx:{room}:{revision}:0',message_id)})
    run(folder,{'update':callback(5,101,f'qs:{room}:{revision}:0',message_id)})
    assert db.execute('SELECT count(*) FROM answers WHERE room_id=?',(room,)).fetchone()[0]==0
    run(folder,{'update':callback(6,101,f'qv:{room}:{revision}:0:0',message_id)})
    accepted=run(folder,{'update':callback(7,101,f'qs:{room}:{revision}:0',message_id)})
    assert any(m=='answerCallbackQuery' for m,_ in accepted)
    assert db.execute('SELECT name,score,source,telegram_id FROM players WHERE room_id=?',(room,)).fetchone()==('Иван',500,'telegram','101')
    assert db.execute('SELECT choice,points FROM answers WHERE room_id=?',(room,)).fetchone()==(0,500)
    assert db.execute('SELECT status FROM rooms WHERE id=?',(room,)).fetchone()[0]=='question'
    # One message is reused for the live question; repeat updates are ignored.
    updated=run(folder,{'tick':True});assert any(m=='editMessageText' for m,_ in updated)
    assert run(folder,{'update':callback(7,101,f'qs:{room}:{revision}:0',message_id)})==[]
    db.close()
print('PASS: group admin binding, private draft selection/cancel, shared game scoring, Telegram player visibility, room timer semantics, one editable message and update de-duplication')
