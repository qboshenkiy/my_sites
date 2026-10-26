<?php
declare(strict_types=1);

require_once __DIR__.'/pulse-miniapp.php';

function pulseTelegramSchema(): void {
    global $db;
    $db->exec('CREATE TABLE IF NOT EXISTS pulse_telegram_requests(token_hash TEXT PRIMARY KEY,session_hash TEXT NOT NULL,expires_at INTEGER NOT NULL,user_id TEXT,telegram_id TEXT,consumed INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS pulse_bot_updates(bot_id TEXT NOT NULL,update_id INTEGER NOT NULL,processed_at INTEGER NOT NULL,PRIMARY KEY(bot_id,update_id));');
}
// The update comes only from this site's dedicated bot's getUpdates API.
function pulseTelegramUpdate(array $update,string $botId): array {
    global $db;
    pulseTelegramSchema();$updateId=$update['update_id']??null;
    if(!is_int($updateId)||query('SELECT 1 FROM pulse_bot_updates WHERE bot_id=? AND update_id=?',[$botId,$updateId])->fetchColumn())return [];
    $callback=$update['callback_query']??null;$message=$callback['message']??$update['message']??[];
    $from=$callback['from']??$message['from']??[];$chat=$message['chat']??[];$telegramId=(string)($from['id']??'');
    if(($chat['type']??'')!=='private'||(string)($chat['id']??'')!==$telegramId||!preg_match('/^[0-9]{1,20}$/',$telegramId)||!empty($from['is_bot']))return [];
    $actions=[];if($callback)$actions[]=['method'=>'answerCallbackQuery','args'=>['callback_query_id'=>$callback['id']]];
    $text=$callback['data']??$message['text']??'';$match=[];$request=null;
    if(preg_match($callback?'/^pl_([a-f0-9]{48})$/':'/^\/start(?:@\w+)? pl_([a-f0-9]{48})$/',$text,$match))$request=query('SELECT * FROM pulse_telegram_requests WHERE token_hash=?',[hash('sha256',$match[1])])->fetch();
    $reply=['chat_id'=>$chat['id'],'text'=>'Откройте Пульс и нажмите «Войти через Telegram». Этот отдельный бот подтверждает вход в аккаунт, уже привязанный в марафоне.'];
    if(!$callback&&preg_match('/^\/(?:start|app)(?:@\w+)?$/',trim($text))&&($url=pulseMiniAppUrl())){
        $reply['text']='Откройте Пульс прямо в Telegram: викторины, тесты и ваши результаты.';
        $reply['reply_markup']=['inline_keyboard'=>[[['text'=>'Открыть Пульс','web_app'=>['url'=>$url]]]]];
    }
    if($match){
        if(!$request||$request['consumed']||$request['expires_at']<time())$reply['text']='Запрос уже использован или истёк. Начните вход заново на сайте Пульса.';
        else{
            // Network work is deliberately outside the SQLite write transaction.
            try{$identity=communityBridge('pulse_telegram_identity',['telegram_id'=>$telegramId],true);}
            catch(Throwable $error){
                $identity=null;
                $reply['text']=$error instanceof DomainException&&$error->getCode()===403
                    ?'Этот Telegram не привязан к активному аккаунту марафона. Проверьте привязку в профиле марафона или обратитесь к администратору.'
                    :'Не удалось связаться с марафоном и проверить аккаунт. Это не означает, что Telegram не привязан. Администратору: обновите «Марафон чтения» и «Пульс» в GitDeck, затем проверьте подключение сайтов. После этого начните вход заново на сайте Пульса.';
            }
            if($identity){
                if(!$callback){
                    $reply['text']='Подтвердить вход в Пульс для «'.$identity['users'][0]['name'].'»?' . "\nПодтверждайте только вход, который начали сами. Пароль не нужен.";
                    $reply['reply_markup']=['inline_keyboard'=>[[['text'=>'✓ Подтвердить вход в Пульс','callback_data'=>'pl_'.$match[1]]]]];
                }else{
                    $db->exec('BEGIN IMMEDIATE');
                    $fresh=query('SELECT * FROM pulse_telegram_requests WHERE token_hash=?',[$request['token_hash']])->fetch();
                    if(!$fresh||$fresh['consumed']||$fresh['expires_at']<time()||$fresh['user_id'])$reply['text']='Вход уже подтверждён или запрос истёк. Вернитесь в Пульс.';
                    else{
                        communityImport($identity);$u=query('SELECT id FROM pulse_accounts WHERE issuer=? AND external_id=? AND active=1',[$identity['issuer'],$identity['users'][0]['id']])->fetch();
                        require_once __DIR__.'/forms-bot.php';formsBotSchema();query('INSERT OR REPLACE INTO pulse_tg_accounts VALUES (?,?)',[$telegramId,$u['id']]);
                        query('UPDATE pulse_telegram_requests SET user_id=?,telegram_id=? WHERE token_hash=?',[$u['id'],$telegramId,$request['token_hash']]);
                        $reply['text']='Вход в Пульс подтверждён. Вернитесь на страницу, где начали вход — откроется ваш профиль.';
                    }
                    $db->exec('COMMIT');
                }
            }
        }
    }
    query('INSERT OR IGNORE INTO pulse_bot_updates VALUES (?,?,?)',[$botId,$updateId,time()]);
    query('DELETE FROM pulse_bot_updates WHERE processed_at<?',[time()-7*86400]);
    $actions[]=['method'=>'sendMessage','args'=>$reply];return $actions;
}
