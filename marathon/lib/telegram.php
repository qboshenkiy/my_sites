<?php
declare(strict_types=1);
require_once __DIR__.'/core.php';
require_once __DIR__.'/bot-menu.php';
require_once __DIR__.'/bot-admin.php';
require_once __DIR__.'/bot-audit.php';
// Pure update handler: tests exercise Telegram binding without contacting Telegram.
function telegramUpdate(array $update): array {
    $updateId=$update['update_id']??null;
    if(!is_int($updateId))return [];
    $GLOBALS['audit_transport']=['source'=>'telegram','request_id'=>bin2hex(random_bytes(8))];
    $out=[];db()->exec('BEGIN IMMEDIATE');
    try {
        if(sql('SELECT id FROM bot_updates WHERE id=?',[$updateId])->fetchColumn()!==false){db()->exec('COMMIT');return [];}
        $callback=$update['callback_query']??null;
        $message=$callback['message']??$update['message']??[];
        $from=$callback['from']??$message['from']??[];
        $chat=$message['chat']??[];
        $telegramId=(string)($from['id']??'');
        if(($chat['type']??'')!=='private'||(string)($chat['id']??'')!==$telegramId||!preg_match('/^\d+$/',$telegramId)||!empty($from['is_bot'])){
            sql('INSERT INTO bot_updates VALUES (?,?)',[$updateId,time()]);db()->exec('COMMIT');return [];
        }
        $base=rtrim(getenv('APP_URL')?:'','/');
        $reply=function(string $text,?array $keyboard=null)use(&$out,$chat,&$linked){do{$chunk=mb_strcut($text,0,3500,'UTF-8');$text=substr($text,strlen($chunk));$args=['chat_id'=>$chat['id'],'text'=>$chunk,'reply_markup'=>$keyboard&&$text===''?['inline_keyboard'=>$keyboard]:telegramReplyKeyboard(($linked['role']??null)==='admin')];$out[]=['method'=>'sendMessage','args'=>$args];}while($text!=='');};
        $text=$callback['data']??$message['text']??'';
        $linked=sql('SELECT * FROM users WHERE telegram_id=? AND active=1 AND deleted_at IS NULL',[$telegramId])->fetch()?:null;
        $readingText=$text;
        if($callback&&preg_match('/^amount:(\d+)$/',$text,$amount))$readingText='прочитал '.$amount[1];
        elseif(!$callback&&preg_match('/^\d+$/',trim($text))&&$linked){$state=sql('SELECT * FROM telegram_menu_states WHERE user_id=?',[$linked['id']])->fetch();if($state&&$state['expires_at']>=time()&&$state['telegram_id']===$telegramId&&(int)$state['session_epoch']===(int)$linked['session_epoch']&&(int)$state['round_number']===calendar($linked['id'])['round'])$readingText='прочитал '.trim($text);}
        $match=[];$kind=null;$token=null;
        if($callback&&preg_match('/^([ai])_([a-f0-9]{48})$/',$text,$match)){$kind=$match[1]==='a'?'login':'invite';$token=$match[2];}
        elseif(!$callback&&preg_match('/^\/start(?:@\w+)? ([ai])_([a-f0-9]{48})$/',$text,$match)){$kind=$match[1]==='a'?'login':'invite';$token=$match[2];}
        if($callback)$out[]=['method'=>'answerCallbackQuery','args'=>['callback_query_id'=>$callback['id']]];
        if(telegramAuditMenu($text,(bool)$callback,$linked,$reply)){}
        elseif(telegramAdminMenu($text,(bool)$callback,$linked,$telegramId,$reply)){}
        elseif(telegramMenu($text,(bool)$callback,$linked,$telegramId,$reply)){}
        elseif($callback&&preg_match('/^r_([yn])_([a-f0-9]{32})$/',$text,$confirmation)){
            $request=sql('SELECT * FROM telegram_reading_requests WHERE token_hash=?',[hash('sha256',$confirmation[2])])->fetch();
            $reader=$request?user($request['user_id']):null;
            if(!$request||$request['consumed']||$request['expires_at']<time()||!$reader||!$reader['active']||$reader['telegram_id']!==$telegramId||$request['telegram_id']!==$telegramId||(int)$reader['session_epoch']!==(int)$request['session_epoch'])$reply('Подтверждение недоступно, уже использовано или истекло. Отправьте число глав заново.');
            else {
                sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$reader['id']]);
                sql('UPDATE telegram_reading_requests SET consumed=1 WHERE token_hash=?',[$request['token_hash']]);
                if($confirmation[1]==='n')$reply('Отменено. Главы не добавлены. Можно отправить правильное число: прочитал 5');
                else {try{
                    $plan=telegramReadingPlan($reader['id'],(int)$request['chapters']);
                    if(!hash_equals($request['snapshot'],json_encode(['today'=>calendar($reader['id'])['today'],'plan'=>$plan],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR)))$reply('Результаты или план изменились после запроса. Ничего не добавлено. Отправьте число глав заново и проверьте распределение.');
                    else {$weeks=addTelegramReading($reader['id'],(int)$request['chapters'],$updateId);$lines=['Зачтено '.$request['chapters'].' глав.'];
                        foreach($weeks as $week)$lines[]='Неделя '.$week['week'].' · круг '.$week['cycle'].': +'.$week['added'].' глав, всего '.$week['chapters'].' из '.$week['goal'].'. '.($week['completed']?'План выполнен за '.$week['days'].' дн.'.($week['late']?' С опозданием.':''):'Осталось '.$week['remaining'].' глав.');
                        $current=stats($reader['id'])['pace'];$reply(implode("\n",$lines),$current&&$current['completed']?[[['text'=>'🔁 Прочитать план ещё раз','callback_data'=>'repeat:new']]]:[[['text'=>'📊 Мой прогресс','callback_data'=>'menu:progress']]]);}
                }catch(DomainException $e){$reply($e->getMessage().' Отправьте число глав заново.');}}
                if(isset($message['message_id']))$out[]=['method'=>'editMessageReplyMarkup','args'=>['chat_id'=>$chat['id'],'message_id'=>$message['message_id'],'reply_markup'=>['inline_keyboard'=>[]]]];
            }
        } elseif($kind&&$token){
            $r=sql('SELECT * FROM requests WHERE token_hash=?',[hash('sha256',$token)])->fetch();
            $linked=sql('SELECT * FROM users WHERE telegram_id=? AND active=1 AND deleted_at IS NULL',[$telegramId])->fetch();
            if(!$r||$r['kind']!==$kind||$r['expires_at']<time()||$r['approved']||$r['consumed'])$reply('Ссылка уже использована или истекла. Получите новую ссылку на сайте.');
            elseif($kind==='login'&&!$linked)$reply('Ваш Telegram ещё не привязан. Попросите администратора или модератора прислать персональную ссылку-приглашение.');
            else {
                $target=$kind==='invite'?user($r['user_id']):$linked;
                if(!$target||!$target['active'])$reply('Этот аккаунт недоступен. Обратитесь к администратору.');
                elseif($kind==='invite'&&($target['telegram_id']||sql('SELECT id FROM users WHERE telegram_id=?',[$telegramId])->fetchColumn()))$reply('Этот Telegram или аккаунт уже привязан. Обратитесь к администратору.');
                elseif(!$callback){
                    $label=$kind==='invite'?'Привязать Telegram':'Подтвердить вход';
                    $reply(($kind==='invite'?'Привязать ваш Telegram к аккаунту «'.$target['name'].'»?':'Подтвердить вход на сайт для «'.$target['name'].'»?')."\nПодтверждайте только свой запрос.",[[['text'=>$label,'callback_data'=>($kind==='invite'?'i_':'a_').$token]]]);
                } else {
                    if($kind==='invite')sql('UPDATE users SET telegram_id=?,telegram_name=? WHERE id=?',[$telegramId,$from['username']??null,$target['id']]);
                    sql('UPDATE requests SET approved=1,user_id=? WHERE token_hash=?',[$target['id'],$r['token_hash']]);
                    audit($target['id'],$kind==='invite'?'telegram_link':'telegram_login',$target['id'],$kind==='invite'?'Telegram привязан':'Вход подтверждён в Telegram');
                    $keyboard=telegramAppButtons();
                    $reply($kind==='invite'?(telegramMiniAppUrl()?'Telegram привязан. Нажмите «Открыть марафон» для входа в приложение.':'Telegram привязан. Откройте сайт и нажмите «Войти через Telegram».'):'Вход подтверждён. Вернитесь на сайт или в Android-приложение — кабинет откроется автоматически.',$keyboard);
                }
            }
        } elseif((!$callback||str_starts_with($text,'amount:'))&&preg_match('/^(?:прочитал(?:а)?|\/read(?:@\w+)?)\s+(\d+)\s*(?:глав(?:у|ы)?\s*)?$/iu',trim($readingText),$reading)) {
            $reader=sql('SELECT * FROM users WHERE telegram_id=? AND active=1 AND deleted_at IS NULL',[$telegramId])->fetch();
            if(!$reader)$reply('Сначала привяжите Telegram к своему аккаунту по персональной ссылке от команды марафона.');
            else {sql('INSERT INTO telegram_menu_states VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET telegram_id=excluded.telegram_id,session_epoch=excluded.session_epoch,round_number=excluded.round_number,expires_at=excluded.expires_at',[$reader['id'],$telegramId,(int)$reader['session_epoch'],calendar($reader['id'])['round'],time()+900]);sql('DELETE FROM telegram_reading_requests WHERE user_id=? OR expires_at<?',[$reader['id'],time()]);try{$plan=telegramReadingPlan($reader['id'],(int)$reading[1]);$token=bin2hex(random_bytes(16));
                sql('INSERT INTO telegram_reading_requests(token_hash,user_id,telegram_id,session_epoch,chapters,snapshot,expires_at) VALUES (?,?,?,?,?,?,?)',[hash('sha256',$token),$reader['id'],$telegramId,(int)$reader['session_epoch'],(int)$reading[1],json_encode(['today'=>calendar($reader['id'])['today'],'plan'=>$plan],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),time()+900]);
                $lines=['Добавить '.$reading[1].' глав? Сначала непрочитанный план предыдущей недели, затем текущая.'];
                foreach($plan as $week)$lines[]='Неделя '.$week['week'].' · круг '.$week['cycle'].': +'.$week['added'].' глав → '.($week['chapters']+$week['added']).' из '.$week['goal'].'.';
                $lines[]='Пока ничего не зачтено. Проверьте число и подтвердите. Кнопки действуют 15 минут; новый ввод заменяет предыдущий запрос.';
                $reply(implode("\n",$lines),[[['text'=>'✓ Подтвердить','callback_data'=>'r_y_'.$token],['text'=>'Отмена','callback_data'=>'r_n_'.$token]]]);
            }catch(DomainException $e){$reply($e->getMessage());}}
        } else $reply("Бот привязывает Telegram и подтверждает вход.\nЧтобы добавить прочитанные главы, напишите: прочитал 5\nГлавы сначала закрывают предыдущую неделю, остаток идёт в текущую. Перед зачётом нажмите «Подтвердить» или «Отмена».\nГрафики, планы и отчёты доступны на сайте.",$base!==''?[[['text'=>'Открыть сайт','url'=>$base]]]:null);
        sql('INSERT INTO bot_updates VALUES (?,?)',[$updateId,time()]);
        db()->exec('COMMIT');return $out;
    } catch(Throwable $e){if(db()->inTransaction())db()->rollBack();else db()->exec('ROLLBACK');throw $e;}
}
function telegramCall(string $method,array $args): array {
    $token=getenv('TELEGRAM_BOT_TOKEN');if(!$token)throw new RuntimeException('Telegram token is not configured.');
    $curl=curl_init('https://api.telegram.org/bot'.$token.'/'.$method);
    curl_setopt_array($curl,[CURLOPT_POST=>true,CURLOPT_POSTFIELDS=>json_encode($args),CURLOPT_HTTPHEADER=>['Content-Type: application/json'],CURLOPT_RETURNTRANSFER=>true,CURLOPT_CONNECTTIMEOUT=>10,CURLOPT_TIMEOUT=>40]);
    $raw=curl_exec($curl);$code=curl_getinfo($curl,CURLINFO_RESPONSE_CODE);curl_close($curl);
    $result=is_string($raw)?json_decode($raw,true):null;
    if($code!==200||!is_array($result)||!($result['ok']??false))throw new RuntimeException('Telegram request failed (HTTP '.$code.').');
    return $result;
}
