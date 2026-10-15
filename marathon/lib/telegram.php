<?php
declare(strict_types=1);
require_once __DIR__.'/core.php';
// Pure update handler: tests exercise Telegram binding without contacting Telegram.
function telegramUpdate(array $update): array {
    $updateId=$update['update_id']??null;
    if(!is_int($updateId))return [];
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
        $reply=function(string $text,?array $keyboard=null)use(&$out,$chat){$args=['chat_id'=>$chat['id'],'text'=>$text];if($keyboard)$args['reply_markup']=['inline_keyboard'=>$keyboard];$out[]=['method'=>'sendMessage','args'=>$args];};
        $text=$callback['data']??$message['text']??'';
        $match=[];$kind=null;$token=null;
        if($callback&&preg_match('/^([ai])_([a-f0-9]{48})$/',$text,$match)){$kind=$match[1]==='a'?'login':'invite';$token=$match[2];}
        elseif(!$callback&&preg_match('/^\/start(?:@\w+)? ([ai])_([a-f0-9]{48})$/',$text,$match)){$kind=$match[1]==='a'?'login':'invite';$token=$match[2];}
        if($callback)$out[]=['method'=>'answerCallbackQuery','args'=>['callback_query_id'=>$callback['id']]];
        if($kind&&$token){
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
                    $keyboard=$base!==''?[[['text'=>'Открыть сайт','url'=>$base]]]:null;
                    $reply($kind==='invite'?'Telegram привязан. Откройте сайт и нажмите «Войти через Telegram».':'Вход подтверждён. Вернитесь во вкладку сайта — кабинет откроется автоматически.',$keyboard);
                }
            }
        } elseif(!$callback&&preg_match('/^(?:прочитал(?:а)?|\/read(?:@\w+)?)\s+(\d+)\s*(?:глав(?:у|ы)?\s*)?$/iu',trim($text),$reading)) {
            $reader=sql('SELECT * FROM users WHERE telegram_id=? AND active=1 AND deleted_at IS NULL',[$telegramId])->fetch();
            if(!$reader)$reply('Сначала привяжите Telegram к своему аккаунту по персональной ссылке от команды марафона.');
            else {try{$week=addReading($reader['id'],$reader['id'],(int)$reading[1],calendar()['today'],'','Отметка из Telegram','telegram','tg_'.$updateId);$reply('Зачтено '.$reading[1].' глав. Неделя '.$week['week'].': '.$week['chapters'].' из '.$week['goal'].'. '.($week['completed']?'План выполнен за '.$week['days'].' дн.':'Осталось '.$week['remaining'].' глав; темп — '.$week['perDay'].' в день.'));}catch(DomainException $e){$reply($e->getMessage());}}
        } else $reply("Бот привязывает Telegram и подтверждает вход.\nЧтобы отметить чтение за сегодня, напишите: прочитал 5\nГрафики, планы и отчёты доступны на сайте.",$base!==''?[[['text'=>'Открыть сайт','url'=>$base]]]:null);
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
