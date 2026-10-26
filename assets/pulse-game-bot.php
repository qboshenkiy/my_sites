<?php
declare(strict_types=1);
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){http_response_code(404);exit;}

function pulseGameBotSchema(): void {
    global $db;
    $db->exec("CREATE TABLE IF NOT EXISTS pulse_room_groups(
        room_id TEXT PRIMARY KEY REFERENCES rooms(id) ON DELETE CASCADE,
        bind_code TEXT UNIQUE, chat_id TEXT UNIQUE, chat_title TEXT NOT NULL DEFAULT '', admin_tg_id TEXT,
        revision INTEGER NOT NULL DEFAULT 0, message_id INTEGER, last_view TEXT NOT NULL DEFAULT '', created_at INTEGER NOT NULL
    );
        CREATE TABLE IF NOT EXISTS pulse_room_group_selections(
        room_id TEXT NOT NULL, telegram_id TEXT NOT NULL, question_index INTEGER NOT NULL,
        choices TEXT NOT NULL, name TEXT NOT NULL, PRIMARY KEY(room_id,telegram_id,question_index)
    );");
    foreach(["ALTER TABLE players ADD COLUMN source TEXT NOT NULL DEFAULT 'website'","ALTER TABLE players ADD COLUMN telegram_id TEXT"] as $sql){try{$db->exec($sql);}catch(Throwable $e){if(!str_contains(strtolower($e->getMessage()),'duplicate column'))throw $e;}}
    $db->exec('CREATE UNIQUE INDEX IF NOT EXISTS players_room_telegram ON players(room_id,telegram_id) WHERE telegram_id IS NOT NULL');
}
function pulseGameBotCreate(string $roomId): array {
    $room=query('SELECT * FROM rooms WHERE id=?',[$roomId])->fetch();
    if(!$room)fail('Комната не найдена.',404);
    if($room['status']==='finished')fail('Игра уже завершена. Откройте новую комнату.');
    if(query('SELECT 1 FROM pulse_room_groups WHERE room_id=? AND chat_id IS NOT NULL',[$roomId])->fetchColumn())fail('Для этой комнаты группа уже подключена.');
    $code=bin2hex(random_bytes(16));
    query('INSERT INTO pulse_room_groups(room_id,bind_code,created_at) VALUES (?,?,?) ON CONFLICT(room_id) DO UPDATE SET bind_code=excluded.bind_code,chat_id=NULL,chat_title="",admin_tg_id=NULL,message_id=NULL,last_view="",revision=pulse_room_groups.revision+1,created_at=excluded.created_at',[$roomId,$code,time()]);
    return ['command'=>'/quiz '.$code];
}
function pulseGameBotButtons(array $delivery,array $room,array $quiz): array {
    $revision=(int)$delivery['revision'];$index=(int)$room['current_index'];$rows=[];
    $q=$quiz['questions'][$index]??null;
    if($room['status']==='question'&&$q){
        foreach($q['options'] as $i=>$option){$label=($i+1).'. '.(mb_strlen($option)>45?mb_substr($option,0,44).'…':$option);$rows[]=[['text'=>$label,'callback_data'=>'qv:'.$room['id'].':'.$revision.':'.$index.':'.$i]];}
        $rows[]=[['text'=>'Очистить мой выбор','callback_data'=>'qx:'.$room['id'].':'.$revision.':'.$index],['text'=>'Отправить ответ','callback_data'=>'qs:'.$room['id'].':'.$revision.':'.$index]];
    }
    return $rows;
}
function pulseGameBotText(array $delivery,array $room,array $quiz): string {
    $index=(int)$room['current_index'];$total=count($quiz['questions']);
    if($room['status']==='lobby')return $room['quiz']?json_decode($room['quiz'],true)['title']."\n\nИгра подключена. Ведущий скоро начнёт.":'Игра подключена. Ведущий скоро начнёт.';
    if($room['status']==='finished')return "Игра завершена. Спасибо всем участникам!";
    $q=$quiz['questions'][$index]??null;if(!$q)return 'Ожидаем следующий вопрос от ведущего.';
    $players=(int)query('SELECT count(*) FROM players WHERE room_id=?',[$room['id']])->fetchColumn();
    $answers=(int)query('SELECT count(*) FROM answers WHERE room_id=? AND question_index=?',[$room['id'],$index])->fetchColumn();
    if($room['status']==='results'){
        $text="РЕЗУЛЬТАТЫ · ".($index+1)." / {$total}\n\n".$q['text'];
        if(($q['type']??'quiz')==='quiz'){$correct=$q['correct']??null;$correct=is_array($correct)?$correct:[$correct];$text.="\n\nПравильный ответ: ".implode(', ',array_map(fn($n)=>$q['options'][(int)$n]??'', $correct));}
        return $text."\n\nОтветили: {$answers} / {$players}. Следующий вопрос появится здесь.";
    }
    return "ПУЛЬС · ВОПРОС ".($index+1)." / {$total}\n\n".$q['text']."\n\nОтветьте кнопками ниже. Выбор можно отменить или изменить до отправки.\nОтветили: {$answers} / {$players}";
}
function pulseGameBotTick(): void {
    foreach(query('SELECT * FROM pulse_room_groups WHERE chat_id IS NOT NULL ORDER BY created_at LIMIT 100')->fetchAll() as $d){
        $room=query('SELECT * FROM rooms WHERE id=?',[$d['room_id']])->fetch();if(!$room)continue;
        if($room['status']==='question'&&(float)$room['deadline']<=microtime(true)){query("UPDATE rooms SET status='results',control_version=control_version+1 WHERE id=? AND status='question'",[$room['id']]);$room=query('SELECT * FROM rooms WHERE id=?',[$d['room_id']])->fetch();}
        $quiz=json_decode($room['quiz'],true);if(!is_array($quiz))continue;
        $view=hash('sha256',pulseGameBotText($d,$room,$quiz).'|'.$room['status'].'|'.$room['current_index'].'|'.$room['control_version']);
        if(hash_equals((string)$d['last_view'],$view))continue;
        try{
            $text=pulseGameBotText($d,$room,$quiz);$markup=['inline_keyboard'=>pulseGameBotButtons($d,$room,$quiz)];
            if($d['message_id']){
                formsBotCall('editMessageText',['chat_id'=>$d['chat_id'],'message_id'=>(int)$d['message_id'],'text'=>$text,'reply_markup'=>$markup]);
            }else{
                $sent=formsBotCall('sendMessage',['chat_id'=>$d['chat_id'],'text'=>$text,'reply_markup'=>$markup]);if(empty($sent['message_id']))throw new RuntimeException('Не получен номер сообщения Telegram.');
                query('UPDATE pulse_room_groups SET message_id=? WHERE room_id=?',[(int)$sent['message_id'],$d['room_id']]);
            }
            query('UPDATE pulse_room_groups SET last_view=? WHERE room_id=?',[$view,$d['room_id']]);
        }catch(PulseBotApiException $e){
            // Telegram returns “message is not modified” when only hidden draft selections changed.
            if(!str_contains(mb_strtolower($e->telegramDescription),'message is not modified'))fwrite(STDERR,"Не удалось обновить сообщение игры в Telegram. Проверьте права бота в группе.\n");
            else query('UPDATE pulse_room_groups SET last_view=? WHERE room_id=?',[$view,$d['room_id']]);
        }catch(Throwable $e){fwrite(STDERR,"Не удалось обновить сообщение игры в Telegram.\n");}
    }
}
function pulseGameBotUpdate(array $update,string $botId): bool {
    global $db;
    $number=$update['update_id']??null;if(!is_int($number)||query('SELECT 1 FROM pulse_bot_updates WHERE bot_id=? AND update_id=?',[$botId,$number])->fetchColumn())return false;
    $callback=$update['callback_query']??null;$message=$callback['message']??$update['message']??[];
    $text=$callback['data']??$message['text']??'';$from=$callback['from']??$message['from']??[];$chat=$message['chat']??[];
    $isBind=preg_match('/^\/quiz(?:@\w+)?\s+([a-f0-9]{32})$/',$text,$bind);
    $isVote=preg_match('/^qv:([a-f0-9]{16}):(\d+):(\d+):(\d+)$/',$text,$vote);
    $isClear=preg_match('/^qx:([a-f0-9]{16}):(\d+):(\d+)$/',$text,$clear);
    $isSubmit=preg_match('/^qs:([a-f0-9]{16}):(\d+):(\d+)$/',$text,$submit);
    if(!$isBind&&!$isVote&&!$isClear&&!$isSubmit)return false;
    $telegram=(string)($from['id']??'');$chatId=(string)($chat['id']??'');$callbackText=null;
    try{
        if(!preg_match('/^\d{1,20}$/',$telegram)||!empty($from['is_bot']))throw new DomainException('Этот пользователь не может отвечать.');
        if($isBind){
            if(!in_array($chat['type']??'', ['group','supergroup'],true))throw new DomainException('Выполните команду /quiz с кодом внутри группы.');
            if(!formsBotAdmin($chatId,$telegram))throw new DomainException('Подключить игру может только администратор группы.');
            $db->exec('BEGIN IMMEDIATE');$d=query('SELECT * FROM pulse_room_groups WHERE bind_code=?',[$bind[1]])->fetch();
            if(!$d)throw new DomainException('Код истёк или уже использован. Создайте новое подключение из комнаты Pulse.');
            if((int)$d['created_at']<time()-86400)throw new DomainException('Код старше суток. Создайте новое подключение из комнаты Pulse.');
            if(query('SELECT 1 FROM pulse_room_groups WHERE chat_id=? AND room_id<>?',[$chatId,$d['room_id']])->fetchColumn())throw new DomainException('Эта группа уже подключена к другой игре.');
            query('UPDATE pulse_room_groups SET bind_code=NULL,chat_id=?,chat_title=?,admin_tg_id=?,message_id=NULL,last_view="",revision=revision+1 WHERE room_id=?',[$chatId,mb_substr($chat['title']??'Группа',0,100),$telegram,$d['room_id']]);$db->exec('COMMIT');
            formsBotReply($chatId,'Игра Pulse подключена. Вопросы будут появляться в одном сообщении; участники смогут отвечать здесь или на сайте.');
        }else{
            $roomId=$isVote?$vote[1]:($isClear?$clear[1]:$submit[1]);$revision=(int)($isVote?$vote[2]:($isClear?$clear[2]:$submit[2]));$index=(int)($isVote?$vote[3]:($isClear?$clear[3]:$submit[3]));
            $db->exec('BEGIN IMMEDIATE');$d=query('SELECT * FROM pulse_room_groups WHERE room_id=? AND chat_id=?',[$roomId,$chatId])->fetch();
            if(!$d||($chat['type']??'')==='private')throw new DomainException('Эта кнопка относится к другой группе.');
            $room=query('SELECT * FROM rooms WHERE id=?',[$roomId])->fetch();if(!$room||$room['status']!=='question'||(int)$room['current_index']!==$index||(int)$d['revision']!==$revision)throw new DomainException('Вопрос уже закрылся или сменился.');
            if((float)$room['deadline']<=microtime(true))throw new DomainException('Время ответа закончилось.');
            if(query('SELECT 1 FROM answers WHERE room_id=? AND question_index=? AND player_id IN (SELECT id FROM players WHERE room_id=? AND telegram_id=?)',[$roomId,$index,$roomId,$telegram])->fetchColumn())throw new DomainException('Ваш ответ уже принят.');
            $quiz=json_decode($room['quiz'],true);$q=$quiz['questions'][$index]??null;if(!$q)throw new DomainException('Вопрос не найден.');
            $name=trim(($from['first_name']??'').' '.($from['last_name']??''))?:'Участник';$name=mb_substr($name,0,24);
            $player=query('SELECT * FROM players WHERE room_id=? AND telegram_id=?',[$roomId,$telegram])->fetch();
            if(!$player){$base=$name;$i=1;while(query('SELECT 1 FROM players WHERE room_id=? AND name=?',[$roomId,$name])->fetchColumn()){$i++;$name=mb_substr($base,0,20).' '.$i;}
                $playerId=bin2hex(random_bytes(8));query("INSERT INTO players(id,room_id,name,token,score,source,telegram_id) VALUES (?,?,?,?,0,'telegram',?)",[$playerId,$roomId,$name,bin2hex(random_bytes(32)),$telegram]);
            }else{$playerId=$player['id'];}
            if($isVote){$option=(int)$vote[4];if(!isset($q['options'][$option]))throw new DomainException('Вариант не найден.');
                $old=query('SELECT choices FROM pulse_room_group_selections WHERE room_id=? AND telegram_id=? AND question_index=?',[$roomId,$telegram,$index])->fetchColumn();$selected=$old===false?[]:json_decode((string)$old,true);if(!is_array($selected))$selected=[];
                if(in_array($option,$selected,true))$selected=array_values(array_diff($selected,[$option]));else $selected[]=$option;sort($selected);
                query('INSERT OR REPLACE INTO pulse_room_group_selections VALUES (?,?,?,?,?)',[$roomId,$telegram,$index,json_encode($selected),$name]);$callbackText=$selected?'Выбор обновлён. Нажмите «Отправить ответ», когда будете готовы.':'Выбор отменён.';
            }elseif($isClear){query('DELETE FROM pulse_room_group_selections WHERE room_id=? AND telegram_id=? AND question_index=?',[$roomId,$telegram,$index]);$callbackText='Выбор очищен.';
            }else{
                $selected=query('SELECT choices FROM pulse_room_group_selections WHERE room_id=? AND telegram_id=? AND question_index=?',[$roomId,$telegram,$index])->fetchColumn();$choices=$selected===false?[]:json_decode((string)$selected,true);if(!$choices)throw new DomainException('Сначала выберите ответ.');
                $multi=!empty($q['multiple'])||is_array($q['correct']??null);
                if(!$multi&&count($choices)!==1)throw new DomainException('Выберите один вариант ответа.');
                $expected=$q['correct']??null;$expected=is_array($expected)?array_map('intval',$expected):[$expected===null?-1:(int)$expected];$choices=array_map('intval',$choices);sort($choices);sort($expected);
                $correct=($q['type']??'quiz')==='quiz'&&$choices===$expected;$max=(int)($q['points']??1000);$points=$correct?(($quiz['scoring']??'speed')==='fixed'?$max:(int)round($max*(.5+.5*max(0,((float)$room['deadline']-microtime(true))/max(1,(int)$q['seconds']))))):0;
                query('INSERT INTO answers(player_id,room_id,question_index,choice,points,created_at) VALUES (?,?,?,?,?,?)',[$playerId,$roomId,$index,count($choices)===1?$choices[0]:json_encode($choices),$points,microtime(true)]);query('UPDATE players SET score=score+? WHERE id=?',[$points,$playerId]);query('DELETE FROM pulse_room_group_selections WHERE room_id=? AND telegram_id=? AND question_index=?',[$roomId,$telegram,$index]);
                $callbackText='Ответ принят. Его не видят остальные участники.';
                // A mixed web/group room stays open until its timer or the host reveals results.
            }
            $db->exec('COMMIT');
        }
    }catch(DomainException $e){if($db->inTransaction())$db->rollBack();$callbackText=$e->getMessage();if(!$callback&&$chatId)formsBotReply($chatId,$e->getMessage());}
    catch(Throwable $e){if($db->inTransaction())$db->rollBack();$callbackText='Не удалось обработать ответ. Попробуйте ещё раз.';if(!$callback&&$chatId)formsBotReply($chatId,$callbackText);}
    if($callback){try{formsBotCall('answerCallbackQuery',['callback_query_id'=>$callback['id'],'text'=>mb_substr((string)$callbackText,0,190)]);}catch(Throwable $ignored){}}
    query('INSERT OR IGNORE INTO pulse_bot_updates VALUES (?,?,?)',[$botId,$number,time()]);return true;
}
