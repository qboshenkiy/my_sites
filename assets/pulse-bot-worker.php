<?php
declare(strict_types=1);
if(PHP_SAPI!=='cli'){http_response_code(404);exit;}
ini_set('display_errors','0');
require_once __DIR__.'/bot-guard.php';
function fail(string $message,int $status=400): never {throw new RuntimeException($message,$status);}
function query(string $sql,array $args=[]): PDOStatement {global $db;$s=$db->prepare($sql);$s->execute($args);return $s;}
class PulseBotApiException extends RuntimeException {public function __construct(public string $telegramDescription,int $http=0,string $method=''){parent::__construct('Telegram request failed (HTTP '.$http.'; method '.preg_replace('/[^a-zA-Z]/','',$method).').');}}
function pulseBotCall(string $method,array $args=[]): mixed {
    $token=getenv('TELEGRAM_BOT_TOKEN')?:'';
    if(!preg_match('/^\d+:[a-zA-Z0-9_-]+$/',$token))throw new RuntimeException('Задайте токен отдельного бота Пульса.');
    $context=stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\nConnection: close\r\n",'content'=>json_encode($args),'timeout'=>35,'ignore_errors'=>true,'follow_location'=>0],'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true]]);
    $raw=@file_get_contents('https://api.telegram.org/bot'.$token.'/'.$method,false,$context,0,2000000);$data=$raw!==false?json_decode($raw,true):null;
    $http=0;foreach($http_response_header??[] as $header){if(preg_match('/^HTTP\/\S+\s+(\d{3})/',$header,$match))$http=(int)$match[1];}
    if(!$data)throw new RuntimeException('Telegram request failed (HTTP '.$http.'; method '.preg_replace('/[^a-zA-Z]/','',$method).').');
    if(empty($data['ok']))throw new PulseBotApiException((string)($data['description']??''),(int)($data['error_code']??$http),$method);
    guardOutgoing($method,$args);
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
    require __DIR__.'/community.php';require __DIR__.'/pulse-telegram.php';require __DIR__.'/forms-bot.php';require __DIR__.'/pulse-game-bot.php';communitySchema();pulseTelegramSchema();formsBotSchema();pulseGameBotSchema();
    $bot=pulseBotIdentity();$botId=(string)$bot['id'];
    echo "Бот Пульса запущен.\n";
    $offset=(int)(query('SELECT value FROM settings WHERE key=?',['telegram_offset_'.$botId])->fetchColumn()?:0);
    $menuConfigured=false;
    while(true){
        $guardRecorded=false;
        try{
            if(!$menuConfigured){
                $menu=pulseMiniAppMenu();
                if($menu){try{pulseBotCall('setChatMenuButton',['menu_button'=>$menu]);$menuConfigured=true;}catch(Throwable $error){fwrite(STDERR,"Не удалось настроить кнопку Mini App. Повторим при следующем опросе.\n");}}
                else $menuConfigured=true;
            }
            formsBotTick();pulseGameBotTick();
            foreach(pulseBotCall('getUpdates',['offset'=>$offset,'timeout'=>5,'allowed_updates'=>['message','callback_query','poll_answer']]) as $update){
                try{
                if(guardIncoming($update)){
                if(!pulseGameBotUpdate($update,$botId)&&!formsBotUpdate($update,$botId))foreach(pulseTelegramUpdate($update,$botId) as $action)pulseBotCall($action['method'],$action['args']);
                }
                }catch(Throwable $error){guardFailure($update,'processing',$error);$guardRecorded=true;throw $error;}
                $offset=(int)$update['update_id']+1;query('INSERT OR REPLACE INTO settings VALUES (?,?)',['telegram_offset_'.$botId,(string)$offset]);
            }
            formsBotTick();pulseGameBotTick();
        }catch(Throwable $error){if(!$guardRecorded)guardFailure([],'connection',$error);formsBotRollback();fwrite(STDERR,"Ошибка связи бота Пульса. Повтор через 5 секунд.\n");sleep(5);}
    }
}catch(Throwable $error){fwrite(STDERR,$error->getMessage()."\n");exit(1);}
