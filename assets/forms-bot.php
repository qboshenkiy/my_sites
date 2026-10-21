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
        CREATE TABLE IF NOT EXISTS form_tg_selections(delivery_id TEXT NOT NULL,telegram_id TEXT NOT NULL,question_index INTEGER NOT NULL,
        choices TEXT NOT NULL,name TEXT NOT NULL,user_id TEXT,PRIMARY KEY(delivery_id,telegram_id,question_index));
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
        if(count($q['options'])>12)throw new DomainException('В Telegram можно добавить не более 12 вариантов ответа. Сократите список и создайте новый тест.');
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
function formsBotGroupKeyboard(array $delivery,array $form,array $question): array {
    $revision=(int)$delivery['revision'];$qi=(int)$delivery['position'];$rows=[];
    foreach($question['options'] as $i=>$option){$label=($i+1).'. '.(mb_strlen($option)>56?mb_substr($option,0,55).'…':$option);$rows[]=[['text'=>$label,'callback_data'=>'fa:'.$delivery['id'].':'.$revision.':'.$qi.':'.$i]];}
    $rows[]=[['text'=>'Отправить мой ответ','callback_data'=>'fs:'.$delivery['id'].':'.$revision.':'.$qi]];
    $rows[]=[['text'=>'Следующий вопрос →','callback_data'=>'pg:'.$delivery['id'].':'.$revision.':next'],['text'=>'Завершить','callback_data'=>'pg:'.$delivery['id'].':'.$revision.':finish']];
    return $rows;
}
function formsBotGroupText(array $delivery,array $form): string {
    $quiz=json_decode($form['quiz'],true);$qi=(int)$delivery['position'];$q=$quiz['questions'][$qi];
    $answered=(int)query('SELECT count(*) FROM form_tg_votes WHERE delivery_id=? AND question_index=?',[$delivery['id'],$qi])->fetchColumn();
    $text=$form['title']."\nВопрос ".($qi+1).' из '.count($quiz['questions'])."\n\n".$q['text'];
    if(!empty($q['image']))$text.="\n\nИзображение: ".rtrim(getenv('APP_URL')?:'','/').'/api.php?action=image&id='.$q['image'];
    $text.="\n\nОтветили: ".$answered."\nВыберите вариант(ы), затем нажмите «Отправить мой ответ». Ваш выбор скрыт от группы.";
    return $text;
}
function formsBotEditGroupQuestion(array $delivery,array $form): void {
    $quiz=json_decode($form['quiz'],true);$q=$quiz['questions'][(int)$delivery['position']];
    formsBotCall('editMessageText',['chat_id'=>$delivery['chat_id'],'message_id'=>(int)$delivery['current_message_id'],
        'text'=>formsBotGroupText($delivery,$form),'reply_markup'=>['inline_keyboard'=>formsBotGroupKeyboard($delivery,$form,$q)]]);
}
function formsBotUpdate(array $update,string $botId): bool {
    global $db;
    formsBotSchema();pulseTelegramSchema();$number=$update['update_id']??null;if(!is_int($number))return false;
    $message=$update['message']??$update['callback_query']['message']??[];$callback=$update['callback_query']??null;
    $text=$callback['data']??$message['text']??'';$poll=$update['poll_answer']??null;
    $isStart=preg_match('/^\/start(?:@\w+)? ft_([a-f0-9]{32})$/',$text,$start);
    $isBind=preg_match('/^\/pulse(?:@\w+)? ([a-f0-9]{32})$/',$text,$bind);
    $isControl=preg_match('/^pg:([a-f0-9]{16}):(\d+):(next|finish|review)$/',$text,$control);
    $isGroupAnswer=preg_match('/^fa:([a-f0-9]{16}):(\d+):(\d+):(\d+)$/',$text,$groupAnswer);
    $isGroupSubmit=preg_match('/^fs:([a-f0-9]{16}):(\d+):(\d+)$/',$text,$groupSubmit);
    $isResult=preg_match('/^pr:([a-f0-9]{16})$/',$text,$result);
    $isRetry=preg_match('/^pt:([a-f0-9]{16}):(\d+)$/',$text,$retry);
    if(!$isStart&&!$isBind&&!$isControl&&!$isGroupAnswer&&!$isGroupSubmit&&!$isResult&&!$isRetry&&!$poll)return false;
    if(query('SELECT 1 FROM pulse_bot_updates WHERE bot_id=? AND update_id=?',[$botId,$number])->fetchColumn())return true;
    $from=$poll['user']??$callback['from']??$message['from']??[];$telegram=(string)($from['id']??'');$chat=(string)($message['chat']['id']??'');
    if(!preg_match('/^[0-9]{1,20}$/',$telegram)||!empty($from['is_bot']))return true;
    $name=trim(($from['first_name']??'').' '.($from['last_name']??''))?:'Участник';
    $callbackText=null;
    try{
        if($poll){
            $p=query('SELECT * FROM form_tg_polls WHERE poll_id=?',[$poll['poll_id']??''])->fetch();if(!$p||$p['closed'])return true;
            $delivery=query('SELECT * FROM form_tg_deliveries WHERE id=?',[$p['delivery_id']])->fetch();
            if($delivery['kind']==='private'&&$delivery['chat_id']!==$telegram)return true;
            if($delivery['state']!=='active')return true;
            $form=query('SELECT * FROM pulse_forms WHERE id=?',[$delivery['form_id']])->fetch();
            if(!$form['active'])return true;
            $q=json_decode($form['quiz'],true)['questions'][$p['question_index']];$choices=$poll['option_ids']??[];
            if(count($choices)>12||array_filter($choices,fn($n)=>!is_int($n)||!isset($q['options'][$n])))return true;
            $known=query('SELECT user_id FROM form_tg_votes WHERE delivery_id=? AND telegram_id=? LIMIT 1',[$delivery['id'],$telegram])->fetch();
            if(!$known&&(int)query('SELECT count(DISTINCT telegram_id) FROM form_tg_votes WHERE delivery_id=?',[$delivery['id']])->fetchColumn()>=500)return true;
            $uid=$known?$known['user_id']:(formsBotIdentity($telegram)['id']??null);
            $db->exec('BEGIN IMMEDIATE');$fresh=query('SELECT closed FROM form_tg_polls WHERE poll_id=?',[$p['poll_id']])->fetchColumn();
            if(!$fresh)query('INSERT INTO form_tg_votes VALUES (?,?,?,?,?,?) ON CONFLICT(delivery_id,telegram_id,question_index) DO UPDATE SET choice=excluded.choice',[$delivery['id'],$telegram,$p['question_index'],count($choices)>1?json_encode($choices):($choices[0]??null),mb_substr($name,0,80),$uid]);
            if(!$fresh&&$choices&&$delivery['kind']==='private')formsBotQueue($delivery,'next');
            $db->exec('COMMIT');
        }elseif($isGroupAnswer||$isGroupSubmit){
            $deliveryId=$isGroupAnswer?$groupAnswer[1]:$groupSubmit[1];
            $delivery=query("SELECT * FROM form_tg_deliveries WHERE id=? AND chat_id=? AND kind='group'",[$deliveryId,$chat])->fetch();
            if(!$delivery||($message['chat']['type']??'')==='private')throw new DomainException('Ответ относится к другой группе.');
            if($delivery['state']!=='active'||(int)$delivery['current_message_id']!==(int)($message['message_id']??0))throw new DomainException('Этот вопрос уже закрыт.');
            $qi=(int)$delivery['position'];$expectedRevision=(int)($isGroupAnswer?$groupAnswer[2]:$groupSubmit[2]);$callbackQuestion=(int)($isGroupAnswer?$groupAnswer[3]:$groupSubmit[3]);
            if($expectedRevision!==(int)$delivery['revision']||$callbackQuestion!==$qi)throw new DomainException('Опрос уже переключился на следующий вопрос.');
            $form=query('SELECT * FROM pulse_forms WHERE id=?',[$delivery['form_id']])->fetch();if(!$form['active'])throw new DomainException('Приём ответов теста закрыт.');
            $question=json_decode($form['quiz'],true)['questions'][$qi]??null;if(!$question)throw new DomainException('Вопрос не найден.');
            $telegramKey=(string)$telegram;$existing=query('SELECT 1 FROM form_tg_votes WHERE delivery_id=? AND telegram_id=? AND question_index=?',[$deliveryId,$telegramKey,$qi])->fetchColumn();
            if($existing)throw new DomainException('Ваш ответ уже принят.');
            $known=query('SELECT user_id FROM form_tg_votes WHERE delivery_id=? AND telegram_id=? LIMIT 1',[$deliveryId,$telegramKey])->fetch();
            if(!$known&&(int)query('SELECT count(DISTINCT telegram_id) FROM form_tg_votes WHERE delivery_id=?',[$deliveryId])->fetchColumn()>=500)throw new DomainException('Достигнут лимит в 500 участников.');
            $userId=$known?$known['user_id']:(formsBotIdentity($telegramKey)['id']??null);
            $db->exec('BEGIN IMMEDIATE');
            if($isGroupAnswer){
                $option=(int)$groupAnswer[4];if($option<0||!array_key_exists($option,$question['options']))throw new DomainException('Вариант ответа не найден.');
                $staged=query('SELECT choices FROM form_tg_selections WHERE delivery_id=? AND telegram_id=? AND question_index=?',[$deliveryId,$telegramKey,$qi])->fetchColumn();
                $selected=$staged===false?[]:json_decode((string)$staged,true);if(!is_array($selected))$selected=[];
                if(in_array($option,$selected,true))$selected=array_values(array_diff($selected,[$option]));else $selected[]=$option;
                sort($selected);query('INSERT OR REPLACE INTO form_tg_selections VALUES (?,?,?,?,?,?)',[$deliveryId,$telegramKey,$qi,json_encode($selected),mb_substr($name,0,80),$userId]);
                $callbackText=in_array($option,$selected,true)?'Вариант выбран. Остальные участники его не видят.':'Вариант снят.';
            }else{
                $staged=query('SELECT * FROM form_tg_selections WHERE delivery_id=? AND telegram_id=? AND question_index=?',[$deliveryId,$telegramKey,$qi])->fetch();
                $selected=$staged?json_decode($staged['choices'],true):[];
                if(!$selected)throw new DomainException('Сначала выберите хотя бы один вариант.');
                sort($selected);query('INSERT INTO form_tg_votes VALUES (?,?,?,?,?,?)',[$deliveryId,$telegramKey,$qi,json_encode($selected),$staged['name']??mb_substr($name,0,80),$staged['user_id']??$userId]);
                query('DELETE FROM form_tg_selections WHERE delivery_id=? AND telegram_id=? AND question_index=?',[$deliveryId,$telegramKey,$qi]);
                $callbackText='Ответ принят. Ваш вариант скрыт от группы.';
                $db->exec('COMMIT');$fresh=query('SELECT * FROM form_tg_deliveries WHERE id=?',[$deliveryId])->fetch();formsBotEditGroupQuestion($fresh,$form);
                $db->exec('BEGIN IMMEDIATE');
            }
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
    }catch(DomainException $e){formsBotRollback();if($callback)$callbackText=$e->getMessage();elseif($chat)formsBotReply($chat,$e->getMessage());}
    if($callback){$ack=['callback_query_id'=>$callback['id']];if($callbackText!==null)$ack['text']=mb_substr($callbackText,0,190);try{formsBotCall('answerCallbackQuery',$ack);}catch(Throwable $ignored){}}
    query('INSERT OR IGNORE INTO pulse_bot_updates VALUES (?,?,?)',[$botId,$number,time()]);return true;
}
function formsBotSendReview(array $form,string $chat,?array $attempt=null): void {
    if($attempt)$attempt=formAdjustedAttempt($form,$attempt);
    $answers=$attempt?json_decode($attempt['answers'],true):[];$chunks=[];
    $text=$form['title']."\n".($attempt?'Ваш результат: '.$attempt['points'].' / '.$attempt['max_points'].' баллов.':"Правильные ответы:");
    foreach(json_decode($form['quiz'],true)['questions'] as $i=>$q){
        if($q['type']!=='quiz')continue;
        $correct=$q['correct']??null;$correct=is_array($correct)?array_map('intval',$correct):[$correct===null?-1:(int)$correct];
        $row="\n\n".($i+1).'. '.$q['text']."\nПравильно: ".implode(', ',array_map(fn($n)=>$q['options'][$n]??'', $correct));
        if($attempt){$selected=$answers[$i]??null;$selected=$selected===null?[]:(is_array($selected)?$selected:[$selected]);$row.="\nВаш ответ: ".($selected?implode(', ',array_map(fn($n)=>$q['options'][(int)$n]??'', $selected)):'Нет ответа');}
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
        foreach(query('SELECT question_index,choice FROM form_tg_votes WHERE delivery_id=? AND telegram_id=?',[$delivery['id'],$v['telegram_id']])->fetchAll() as $vote){$decoded=json_decode((string)$vote['choice'],true);$answer=is_array($decoded)?array_map('intval',$decoded):($vote['choice']===null?null:(int)$vote['choice']);$q=json_decode($form['quiz'],true)['questions'][$vote['question_index']];if(is_array($q['correct']??null)&&$answer!==null&&!is_array($answer))$answer=[$answer];$choices[$vote['question_index']]=$answer;}
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
                if($d['current_poll_id']){
                    try{formsBotCall('stopPoll',['chat_id'=>$d['chat_id'],'message_id'=>(int)$d['current_message_id']]);}catch(Throwable $e){if(!property_exists($e,'telegramDescription')||!str_contains(mb_strtolower($e->telegramDescription),'already been closed'))throw $e;}
                    query('UPDATE form_tg_polls SET closed=1 WHERE poll_id=?',[$d['current_poll_id']]);
                }
            }
            if($d['pending']==='finish'||$next>=count($quiz['questions'])){
                $db->exec('BEGIN IMMEDIATE');formsBotFinish($d,$form);query("UPDATE form_tg_deliveries SET state='closed',pending='',error='' WHERE id=?",[$d['id']]);$db->exec('COMMIT');
                $finishText='Опрос завершён. Ответы сохранены. '.($form['published']?'Результаты открыты.':'Результаты откроет администратор.');
                if($d['kind']==='group'&&$d['current_message_id']&&!$d['current_poll_id'])formsBotCall('editMessageText',['chat_id'=>$d['chat_id'],'message_id'=>(int)$d['current_message_id'],'text'=>$finishText,'reply_markup'=>['inline_keyboard'=>[[['text'=>'Открыть разбор','callback_data'=>'pg:'.$d['id'].':'.$d['revision'].':review']]]]]);
                else formsBotReply($d['chat_id'],$finishText,$d['kind']==='private'?[[['text'=>'Мой результат','callback_data'=>'pr:'.$form['id']]]]:[[['text'=>'Отправить правильные ответы','callback_data'=>'pg:'.$d['id'].':'.$d['revision'].':review']]]);
                continue;
            }
            if(!$form['active'])throw new DomainException('Приём ответов теста закрыт на сайте.');
            $q=$quiz['questions'][$next];
            if($d['kind']==='group'){
                $nextDelivery=$d;$nextDelivery['position']=$next;$text=formsBotGroupText($nextDelivery,$form);
                $markup=['inline_keyboard'=>formsBotGroupKeyboard($nextDelivery,$form,$q)];
                if($d['current_message_id']&&!$d['current_poll_id']){
                    $sent=formsBotCall('editMessageText',['chat_id'=>$d['chat_id'],'message_id'=>(int)$d['current_message_id'],'text'=>$text,'reply_markup'=>$markup]);
                    $messageId=(int)$d['current_message_id'];
                }else{
                    $sent=formsBotCall('sendMessage',['chat_id'=>$d['chat_id'],'text'=>$text,'reply_markup'=>$markup]);
                    if(!isset($sent['message_id']))throw new RuntimeException('Не подтверждена отправка вопроса в группу.');$messageId=(int)$sent['message_id'];
                }
                $db->exec('BEGIN IMMEDIATE');query("UPDATE form_tg_deliveries SET position=?,current_poll_id=NULL,current_message_id=?,state='active',pending='',error='' WHERE id=?",[$next,$messageId,$d['id']]);$db->exec('COMMIT');continue;
            }
            if(!empty($q['image']))formsBotCall('sendPhoto',['chat_id'=>$d['chat_id'],'photo'=>rtrim(getenv('APP_URL')?:'','/').'/api.php?action=image&id='.$q['image']]);
            $args=['chat_id'=>$d['chat_id'],'question'=>($next+1).'/'.count($quiz['questions']).' · '.$q['text'],
                'options'=>array_map(fn($text)=>['text'=>$text],$q['options']),'type'=>'regular','is_anonymous'=>false,'allows_multiple_answers'=>count(is_array($q['correct']??null)?$q['correct']:[])>1,'allows_revoting'=>false,'hide_results_until_closes'=>true];
            if($d['kind']==='group')$args['reply_markup']=['inline_keyboard'=>[[['text'=>'Следующий вопрос →','callback_data'=>'pg:'.$d['id'].':'.$d['revision'].':next'],['text'=>'Завершить','callback_data'=>'pg:'.$d['id'].':'.$d['revision'].':finish']]]];
            $sent=formsBotCall('sendPoll',$args);if(!isset($sent['poll']['id'],$sent['message_id']))throw new RuntimeException('Не подтверждена отправка опроса.');
            $db->exec('BEGIN IMMEDIATE');query('INSERT INTO form_tg_polls VALUES (?,?,?,?,0)',[(string)$sent['poll']['id'],$d['id'],$next,(int)$sent['message_id']]);
            query("UPDATE form_tg_deliveries SET position=?,current_poll_id=?,current_message_id=?,state='active',pending='',error='' WHERE id=?",[$next,(string)$sent['poll']['id'],(int)$sent['message_id'],$d['id']]);$db->exec('COMMIT');
        }catch(Throwable $e){formsBotRollback();query("UPDATE form_tg_deliveries SET state='error',error=? WHERE id=?",[$e instanceof DomainException?$e->getMessage():'Не подтверждена отправка. Проверьте чат, права бота и подключение перед повтором.',$d['id']]);}
    }
}
