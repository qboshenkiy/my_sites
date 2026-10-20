<?php
declare(strict_types=1);
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){http_response_code(404);exit;}

function formsBotSchema(): void {
    global $db;
    $db->exec("CREATE TABLE IF NOT EXISTS form_tg_deliveries(id TEXT PRIMARY KEY,form_id TEXT NOT NULL REFERENCES pulse_forms(id),
        kind TEXT NOT NULL,chat_id TEXT NOT NULL DEFAULT '',chat_title TEXT NOT NULL DEFAULT '',admin_tg_id TEXT,
        bind_code TEXT UNIQUE,position INTEGER NOT NULL DEFAULT -1,state TEXT NOT NULL DEFAULT 'awaiting',
        pending TEXT NOT NULL DEFAULT '',error TEXT NOT NULL DEFAULT '',revision INTEGER NOT NULL DEFAULT 0,
        current_poll_id TEXT,current_message_id INTEGER,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS form_tg_polls(poll_id TEXT PRIMARY KEY,delivery_id TEXT NOT NULL REFERENCES form_tg_deliveries(id),
        question_index INTEGER NOT NULL,message_id INTEGER NOT NULL,closed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS form_tg_votes(delivery_id TEXT NOT NULL,telegram_id TEXT NOT NULL,question_index INTEGER NOT NULL,
        choice INTEGER,name TEXT NOT NULL,user_id TEXT,PRIMARY KEY(delivery_id,telegram_id,question_index));
        CREATE TABLE IF NOT EXISTS pulse_tg_accounts(telegram_id TEXT PRIMARY KEY,user_id TEXT NOT NULL);
        CREATE INDEX IF NOT EXISTS form_tg_pending ON form_tg_deliveries(state,pending);");
}
function formsBotCall(string $method,array $args=[]): mixed {
    global $pulseFormBotTransport;
    return isset($pulseFormBotTransport)?$pulseFormBotTransport($method,$args):pulseBotCall($method,$args);
}
function formsBotRollback(): void {global $db;try{$db->exec('ROLLBACK');}catch(Throwable $ignored){}}
function formsBotValidate(array $form): void {
    if(!getenv('TELEGRAM_BOT_TOKEN')||!getenv('TELEGRAM_BOT_USERNAME'))throw new DomainException('Подключите отдельного бота Пульса в GitDeck.');
    foreach(json_decode($form['quiz'],true)['questions'] as $q){
        foreach($q['options'] as $option)if(mb_strlen($option)>100)throw new DomainException('В Telegram вариант ответа может содержать до 100 символов. Сократите его в опроснике и создайте новый тест.');
        if(!empty($q['image'])&&!preg_match('~^https://[^\s]+$~',getenv('APP_URL')?:''))throw new DomainException('Для изображений в Telegram задайте HTTPS-адрес Пульса в APP_URL.');
    }
}
function formsBotIdentity(string $telegram): ?array {
    try{
        $identity=communityBridge('pulse_telegram_identity',['telegram_id'=>$telegram],true);communityImport($identity);
        $u=query('SELECT * FROM pulse_accounts WHERE issuer=? AND external_id=? AND active=1',[$identity['issuer'],$identity['users'][0]['id']])->fetch();
        if($u){query('INSERT OR REPLACE INTO pulse_tg_accounts VALUES (?,?)',[$telegram,$u['id']]);return $u;}
    }catch(Throwable $e){if($e instanceof DomainException)query('DELETE FROM pulse_tg_accounts WHERE telegram_id=?',[$telegram]);}
    return null;
}
function formsBotQueue(array $delivery,string $command,?int $version=null): void {
    if($version!==null&&$version!==(int)$delivery['revision'])throw new DomainException('Управление уже изменилось. Используйте актуальные кнопки.');
    if(in_array($delivery['state'],['queued','sending'],true))throw new DomainException('Предыдущая команда ещё выполняется.');
    if(!in_array($command,['next','finish','review','retry'],true))throw new DomainException('Неизвестная команда.');
    if($delivery['state']==='awaiting')throw new DomainException('Сначала подключите группу командой /pulse.');
    if($command==='retry'&&$delivery['state']!=='error')throw new DomainException('Повтор доступен только после ошибки.');
    if($command==='next'&&$delivery['state']==='error')throw new DomainException('Сначала проверьте чат и используйте явный повтор отправки.');
    if($command==='next'&&$delivery['state']==='closed')throw new DomainException('Прохождение уже завершено.');
    if($command==='review'){
        $f=query('SELECT * FROM pulse_forms WHERE id=?',[$delivery['form_id']])->fetch();
        if(!$f['published'])throw new DomainException('Сначала откройте результаты теста на сайте.');
        if($delivery['state']!=='closed')throw new DomainException('Сначала завершите опрос в группе.');
    }
    query("UPDATE form_tg_deliveries SET pending=?,state='queued',error='',revision=revision+1 WHERE id=?",[$command==='retry'?($delivery['pending']?:'next'):$command,$delivery['id']]);
    if($command!=='review'&&$delivery['current_poll_id'])query('UPDATE form_tg_polls SET closed=1 WHERE poll_id=?',[$delivery['current_poll_id']]);
}
function formsBotHandle(string $action,array $input,array $form): void {
    global $db;
    try{formsBotValidate($form);}catch(DomainException $e){fail($e->getMessage());}
    if($action==='form_telegram_create'){
        $id=bin2hex(random_bytes(8));$code=bin2hex(random_bytes(16));
        query('INSERT INTO form_tg_deliveries(id,form_id,kind,bind_code,created_at) VALUES (?,?,?,?,?)',[$id,$form['id'],'group',$code,time()]);
        out(['id'=>$id,'command'=>'/pulse '.$code]);
    }
    $db->exec('BEGIN IMMEDIATE');$delivery=query('SELECT * FROM form_tg_deliveries WHERE id=? AND form_id=? AND kind=\'group\'',[$input['delivery']??'',$form['id']])->fetch();
    if(!$delivery)fail('Отправка в группу не найдена.',404);
    try{formsBotQueue($delivery,(string)($input['command']??''),(int)($input['revision']??-1));}catch(DomainException $e){fail($e->getMessage(),409);}
    communityAudit('telegram_form_command',$delivery['id'],['command'=>$input['command']]);$db->exec('COMMIT');out(['ok'=>true]);
}
function formsBotReply(string $chat,string $text,?array $keyboard=null): void {
    $args=['chat_id'=>$chat,'text'=>$text];if($keyboard)$args['reply_markup']=['inline_keyboard'=>$keyboard];formsBotCall('sendMessage',$args);
}
function formsBotAdmin(string $chat,string $telegram): bool {
    $member=formsBotCall('getChatMember',['chat_id'=>$chat,'user_id'=>$telegram]);
    return in_array($member['status']??'',['creator','administrator'],true);
}
function formsBotUpdate(array $update,string $botId): bool {
    global $db;
    formsBotSchema();pulseTelegramSchema();$number=$update['update_id']??null;if(!is_int($number))return false;
    $message=$update['message']??$update['callback_query']['message']??[];$callback=$update['callback_query']??null;
    $text=$callback['data']??$message['text']??'';$poll=$update['poll_answer']??null;
    $isStart=preg_match('/^\/start(?:@\w+)? ft_([a-f0-9]{32})$/',$text,$start);
    $isBind=preg_match('/^\/pulse(?:@\w+)? ([a-f0-9]{32})$/',$text,$bind);
    $isControl=preg_match('/^pg:([a-f0-9]{16}):(\d+):(next|finish|review)$/',$text,$control);
    $isResult=preg_match('/^pr:([a-f0-9]{16})$/',$text,$result);
    $isRetry=preg_match('/^pt:([a-f0-9]{16}):(\d+)$/',$text,$retry);
    if(!$isStart&&!$isBind&&!$isControl&&!$isResult&&!$isRetry&&!$poll)return false;
    if(query('SELECT 1 FROM pulse_bot_updates WHERE bot_id=? AND update_id=?',[$botId,$number])->fetchColumn())return true;
    $from=$poll['user']??$callback['from']??$message['from']??[];$telegram=(string)($from['id']??'');$chat=(string)($message['chat']['id']??'');
    if(!preg_match('/^[0-9]{1,20}$/',$telegram)||!empty($from['is_bot']))return true;
    $name=trim(($from['first_name']??'').' '.($from['last_name']??''))?:'Участник';
    if($callback)formsBotCall('answerCallbackQuery',['callback_query_id'=>$callback['id']]);
    try{
        if($poll){
            $p=query('SELECT * FROM form_tg_polls WHERE poll_id=?',[$poll['poll_id']??''])->fetch();if(!$p||$p['closed'])return true;
            $delivery=query('SELECT * FROM form_tg_deliveries WHERE id=?',[$p['delivery_id']])->fetch();
            if($delivery['kind']==='private'&&$delivery['chat_id']!==$telegram)return true;
            if($delivery['state']!=='active')return true;
            $form=query('SELECT * FROM pulse_forms WHERE id=?',[$delivery['form_id']])->fetch();
            if(!$form['active'])return true;
            $q=json_decode($form['quiz'],true)['questions'][$p['question_index']];$choices=$poll['option_ids']??[];
            if(count($choices)>1||($choices&&(!is_int($choices[0])||!isset($q['options'][$choices[0]]))))return true;
            $known=query('SELECT user_id FROM form_tg_votes WHERE delivery_id=? AND telegram_id=? LIMIT 1',[$delivery['id'],$telegram])->fetch();
            if(!$known&&(int)query('SELECT count(DISTINCT telegram_id) FROM form_tg_votes WHERE delivery_id=?',[$delivery['id']])->fetchColumn()>=500)return true;
            $uid=$known?$known['user_id']:(formsBotIdentity($telegram)['id']??null);
            $db->exec('BEGIN IMMEDIATE');$fresh=query('SELECT closed FROM form_tg_polls WHERE poll_id=?',[$p['poll_id']])->fetchColumn();
            if(!$fresh)query('INSERT INTO form_tg_votes VALUES (?,?,?,?,?,?) ON CONFLICT(delivery_id,telegram_id,question_index) DO UPDATE SET choice=excluded.choice',[$delivery['id'],$telegram,$p['question_index'],$choices[0]??null,mb_substr($name,0,80),$uid]);
            if(!$fresh&&$choices&&$delivery['kind']==='private')formsBotQueue($delivery,'next');
            $db->exec('COMMIT');
        }elseif($isRetry){
            $db->exec('BEGIN IMMEDIATE');$d=query("SELECT * FROM form_tg_deliveries WHERE id=? AND kind='private' AND chat_id=?",[$retry[1],$telegram])->fetch();
            if(!$d||$chat!==$telegram||($message['chat']['type']??'')!=='private')throw new DomainException('Отправка не найдена.');
            formsBotQueue($d,'retry',(int)$retry[2]);$db->exec('COMMIT');
        }elseif($isStart){
            if(($message['chat']['type']??'')!=='private'||$chat!==$telegram)return true;
            $form=query('SELECT * FROM pulse_forms WHERE token=?',[$start[1]])->fetch();if(!$form)throw new DomainException('Тест не найден.');
            $existing=query('SELECT * FROM form_tg_deliveries WHERE form_id=? AND chat_id=? AND kind=\'private\' ORDER BY created_at DESC LIMIT 1',[$form['id'],$chat])->fetch();
            if($existing){
                $buttons=[[['text'=>'Мой результат','callback_data'=>'pr:'.$form['id']]]];
                if($existing['state']==='error')$buttons[]=[['text'=>'Проверил чат · повторить отправку','callback_data'=>'pt:'.$existing['id'].':'.$existing['revision']]];
                formsBotReply($chat,$existing['state']==='closed'?'Вы уже отправили ответы. Проверьте результат кнопкой ниже.':($existing['state']==='error'?'Отправка прервана. Проверьте, не пришёл ли опрос, перед повтором.':'Тест уже начат. Ответьте на последний присланный опрос.'),$buttons);
            }
            else{
                if(!$form['active'])throw new DomainException('Приём ответов теста закрыт.');formsBotValidate($form);$user=formsBotIdentity($telegram);
                if($form['require_account']&&!$user)throw new DomainException('Для этого теста нужен аккаунт марафона. Сначала привяжите Telegram и войдите в Пульс через этого бота.');
                $already=$user?query('SELECT id FROM form_attempts WHERE form_id=? AND user_id=?',[$form['id'],$user['id']])->fetchColumn():false;
                if($already)throw new DomainException('Вы уже отправили этот тест на сайте или в Telegram. Результат доступен на сайте после открытия администратором.');
                query("INSERT INTO form_tg_deliveries(id,form_id,kind,chat_id,chat_title,state,pending,created_at) VALUES (?,?,?,?,?,'queued','next',?)",[bin2hex(random_bytes(8)),$form['id'],'private',$chat,mb_substr($name,0,80),time()]);
                formsBotReply($chat,$form['title']."\nВопросы придут по одному. Ответ окончательный. Оценку и правильные ответы откроет администратор.");
            }
        }elseif($isBind){
            if(!in_array($message['chat']['type']??'',['group','supergroup'],true))throw new DomainException('Отправьте команду /pulse с кодом в нужной группе.');
            if(!formsBotAdmin($chat,$telegram))throw new DomainException('Подключить тест может только администратор этой группы.');
            $db->exec('BEGIN IMMEDIATE');$d=query('SELECT * FROM form_tg_deliveries WHERE bind_code=? AND state=\'awaiting\'',[$bind[1]])->fetch();
            if(!$d)throw new DomainException('Код уже использован или не найден. Создайте новое подключение на сайте.');
            if((int)$d['created_at']<time()-86400)throw new DomainException('Код старше суток. Создайте новое подключение на сайте.');
            query("UPDATE form_tg_deliveries SET chat_id=?,chat_title=?,admin_tg_id=?,bind_code=NULL,state='queued',pending='next',revision=revision+1 WHERE id=?",[$chat,mb_substr($message['chat']['title']??'Группа',0,100),$telegram,$d['id']]);$db->exec('COMMIT');
            $boundForm=query('SELECT require_account FROM pulse_forms WHERE id=?',[$d['form_id']])->fetch();
            formsBotReply($chat,'Тест подключён. Следующий вопрос и завершение доступны ведущему под опросом и в панели Пульса.'.($boundForm['require_account']?' Для учёта результата Telegram должен быть привязан к активному аккаунту марафона.':''));
        }elseif($isControl){
            $d=query('SELECT * FROM form_tg_deliveries WHERE id=? AND chat_id=? AND kind=\'group\'',[$control[1],$chat])->fetch();
            if(!$d||$d['admin_tg_id']!==$telegram||!formsBotAdmin($chat,$telegram))throw new DomainException('Управлять тестом может подключивший его администратор группы.');
            $db->exec('BEGIN IMMEDIATE');$d=query('SELECT * FROM form_tg_deliveries WHERE id=?',[$d['id']])->fetch();formsBotQueue($d,$control[3],(int)$control[2]);$db->exec('COMMIT');
        }elseif($isResult){
            if(($message['chat']['type']??'')!=='private'||$chat!==$telegram)return true;
            $form=query('SELECT * FROM pulse_forms WHERE id=?',[$result[1]])->fetch();if(!$form)throw new DomainException('Тест не найден.');
            $a=query('SELECT * FROM form_attempts WHERE form_id=? AND guest_key=?',[$form['id'],'t:'.hash('sha256',$telegram)])->fetch();
            if(!$a)throw new DomainException('Сначала завершите этот тест в боте.');
            if(!$form['published'])formsBotReply($chat,'Ответы приняты. Администратор ещё не открыл результаты.',[[['text'=>'Проверить позже','callback_data'=>'pr:'.$form['id']]]]);
            else formsBotSendReview($form,$chat,$a);
        }
    }catch(DomainException $e){formsBotRollback();if($chat)formsBotReply($chat,$e->getMessage());}
    query('INSERT OR IGNORE INTO pulse_bot_updates VALUES (?,?,?)',[$botId,$number,time()]);return true;
}
function formsBotSendReview(array $form,string $chat,?array $attempt=null): void {
    if($attempt)$attempt=formAdjustedAttempt($form,$attempt);
    $answers=$attempt?json_decode($attempt['answers'],true):[];$chunks=[];
    $text=$form['title']."\n".($attempt?'Ваш результат: '.$attempt['points'].' / '.$attempt['max_points'].' баллов.':"Правильные ответы:");
    foreach(json_decode($form['quiz'],true)['questions'] as $i=>$q){
        if($q['type']!=='quiz')continue;
        $row="\n\n".($i+1).'. '.$q['text']."\nПравильно: ".$q['options'][$q['correct']];
        if($attempt)$row.="\nВаш ответ: ".(isset($answers[$i])?$q['options'][$answers[$i]]:'Нет ответа');
        if(!empty($q['reference']))$row.="\n".$q['reference'];
        if(mb_strlen($text.$row)>3500){$chunks[]=$text;$text='';}$text.=$row;
    }
    $chunks[]=$text;foreach($chunks as $chunk)formsBotReply($chat,$chunk);
}
function formsBotFinish(array $delivery,array $form): void {
    $voters=query('SELECT telegram_id,name,user_id FROM form_tg_votes WHERE delivery_id=? GROUP BY telegram_id',[$delivery['id']])->fetchAll();
    foreach($voters as $v){
        if($form['require_account']&&!$v['user_id'])continue;
        $choices=array_fill(0,count(json_decode($form['quiz'],true)['questions']),null);
        foreach(query('SELECT question_index,choice FROM form_tg_votes WHERE delivery_id=? AND telegram_id=?',[$delivery['id'],$v['telegram_id']])->fetchAll() as $vote)$choices[$vote['question_index']]=$vote['choice']===null?null:(int)$vote['choice'];
        formStoreAttempt($form,$v['user_id'],'t:'.hash('sha256',$v['telegram_id']),$v['name'],$choices,'telegram_'.$delivery['kind'],true);
    }
}
function formsBotTick(): void {
    global $db;
    // No blind resend after a crash: Telegram sendPoll has no idempotency key.
    query("UPDATE form_tg_deliveries SET state='error',error='Отправка прервана. Проверьте чат перед повтором.' WHERE state='sending' AND created_at<?",[time()-60]);
    foreach(query("SELECT * FROM form_tg_deliveries WHERE state='queued' ORDER BY created_at LIMIT 3")->fetchAll() as $d){
        query("UPDATE form_tg_deliveries SET state='sending' WHERE id=? AND state='queued'",[$d['id']]);
        try{
            $form=query('SELECT * FROM pulse_forms WHERE id=?',[$d['form_id']])->fetch();$quiz=json_decode($form['quiz'],true);$next=(int)$d['position']+1;
            if($d['pending']==='review'){
                if(!$form['published'])throw new DomainException('Результаты ещё не открыты.');formsBotSendReview($form,$d['chat_id']);query("UPDATE form_tg_deliveries SET state='closed',pending='' WHERE id=?",[$d['id']]);continue;
            }
            if($d['current_message_id']){
                try{formsBotCall('stopPoll',['chat_id'=>$d['chat_id'],'message_id'=>(int)$d['current_message_id']]);}catch(Throwable $e){if(!property_exists($e,'telegramDescription')||!str_contains(mb_strtolower($e->telegramDescription),'already been closed'))throw $e;}
                query('UPDATE form_tg_polls SET closed=1 WHERE poll_id=?',[$d['current_poll_id']]);
            }
            if($d['pending']==='finish'||$next>=count($quiz['questions'])){
                $db->exec('BEGIN IMMEDIATE');formsBotFinish($d,$form);query("UPDATE form_tg_deliveries SET state='closed',pending='',error='' WHERE id=?",[$d['id']]);$db->exec('COMMIT');
                formsBotReply($d['chat_id'],'Ответы сохранены. '.($form['published']?'Результаты открыты.':'Результаты откроет администратор.'),$d['kind']==='private'?[[['text'=>'Мой результат','callback_data'=>'pr:'.$form['id']]]]:[[['text'=>'Отправить правильные ответы','callback_data'=>'pg:'.$d['id'].':'.$d['revision'].':review']]]);continue;
            }
            if(!$form['active'])throw new DomainException('Приём ответов теста закрыт на сайте.');
            $q=$quiz['questions'][$next];if(!empty($q['image']))formsBotCall('sendPhoto',['chat_id'=>$d['chat_id'],'photo'=>rtrim(getenv('APP_URL')?:'','/').'/api.php?action=image&id='.$q['image']]);
            $args=['chat_id'=>$d['chat_id'],'question'=>($next+1).'/'.count($quiz['questions']).' · '.$q['text'],
                'options'=>array_map(fn($text)=>['text'=>$text],$q['options']),'type'=>'regular','is_anonymous'=>false,'allows_multiple_answers'=>false,'allows_revoting'=>false,'hide_results_until_closes'=>true];
            if($d['kind']==='group')$args['reply_markup']=['inline_keyboard'=>[[['text'=>'Следующий вопрос →','callback_data'=>'pg:'.$d['id'].':'.$d['revision'].':next'],['text'=>'Завершить','callback_data'=>'pg:'.$d['id'].':'.$d['revision'].':finish']]]];
            $sent=formsBotCall('sendPoll',$args);if(!isset($sent['poll']['id'],$sent['message_id']))throw new RuntimeException('Не подтверждена отправка опроса.');
            $db->exec('BEGIN IMMEDIATE');query('INSERT INTO form_tg_polls VALUES (?,?,?,?,0)',[(string)$sent['poll']['id'],$d['id'],$next,(int)$sent['message_id']]);
            query("UPDATE form_tg_deliveries SET position=?,current_poll_id=?,current_message_id=?,state='active',pending='',error='' WHERE id=?",[$next,(string)$sent['poll']['id'],(int)$sent['message_id'],$d['id']]);$db->exec('COMMIT');
        }catch(Throwable $e){formsBotRollback();query("UPDATE form_tg_deliveries SET state='error',error=? WHERE id=?",[$e instanceof DomainException?$e->getMessage():'Не подтверждена отправка. Проверьте чат, права бота и подключение перед повтором.',$d['id']]);}
    }
}
