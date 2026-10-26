<?php
declare(strict_types=1);
require __DIR__.'/../assets/pulse-telegram.php';
function check(bool $ok): void {if(!$ok)throw new RuntimeException('Check failed');}
function denied(callable $call): void {try{$call();}catch(DomainException $e){return;}throw new RuntimeException('Accepted invalid Telegram data');}
putenv('APP_URL=https://pulse.vano.sbena.net/');
check(pulseMiniAppMenu()['web_app']['url']==='https://pulse.vano.sbena.net/index.php?miniapp=1');
foreach(['http://pulse.test','https://user:pass@pulse.test','https://pulse.test/?bad=1','https://pulse.test/#bad',''] as $url){putenv('APP_URL='.$url);check(pulseMiniAppMenu()===null);}
putenv('APP_URL=https://pulse.vano.sbena.net');
$token='123:testing';$now=1700000000;
function signed(array $fields,string $token): string {ksort($fields);$lines=[];foreach($fields as $k=>$v)$lines[]=$k.'='.$v;$secret=hash_hmac('sha256',$token,'WebAppData',true);$fields['hash']=hash_hmac('sha256',implode("\n",$lines),$secret);return http_build_query($fields);}
$fields=['auth_date'=>(string)$now,'query_id'=>'test','user'=>json_encode(['id'=>123,'first_name'=>'Test'])];
$raw=signed($fields,$token);check(pulseValidateTelegramInitData($raw,$token,$now)['telegram_id']==='123');
denied(fn()=>pulseValidateTelegramInitData($raw,'wrong',$now));
denied(fn()=>pulseValidateTelegramInitData($raw,$token,$now+3601));
denied(fn()=>pulseValidateTelegramInitData($raw.'&auth_date='.$now,$token,$now));
$fields['user']=json_encode(['id'=>456]);denied(fn()=>pulseValidateTelegramInitData(str_replace('123','456',$raw),$token,$now));
$db=new PDO('sqlite::memory:',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION]);
function query(string $sql,array $args=[]): PDOStatement {global $db;$s=$db->prepare($sql);$s->execute($args);return $s;}
$update=['update_id'=>1,'message'=>['text'=>'/start','chat'=>['type'=>'private','id'=>123],'from'=>['id'=>123]]];
$actions=pulseTelegramUpdate($update,'bot');check($actions[0]['args']['reply_markup']['inline_keyboard'][0][0]['web_app']['url']===pulseMiniAppUrl());
check(pulseTelegramUpdate($update,'bot')===[]);
$update['update_id']=2;$update['message']['chat']['type']='group';check(pulseTelegramUpdate($update,'bot')===[]);
echo "PASS: Mini App URL, Telegram signatures, expiry, tampering, private launch and duplicate updates\n";
