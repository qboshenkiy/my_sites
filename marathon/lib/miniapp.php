<?php
declare(strict_types=1);

function telegramMiniAppUrl(): ?string {
    $base=rtrim(getenv('APP_URL')?:'','/');$parts=parse_url($base);
    if(!$parts||($parts['scheme']??'')!=='https'||empty($parts['host'])||isset($parts['user'])||isset($parts['pass'])||isset($parts['query'])||isset($parts['fragment']))return null;
    return $base.'/index.php?miniapp=1';
}
function telegramAppButtons(): ?array {
    $url=telegramMiniAppUrl();
    if($url)return [[['text'=>'📱 Открыть марафон','web_app'=>['url'=>$url]]]];
    $base=rtrim(getenv('APP_URL')?:'','/');
    return $base?[[['text'=>'🌐 Открыть сайт','url'=>$base]]]:null;
}
// Use the signed raw initData, never the browser's initDataUnsafe object.
function validateTelegramInitData(string $raw,string $token,?int $now=null): array {
    $deny=static function():never {throw new DomainException('Не удалось подтвердить вход Telegram. Закройте Mini App и откройте его заново из бота.');};
    if($token===''||$raw===''||strlen($raw)>16384)$deny();
    $fields=[];$pairs=explode('&',$raw);if(count($pairs)>32)$deny();
    foreach($pairs as $pair){
        if(!str_contains($pair,'=')||preg_match('/%(?![0-9a-fA-F]{2})/',$pair))$deny();
        [$key,$value]=explode('=',$pair,2);$key=urldecode($key);$value=urldecode($value);
        if(!preg_match('/^[a-z_]+$/D',$key)||array_key_exists($key,$fields))$deny();
        $fields[$key]=$value;
    }
    $hash=$fields['hash']??'';unset($fields['hash']);
    if(!preg_match('/^[0-9a-f]{64}$/D',$hash))$deny();
    ksort($fields,SORT_STRING);$lines=[];foreach($fields as $key=>$value)$lines[]=$key.'='.$value;
    $secret=hash_hmac('sha256',$token,'WebAppData',true);
    if(!hash_equals(hash_hmac('sha256',implode("\n",$lines),$secret),$hash))$deny();
    $date=$fields['auth_date']??'';$now??=time();
    if(!preg_match('/^\d{1,12}$/D',$date)||(int)$date>$now+30||$now-(int)$date>3600)$deny();
    try{$u=json_decode($fields['user']??'',true,16,JSON_THROW_ON_ERROR);}catch(JsonException){$deny();}
    if(!is_array($u)||!isset($u['id'])||!is_int($u['id'])||$u['id']<1||$u['id']>4503599627370495||!empty($u['is_bot']))$deny();
    $photo=$u['photo_url']??null;$parts=is_string($photo)?parse_url($photo):false;
    if(!is_string($photo)||strlen($photo)>2048||!$parts||($parts['scheme']??'')!=='https'||empty($parts['host'])||isset($parts['user'])||isset($parts['pass']))$photo=null;
    return ['telegram_id'=>(string)$u['id'],'auth_date'=>(int)$date,'photo_url'=>$photo];
}
