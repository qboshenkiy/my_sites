<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
ini_set('display_errors','0');
function fail(string $message,int $status=400): never {throw new RuntimeException($message,$status);}
function query(string $sql,array $args=[]): PDOStatement {global $db;$s=$db->prepare($sql);$s->execute($args);return $s;}
class PulseBotApiException extends RuntimeException {public function __construct(public string $telegramDescription){parent::__construct('Telegram не принял запрос. Проверьте права бота и настройки.');}}
function pulseBotCall(string $method,array $args=[]): mixed {
    $token=getenv('TELEGRAM_BOT_TOKEN')?:'';
    if(!preg_match('/^\d+:[a-zA-Z0-9_-]+$/',$token))throw new RuntimeException('Задайте токен отдельного бота Пульса.');
    $context=stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\nConnection: close\r\n",'content'=>json_encode($args),'timeout'=>35,'ignore_errors'=>true,'follow_location'=>0],'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true]]);
    $raw=@file_get_contents('https://api.telegram.org/bot'.$token.'/'.$method,false,$context,0,2000000);$data=$raw!==false?json_decode($raw,true):null;
    if(!$data)throw new RuntimeException('Нет подтверждения от Telegram. Проверьте подключение.');
    if(empty($data['ok']))throw new PulseBotApiException((string)($data['description']??''));
    return $data['result'];
}
function pulseBotIdentity(): array {
    $bot=pulseBotCall('getMe');
    if(strcasecmp($bot['username']??'',getenv('TELEGRAM_BOT_USERNAME')?:'')!==0)throw new RuntimeException('Имя бота и токен относятся к разным ботам. Проверьте настройки Пульса.');
    if(!empty(pulseBotCall('getWebhookInfo')['url']))throw new RuntimeException('У бота есть webhook. Для Пульса создайте отдельного нового бота без webhook.');
    return $bot;
}
try{
    if(in_array('--check',$argv,true)){pulseBotIdentity();echo "Токен, имя и режим отдельного бота проверены.\n";exit;}
    $dir=getenv('QUIZ_DATA_DIR')?:dirname(__DIR__).'/storage';
    if(!is_file($dir.'/quiz.sqlite'))throw new RuntimeException('Сначала запустите сайт Пульса.');
    $lock=fopen($dir.'/telegram-worker.lock','c');if(!$lock||!flock($lock,LOCK_EX|LOCK_NB))throw new RuntimeException('Бот Пульса уже запущен.');
    $db=new PDO('sqlite:'.$dir.'/quiz.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $db->exec('PRAGMA busy_timeout=10000; PRAGMA foreign_keys=ON;');$me=null;
    require __DIR__.'/community.php';require __DIR__.'/pulse-telegram.php';require __DIR__.'/forms-bot.php';communitySchema();pulseTelegramSchema();formsBotSchema();
    $bot=pulseBotIdentity();$botId=(string)$bot['id'];
    echo "Бот Пульса запущен.\n";
    $offset=(int)(query('SELECT value FROM settings WHERE key=?',['telegram_offset_'.$botId])->fetchColumn()?:0);
    while(true){
        try{
            formsBotTick();
            foreach(pulseBotCall('getUpdates',['offset'=>$offset,'timeout'=>5,'allowed_updates'=>['message','callback_query','poll_answer']]) as $update){
                if(!formsBotUpdate($update,$botId))foreach(pulseTelegramUpdate($update,$botId) as $action)pulseBotCall($action['method'],$action['args']);
                $offset=(int)$update['update_id']+1;query('INSERT OR REPLACE INTO settings VALUES (?,?)',['telegram_offset_'.$botId,(string)$offset]);
            }
            formsBotTick();
        }catch(Throwable $error){formsBotRollback();fwrite(STDERR,"Ошибка связи бота Пульса. Повтор через 5 секунд.\n");sleep(5);}
    }
}catch(Throwable $error){fwrite(STDERR,$error->getMessage()."\n");exit(1);}
