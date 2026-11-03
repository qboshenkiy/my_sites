<?php
declare(strict_types=1);
// Local audit and moderation for this application's own Telegram bot only.
function guardDb(): PDO {
    static $db=null;if($db)return $db;
    $dir=getenv('MARATHON_DATA_DIR')?:getenv('QUIZ_DATA_DIR')?:dirname(__DIR__).'/storage';
    if(!is_dir($dir))mkdir($dir,0700,true);
    $db=new PDO('sqlite:'.$dir.'/bot-guard.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    @chown($dir.'/bot-guard.sqlite','www-data');@chgrp($dir.'/bot-guard.sqlite','www-data');chmod($dir.'/bot-guard.sqlite',0660);
    $db->exec('PRAGMA busy_timeout=3000; CREATE TABLE IF NOT EXISTS people(id TEXT PRIMARY KEY,name TEXT,username TEXT,blocked INTEGER NOT NULL DEFAULT 0,last_seen REAL); CREATE TABLE IF NOT EXISTS events(id INTEGER PRIMARY KEY,person TEXT,direction TEXT,text TEXT,created REAL); CREATE INDEX IF NOT EXISTS events_person ON events(person,id); CREATE TABLE IF NOT EXISTS guard_seen(id INTEGER PRIMARY KEY,created REAL);');
    return $db;
}
function guardText(string $text): string {
    $text=preg_replace('~https?://[^\s]+~u','[ссылка]',$text);
    $text=preg_replace('/\b\d{6,12}:[A-Za-z0-9_-]{20,}\b/','[токен скрыт]',$text);
    $text=preg_replace('/(?:[a-z]{1,12}_){1,3}[a-f0-9]{16,}|sk_[a-zA-Z0-9]{16,}|\b[a-f0-9]{32,}\b/i','[код скрыт]',$text);
    if(preg_match('/^(?:\/start|[ai]_ |pl_|\/password|\/login)\b/ix',$text))return '[команда входа: параметры скрыты]';
    return mb_substr($text,0,4000);
}
function guardEvent(string $person,string $direction,string $text): void {
    $db=guardDb();$s=$db->prepare('INSERT INTO events(person,direction,text,created) VALUES(?,?,?,?)');$s->execute([$person,$direction,guardText($text),microtime(true)]);
    $db->exec('DELETE FROM events WHERE created<'.(time()-30*86400).' OR id<(SELECT COALESCE(MAX(id),0)-50000 FROM events)');
}
function guardIncoming(array $update): bool {
    try{
        $m=$update['callback_query']['message']??$update['message']??[];
        $from=$update['callback_query']['from']??$m['from']??$update['poll_answer']['user']??[];
        $id=(string)($from['id']??'');if(!preg_match('/^\d{1,20}$/',$id)||!empty($from['is_bot']))return true;
        $db=guardDb();$fresh=true;
        if(isset($update['update_id'])&&is_int($update['update_id'])){$seen=$db->prepare('INSERT OR IGNORE INTO guard_seen VALUES(?,?)');$seen->execute([$update['update_id'],microtime(true)]);$fresh=$seen->rowCount()>0;$db->exec('DELETE FROM guard_seen WHERE created<'.(time()-30*86400));}
        $s=$db->prepare('INSERT INTO people(id,name,username,last_seen) VALUES(?,?,?,?) ON CONFLICT(id) DO UPDATE SET name=excluded.name,username=excluded.username,last_seen=excluded.last_seen');
        $s->execute([$id,trim(($from['first_name']??'').' '.($from['last_name']??'')),$from['username']??'',microtime(true)]);
        $s=$db->prepare('SELECT blocked FROM people WHERE id=?');$s->execute([$id]);$blocked=(bool)$s->fetchColumn();
        // Group messages are not copied into private conversation history.
        if($fresh&&(($m['chat']['type']??'')==='private'||isset($update['poll_answer'])))guardEvent($id,$blocked?'blocked':'in',(string)($update['callback_query']['data']??$m['text']??(isset($update['poll_answer'])?'[ответ в опросе]':'[вложение]')));
        return !$blocked;
    }catch(Throwable $e){error_log('Guard audit unavailable');return true;}
}
function guardOutgoing(string $method,array $args): void {
    if(!in_array($method,['sendMessage','sendPoll','editMessageText'],true))return;
    try{
        $id=(string)($args['chat_id']??'');if(!preg_match('/^\d{1,20}$/',$id))return;
        guardEvent($id,'out',(string)($args['text']??$args['question']??''));
    }catch(Throwable $e){error_log('Guard audit unavailable');}
}
function guardFailure(array $update,string $stage,?Throwable $error=null): void {
    try{
        $from=$update['callback_query']['from']??$update['message']['from']??$update['poll_answer']['user']??[];
        $id=(string)($from['id']??'0');if(!preg_match('/^\d{1,20}$/',$id))$id='0';
        $text=match($stage){'response'=>'Не удалось отправить ответ Telegram.','connection'=>'Нет связи с Telegram или ошибка фоновой обработки бота.',default=>'Ошибка обработки сообщения.'};
        if($error&&preg_match('/HTTP ([0-9]{3})/',$error->getMessage(),$code))$text.=' HTTP '.$code[1].'.';
        guardEvent($id,'error',$text);
    }catch(Throwable $ignored){error_log('Guard error audit unavailable');}
}
function guardCli(string $action,array $data): array {
    $db=guardDb();$person=(string)($data['person']??'');
    if($action==='identity')return ['bot_id'=>explode(':',getenv('TELEGRAM_BOT_TOKEN')?:'')[0]];
    if($action==='activity'){
        $after=$data['after']??null;
        $max=(int)$db->query('SELECT COALESCE(MAX(id),0) FROM events')->fetchColumn();
        if($after===null||(is_int($after)&&$after>$max))return ['events'=>[],'cursor'=>$max];
        if(!is_int($after)||$after<0)throw new RuntimeException('Некорректный курсор');
        $q=$db->prepare("SELECT e.id,e.person,e.direction,e.created,CASE WHEN e.direction='error' THEN e.text ELSE '' END AS text,COALESCE(p.name,'') AS name FROM events e LEFT JOIN people p ON p.id=e.person WHERE e.id>? ORDER BY e.id LIMIT 1000");$q->execute([$after]);$events=$q->fetchAll();
        return ['events'=>$events,'cursor'=>$events?(int)end($events)['id']:$after];
    }
    if($action==='people')return ['people'=>$db->query('SELECT * FROM people ORDER BY last_seen DESC LIMIT 500')->fetchAll()];
    if(!preg_match('/^\d{1,20}$/',$person))throw new RuntimeException('Выберите участника');
    $q=$db->prepare('SELECT * FROM people WHERE id=?');$q->execute([$person]);if(!$q->fetch())throw new RuntimeException('Участник ещё не писал этому боту');
    if($action==='history'){$q=$db->prepare('SELECT direction,text,created FROM (SELECT * FROM events WHERE person=? ORDER BY id DESC LIMIT 100) ORDER BY id');$q->execute([$person]);return ['events'=>$q->fetchAll()];}
    if(in_array($action,['block','unblock'],true)){$q=$db->prepare('UPDATE people SET blocked=? WHERE id=?');$q->execute([$action==='block'?1:0,$person]);return ['ok'=>true];}
    if($action==='send'){
        $text=trim((string)($data['text']??''));if($text===''||mb_strlen($text)>3500)throw new RuntimeException('Введите сообщение до 3500 символов');
        $token=getenv('TELEGRAM_BOT_TOKEN');if(!$token)throw new RuntimeException('Токен бота не настроен');
        $body=['chat_id'=>$person,'text'=>$text];$ctx=stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\n",'content'=>json_encode($body),'timeout'=>15,'ignore_errors'=>true,'follow_location'=>0]]);
        $raw=@file_get_contents('https://api.telegram.org/bot'.$token.'/sendMessage',false,$ctx);$r=$raw!==false?json_decode($raw,true):null;
        if(empty($r['ok']))throw new RuntimeException('Telegram не принял сообщение. Возможно, участник остановил бота.');
        guardOutgoing('sendMessage',$body);return ['ok'=>true];
    }
    throw new RuntimeException('Неизвестное действие');
}
if(PHP_SAPI==='cli'&&realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){
    try{echo json_encode(guardCli($argv[1]??'',json_decode($argv[2]??'{}',true,16,JSON_THROW_ON_ERROR)),JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);}
    catch(Throwable $e){echo json_encode(['error'=>$e->getMessage()],JSON_UNESCAPED_UNICODE);exit(1);}
}
