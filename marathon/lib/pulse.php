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
    if (!in_array($action,['pulse_directory','pulse_exchange','pulse_authorize'],true)) return;
    $key=getenv('PULSE_BRIDGE_SECRET')?:'';$url=rtrim(getenv('PULSE_URL')?:'','/');
    if(strlen($key)<32||!preg_match('~^https?://[^\s]+$~',$url))fail('Пульс ещё не подключён в GitDeck.',503);
    if($_SERVER['REQUEST_METHOD']!=='POST')fail('Нужен POST.',405);
    if((int)($_SERVER['CONTENT_LENGTH']??0)>10000)fail('Запрос слишком большой.',413);
    $input=json_decode(file_get_contents('php://input'),true);if(!is_array($input))fail('Некорректный запрос.');
    if($action!=='pulse_authorize'&&!hash_equals($key,$_SERVER['HTTP_X_PULSE_BRIDGE']??''))fail('Запрос не подтверждён.',403);
    if($action==='pulse_authorize'){
        global $csrf;
        if(!$me)fail('Сначала войдите в марафон.',401);
        if(!hash_equals($csrf,$_SERVER['HTTP_X_CSRF_TOKEN']??''))fail('Обновите страницу.',403);
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
