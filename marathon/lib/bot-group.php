<?php
declare(strict_types=1);
function telegramGroupSchema(): void {
    sql('CREATE TABLE IF NOT EXISTS telegram_group_dispatches(id TEXT PRIMARY KEY,actor_id TEXT NOT NULL,actor_epoch INTEGER NOT NULL,chat_id TEXT NOT NULL,thread_id INTEGER,payload TEXT NOT NULL,confirmed INTEGER NOT NULL DEFAULT 0,expires_at INTEGER NOT NULL,next_attempt INTEGER NOT NULL DEFAULT 0)');
    if(!in_array('format_version',array_column(sql('PRAGMA table_info(telegram_group_dispatches)')->fetchAll(),'name'),true))sql('ALTER TABLE telegram_group_dispatches ADD COLUMN format_version INTEGER NOT NULL DEFAULT 0');
    // Retire old previews/queued reports containing personal participant data.
    sql('UPDATE telegram_group_dispatches SET confirmed=2 WHERE format_version<>1 AND confirmed<>2');
    sql('CREATE TABLE IF NOT EXISTS telegram_group_parts(dispatch_id TEXT NOT NULL,part INTEGER NOT NULL,text TEXT NOT NULL,sent_at INTEGER,PRIMARY KEY(dispatch_id,part))');
}
function telegramGroupReport(): string {
    return telegramDailyText(calendar())??'Сейчас нет текущей недели марафона.';
}
function telegramGroupCommand(array $message): ?array {
    $chat=$message['chat']??[];$from=$message['from']??[];
    if(!in_array($chat['type']??'',['group','supergroup'],true)||!preg_match('/^\/reading_here(?:@\w+)?\s*$/u',$message['text']??''))return null;
    $actor=sql("SELECT id FROM users WHERE telegram_id=? AND role='admin' AND active=1 AND deleted_at IS NULL",[(string)($from['id']??'')])->fetchColumn();
    if(!$actor||!empty($from['is_bot']))return null;
    foreach(['reading_group'=>(string)$chat['id'],'reading_group_title'=>(string)($chat['title']??'Группа'),'reading_group_thread'=>(string)($message['message_thread_id']??'')] as $key=>$value)sql('INSERT INTO settings VALUES (?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value',[$key,$value]);
    $args=['chat_id'=>$chat['id'],'text'=>'Группа подключена. В личном чате бота нажмите «📣 Отправить в группу»: сначала покажу предпросмотр.'];if(isset($message['message_thread_id']))$args['message_thread_id']=$message['message_thread_id'];
    return ['method'=>'sendMessage','args'=>$args];
}
function telegramGroupMenu(string $text,bool $callback,?array $actor,callable $reply): bool {
    if($text!=='📣 Отправить в группу'&&!($callback&&str_starts_with($text,'group:')))return false;
    if(!$actor||$actor['role']!=='admin'){$reply('Отправлять отчёт в группу может только администратор.');return true;}
    $group=setting('reading_group');if(!$group){$reply('Добавьте бота в нужную группу и отправьте там /reading_here со своего привязанного аккаунта администратора.');return true;}
    telegramGroupSchema();
    if($text==='📣 Отправить в группу'||$text==='group:preview'){
        $id=bin2hex(random_bytes(12));$body=telegramGroupReport();
        sql('INSERT INTO telegram_group_dispatches(id,actor_id,actor_epoch,chat_id,thread_id,payload,expires_at,format_version) VALUES (?,?,?,?,?,?,?,1)',[$id,$actor['id'],$actor['session_epoch'],$group,setting('reading_group_thread')?:null,$body,time()+600]);
        $reply('Предпросмотр для группы «'.setting('reading_group_title').'». После подтверждения отправлю только этот общий ориентир.' ."\n\n".$body,[[['text'=>'✓ Отправить в группу','callback_data'=>'group:send:'.$id],['text'=>'Отмена','callback_data'=>'group:cancel:'.$id]]]);return true;
    }
    if(!preg_match('/^group:(send|cancel):([a-f0-9]{24})$/D',$text,$m))return true;
    $job=sql('SELECT * FROM telegram_group_dispatches WHERE id=?',[$m[2]])->fetch();
    if(!$job||$job['actor_id']!==$actor['id']||(int)$job['actor_epoch']!==(int)$actor['session_epoch']||$job['chat_id']!==$group||(int)$job['format_version']!==1||$job['confirmed']||$job['expires_at']<time()){$reply('Предпросмотр истёк, уже отправлен или группа изменилась. Откройте новый.');return true;}
    if($m[1]==='cancel'){sql('UPDATE telegram_group_dispatches SET confirmed=2 WHERE id=?',[$job['id']]);$reply('Отправка отменена.');return true;}
    $rest=$job['payload'];$part=0;while($rest!==''){$chunk=mb_strcut($rest,0,3500,'UTF-8');$rest=substr($rest,strlen($chunk));sql('INSERT INTO telegram_group_parts(dispatch_id,part,text) VALUES (?,?,?)',[$job['id'],$part++,$chunk]);}
    sql('UPDATE telegram_group_dispatches SET confirmed=1 WHERE id=?',[$job['id']]);$reply('Отчёт поставлен в очередь отправки в группу.');return true;
}
function telegramGroupDeliveries(?callable $deliver=null): void {
    telegramGroupSchema();$deliver??=fn($args)=>telegramCall('sendMessage',$args);
    $jobs=sql('SELECT d.*,p.part,p.text FROM telegram_group_dispatches d JOIN telegram_group_parts p ON p.dispatch_id=d.id WHERE d.confirmed=1 AND p.sent_at IS NULL AND d.next_attempt<=? ORDER BY d.rowid,p.part LIMIT 5',[time()])->fetchAll();
    foreach($jobs as $job){
        $actor=user($job['actor_id']);if(!$actor||$actor['role']!=='admin'||!$actor['active']||(int)$actor['session_epoch']!==(int)$job['actor_epoch']||$job['chat_id']!==setting('reading_group')||(string)$job['thread_id']!==setting('reading_group_thread')){sql('UPDATE telegram_group_dispatches SET confirmed=2 WHERE id=?',[$job['id']]);continue;}
        $args=['chat_id'=>$job['chat_id'],'text'=>$job['text']];if($job['thread_id'])$args['message_thread_id']=(int)$job['thread_id'];
        try{$deliver($args);sql('UPDATE telegram_group_parts SET sent_at=? WHERE dispatch_id=? AND part=?',[time(),$job['id'],$job['part']]);}
        catch(Throwable $e){sql('UPDATE telegram_group_dispatches SET next_attempt=? WHERE id=?',[time()+300,$job['id']]);error_log('Group reading report delivery failed; retry in 5 minutes.');break;}
    }
}
