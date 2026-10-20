<?php
declare(strict_types=1);

function pulseIdentity(array $u): array {
    return ['id'=>$u['id'],'name'=>$u['name'],'role'=>$u['role'],'active'=>(bool)((int)$u['active']&&$u['deleted_at']===null)];
}
function pulseIssuer(): string {
    sql("INSERT OR IGNORE INTO settings(key,value) VALUES ('pulse_issuer',?)",[bin2hex(random_bytes(16))]);
    return setting('pulse_issuer');
}
function pulseHandle(string $action,?array $me): void {
    if (!in_array($action,['pulse_directory','pulse_exchange','pulse_authorize','pulse_export','pulse_telegram_identity'],true)) return;
    $key=getenv('PULSE_BRIDGE_SECRET')?:'';$url=rtrim(getenv('PULSE_URL')?:'','/');
    if(strlen($key)<32||!preg_match('~^https?://[^\s]+$~',$url))fail('Пульс ещё не подключён в GitDeck.',503);
    if($_SERVER['REQUEST_METHOD']!=='POST')fail('Нужен POST.',405);
    if((int)($_SERVER['CONTENT_LENGTH']??0)>10000)fail('Запрос слишком большой.',413);
    $input=json_decode(file_get_contents('php://input'),true);if(!is_array($input))fail('Некорректный запрос.');
    if(!in_array($action,['pulse_authorize','pulse_export'],true)&&!hash_equals($key,$_SERVER['HTTP_X_PULSE_BRIDGE']??''))fail('Запрос не подтверждён.',403);
    if(in_array($action,['pulse_authorize','pulse_export'],true)){
        global $csrf;
        if(!$me)fail('Сначала войдите в марафон.',401);
        if(!hash_equals($csrf,$_SERVER['HTTP_X_CSRF_TOKEN']??''))fail('Обновите страницу.',403);
    }
    if($action==='pulse_export'){
        guard(true);
        $body=json_encode(['issuer'=>pulseIssuer(),'users'=>array_map('pulseIdentity',sql('SELECT id,name,role,active,deleted_at FROM users ORDER BY name')->fetchAll())],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
        $context=stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\nX-Pulse-Bridge: $key\r\nConnection: close\r\n",'content'=>$body,'timeout'=>15,'ignore_errors'=>true,'follow_location'=>0],'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true]]);
        $raw=@file_get_contents($url.'/api.php?action=receive_marathon',false,$context,0,100000);
        $response=$raw!==false?json_decode($raw,true):null;
        if(!str_contains($http_response_header[0]??'',' 200 ')||!is_array($response)||!isset($response['imported']))fail('Пульс не принял участников. Обновите оба сайта и проверьте подключение в GitDeck.',502);
        audit($me['id'],'pulse_export',null,'Участники переданы в Пульс',['exported'=>(int)$response['imported']]);
        send(['imported'=>(int)$response['imported'],'url'=>$url]);
    }
    if($action==='pulse_telegram_identity'){
        $id=$input['telegram_id']??'';
        if(!is_string($id)||!preg_match('/^[0-9]{1,20}$/',$id))fail('Некорректный Telegram.',400);
        $u=sql('SELECT * FROM users WHERE telegram_id=? AND active=1 AND deleted_at IS NULL',[$id])->fetch();
        if(!$u){http_response_code(403);send(['error'=>'Telegram не привязан к активному аккаунту марафона.','code'=>'telegram_not_linked']);}
        send(['issuer'=>pulseIssuer(),'users'=>[pulseIdentity($u)]]);
    }
    sql('CREATE TABLE IF NOT EXISTS pulse_login_codes(code_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL,epoch INTEGER NOT NULL,state TEXT NOT NULL,challenge TEXT NOT NULL,expires_at INTEGER NOT NULL)');
    if($action==='pulse_directory'){
        $users=sql('SELECT id,name,role,active,deleted_at FROM users ORDER BY name')->fetchAll();
        send(['issuer'=>pulseIssuer(),'users'=>array_map('pulseIdentity',$users)]);
    }
    if($action==='pulse_authorize'){
        foreach(['state','challenge'] as $field)if(!is_string($input[$field]??null)||!preg_match('/^[a-f0-9]{64}$/',$input[$field]))fail('Некорректный запрос входа.');
        $code=bin2hex(random_bytes(32));sql('DELETE FROM pulse_login_codes WHERE expires_at<?',[time()]);
        sql('INSERT INTO pulse_login_codes VALUES (?,?,?,?,?,?)',[hash('sha256',$code),$me['id'],(int)$me['session_epoch'],$input['state'],$input['challenge'],time()+90]);
        send(['url'=>$url.'/?marathon_code='.$code.'&marathon_state='.$input['state']]);
    }
    foreach(['code','state','verifier'] as $field)if(!is_string($input[$field]??null)||!preg_match('/^[a-f0-9]{64}$/',$input[$field]))fail('Некорректный код входа.',403);
    db()->exec('BEGIN IMMEDIATE');
    $r=sql('SELECT * FROM pulse_login_codes WHERE code_hash=?',[hash('sha256',$input['code'])])->fetch();
    if(!$r||$r['expires_at']<time()||!hash_equals($r['state'],$input['state'])||!hash_equals($r['challenge'],hash('sha256',$input['verifier'])))fail('Код входа истёк или уже использован.',403);
    $u=user($r['user_id']);if(!$u||!(int)$u['active']||$u['deleted_at']!==null||(int)$u['session_epoch']!==(int)$r['epoch'])fail('Аккаунт недоступен.',403);
    sql('DELETE FROM pulse_login_codes WHERE code_hash=?',[$r['code_hash']]);$issuer=pulseIssuer();db()->exec('COMMIT');
    send(['issuer'=>$issuer,'users'=>[pulseIdentity($u)]]);
}
