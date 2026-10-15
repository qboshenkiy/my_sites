<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
require dirname(__DIR__).'/lib/telegram.php';
if(!getenv('TELEGRAM_BOT_TOKEN')){fwrite(STDERR,"Set TELEGRAM_BOT_TOKEN in .env and restart the bot service.\n");exit(1);}
$dir=getenv('MARATHON_DATA_DIR')?:dirname(__DIR__).'/storage';db();
$lock=fopen($dir.'/bot.lock','c');if(!flock($lock,LOCK_EX|LOCK_NB)){fwrite(STDERR,"Another bot worker is already running.\n");exit(1);}
try {
    $me=telegramCall('getMe',[])['result'];
    if(strtolower($me['username']??'')!==strtolower(getenv('TELEGRAM_BOT_USERNAME')?:''))throw new RuntimeException('Bot username does not match TELEGRAM_BOT_USERNAME.');
    if((telegramCall('getWebhookInfo',[])['result']['url']??'')!=='')throw new RuntimeException('This bot already has a webhook. Use a new bot or remove its webhook before running this worker.');
} catch(Throwable $e){fwrite(STDERR,$e->getMessage()."\n");exit(1);}
echo "Telegram authorization worker started.\n";
while(true){
    try {
        $last=(int)(sql("SELECT value FROM settings WHERE key='bot_offset'")->fetchColumn()?:0);
        $updates=telegramCall('getUpdates',['offset'=>$last,'timeout'=>25,'allowed_updates'=>['message','callback_query']])['result'];
        foreach($updates as $update){
            $messages=telegramUpdate($update);
            foreach($messages as $message){try{telegramCall($message['method'],$message['args']);}catch(Throwable $e){fwrite(STDERR,"Could not deliver a bot response. The authorization request is still saved.\n");}}
            sql("INSERT INTO settings VALUES ('bot_offset',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",[(string)($update['update_id']+1)]);
        }
    } catch(Throwable $e){fwrite(STDERR,"Bot connection unavailable. Retrying in 5 seconds.\n");sleep(5);}
}
