<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
// GitDeck preserves the server Dockerfile; older images copied only two files into /opt/lib.
// The application library directory always contains the complete deployed code.
$library=is_file('/var/www/html/lib/telegram.php')?'/var/www/html/lib/telegram.php':dirname(__DIR__).'/lib/telegram.php';
require $library;
if(!getenv('TELEGRAM_BOT_TOKEN')){fwrite(STDERR,"Set TELEGRAM_BOT_TOKEN in .env and restart the bot service.\n");exit(1);}
$dir=getenv('MARATHON_DATA_DIR')?:dirname(__DIR__).'/storage';db();
$lock=fopen($dir.'/bot.lock','c');if(!flock($lock,LOCK_EX|LOCK_NB)){fwrite(STDERR,"Another bot worker is already running.\n");exit(1);}
try {
    $me=telegramCall('getMe',[])['result'];
    if(strtolower($me['username']??'')!==strtolower(getenv('TELEGRAM_BOT_USERNAME')?:''))throw new RuntimeException('Bot username does not match TELEGRAM_BOT_USERNAME.');
    if((telegramCall('getWebhookInfo',[])['result']['url']??'')!=='')throw new RuntimeException('This bot already has a webhook. Use a new bot or remove its webhook before running this worker.');
} catch(Throwable $e){fwrite(STDERR,$e->getMessage()."\n");exit(1);}
// Menu button and inline buttons use the signed Mini App launch mode.
if($miniApp=telegramMiniAppUrl()){
    try{telegramCall('setChatMenuButton',['menu_button'=>['type'=>'web_app','text'=>'Марафон','web_app'=>['url'=>$miniApp]]]);}
    catch(Throwable $e){fwrite(STDERR,"Could not configure Mini App menu. Inline launch buttons remain available.\n");}
}else fwrite(STDERR,"Mini App needs an HTTPS APP_URL. Browser and bot reading remain available.\n");
echo "Telegram authorization worker started.\n";
while(true){
    try {
        telegramDailyReminders();
        $last=(int)(sql("SELECT value FROM settings WHERE key='bot_offset'")->fetchColumn()?:0);
        $updates=telegramCall('getUpdates',['offset'=>$last,'timeout'=>25,'allowed_updates'=>['message','callback_query']])['result'];
        foreach($updates as $update){
            $messages=telegramUpdate($update);
            foreach($messages as $message){try{telegramCall($message['method'],$message['args']);}catch(Throwable $e){fwrite(STDERR,"Could not deliver a bot response. The authorization request is still saved.\n");}}
            sql("INSERT INTO settings VALUES ('bot_offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",[(string)($update['update_id']+1)]);
        }
    } catch(Throwable $e){fwrite(STDERR,"Bot connection unavailable. Retrying in 5 seconds.\n");sleep(5);}
}
