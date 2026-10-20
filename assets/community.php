<?php
declare(strict_types=1);
require_once __DIR__.'/room-report.php';
require_once __DIR__.'/forms.php';

// Additive migration: quizzes, room snapshots and past answers stay in place.
function communitySchema(): void {
    global $db;
    $db->exec("CREATE TABLE IF NOT EXISTS pulse_accounts(
        id TEXT PRIMARY KEY,name TEXT NOT NULL,login TEXT UNIQUE,password TEXT,role TEXT NOT NULL DEFAULT 'participant',
        issuer TEXT,external_id TEXT,active INTEGER NOT NULL DEFAULT 1,created_at INTEGER NOT NULL,
        UNIQUE(issuer,external_id));
        CREATE TABLE IF NOT EXISTS assessments(id TEXT PRIMARY KEY,title TEXT NOT NULL,max_points REAL NOT NULL,
        owner_id TEXT NOT NULL REFERENCES pulse_accounts(id),held_on TEXT NOT NULL,created_at INTEGER NOT NULL,revision INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS assessment_scores(assessment_id TEXT NOT NULL REFERENCES assessments(id),
        user_id TEXT NOT NULL REFERENCES pulse_accounts(id),points REAL NOT NULL,note TEXT NOT NULL DEFAULT '',
        updated_at INTEGER NOT NULL,editor_id TEXT NOT NULL,PRIMARY KEY(assessment_id,user_id));
        CREATE TABLE IF NOT EXISTS pulse_audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id TEXT,event TEXT NOT NULL,
        target_id TEXT,details TEXT NOT NULL,created_at INTEGER NOT NULL);");
    if (!query("SELECT value FROM settings WHERE key='community_schema'")->fetchColumn()) {
        $db->exec('BEGIN IMMEDIATE');
        foreach (['quizzes'=>['owner_id'=>'TEXT','visibility'=>"TEXT NOT NULL DEFAULT 'private'"],
                  'rooms'=>['owner_id'=>'TEXT'], 'players'=>['user_id'=>'TEXT']] as $table=>$columns) {
            $existing=array_column(query('PRAGMA table_info('.$table.')')->fetchAll(),'name');
            foreach ($columns as $column=>$type) if (!in_array($column,$existing,true)) $db->exec("ALTER TABLE $table ADD COLUMN $column $type");
        }
        query("INSERT OR REPLACE INTO settings VALUES ('community_schema','1')");
        $db->exec('CREATE INDEX IF NOT EXISTS pulse_players_user ON players(user_id,room_id); CREATE UNIQUE INDEX IF NOT EXISTS pulse_room_account ON players(room_id,user_id) WHERE user_id IS NOT NULL;');
        $db->exec('COMMIT');
    }
    roomReportSchema();
    formsSchema();
}
function communityUser(?array $row): ?array {
    if (!$row) return null;
    return array_intersect_key($row,array_flip(['id','name','login','role','active','issuer','external_id']));
}
function communityStaff(): void {
    global $me;
    if (!$me) fail('Войдите в свой аккаунт.',401);
    if (!in_array($me['role'],['admin','moderator'],true)) fail('Недостаточно прав.',403);
}
function communityAudit(string $event,string $target,array $details=[]): void {
    global $me;
    query('INSERT INTO pulse_audit(actor_id,event,target_id,details,created_at) VALUES (?,?,?,?,?)',[$me['id']??'system',$event,$target,json_encode($details,JSON_UNESCAPED_UNICODE),time()]);
}
function communityLogin(array $user): void {
    session_start(); session_regenerate_id(true); $_SESSION['pulse_uid']=$user['id'];
    $_SESSION['admin']=false; $_SESSION['csrf']=bin2hex(random_bytes(24)); session_write_close();
}
function communityOwn(array $row): bool {
    global $me;
    return $me && (($row['owner_id']??null)===$me['id'] || (empty($row['owner_id']) && $me['role']==='admin'));
}
function communityQuiz(string $id,bool $published=false): array {
    $q=query('SELECT * FROM quizzes WHERE id=?',[$id])->fetch();
    if (!$q || (!communityOwn($q) && !($published && $q['visibility']==='public'))) fail('Опросник не найден.',404);
    return $q;
}
function communityUrl(string $url): string {
    $p=parse_url($url);
    if (!$p || !in_array($p['scheme']??'', ['http','https'],true) || empty($p['host']) || isset($p['user']) || isset($p['pass']) || isset($p['query']) || isset($p['fragment'])) throw new RuntimeException('Неверный адрес марафона.');
    return rtrim($url,'/');
}
function communityBridge(string $action,array $body=[],bool $throw=false): array {
    $base=communityUrl(getenv('MARATHON_URL')?:''); $key=getenv('PULSE_BRIDGE_SECRET')?:'';
    if (strlen($key)<32) {
        if($throw)throw new RuntimeException('Связь с марафоном ещё не настроена в GitDeck.',503);
        fail('Связь с марафоном ещё не настроена в GitDeck.',503);
    }
    $context=stream_context_create(['http'=>['method'=>'POST','header'=>"Content-Type: application/json\r\nX-Pulse-Bridge: $key\r\nConnection: close\r\n",'content'=>json_encode($body),'timeout'=>12,'ignore_errors'=>true,'follow_location'=>0], 'ssl'=>['verify_peer'=>true,'verify_peer_name'=>true]]);
    $response=@file_get_contents($base.'/api.php?action='.$action,false,$context,0,3000000);
    $status=$http_response_header[0]??'';
    $data=$response!==false?json_decode($response,true):null;
    if (!str_contains($status,' 200 ') || !is_array($data)) {
        // Only a response from the authenticated identity endpoint means an unlinked account.
        $unlinked=$action==='pulse_telegram_identity'&&str_contains($status,' 403 ')&&
            (($data['code']??'')==='telegram_not_linked'||($data['error']??'')==='Telegram не привязан к активному аккаунту марафона.');
        if($throw&&$unlinked)throw new DomainException('Telegram не привязан к активному аккаунту марафона.',403);
        $message=$unlinked?'Telegram больше не привязан к активному аккаунту марафона. Начните вход заново.':'Не удалось проверить аккаунт в марафоне. Обновите оба сайта и проверьте их подключение в GitDeck.';
        if($throw)throw new RuntimeException($message,502);
        fail($message,502);
    }
    return $data;
}
function communityImport(array $source): array {
    $issuer=$source['issuer']??''; $users=$source['users']??null;
    if (!preg_match('/^[a-f0-9]{32}$/',$issuer) || !is_array($users) || count($users)>20000) fail('Некорректный список марафона.',502);
    $count=0;
    foreach ($users as $u) {
        if (!is_string($u['id']??null) || !preg_match('/^[a-f0-9]{24}$/',$u['id']) || !is_string($u['name']??null) || !in_array($u['role']??'', ['admin','moderator','participant'],true)) fail('Некорректный участник марафона.',502);
        $id='m_'.substr(hash('sha256',$issuer.':'.$u['id']),0,30);
        query('INSERT INTO pulse_accounts(id,name,role,issuer,external_id,active,created_at) VALUES (?,?,?,?,?,?,?) ON CONFLICT(issuer,external_id) DO UPDATE SET name=excluded.name,role=excluded.role,active=excluded.active',[$id,mb_substr($u['name'],0,80),$u['role'],$issuer,$u['id'],!empty($u['active'])?1:0,time()]);
        $count++;
    }
    return ['imported'=>$count];
}
function communityHandle(string $action,array $input): void {
    global $db,$me,$admin;
    roomReportHandle($action,$input);
    formsHandle($action,$input);
    if($action==='receive_marathon'){
        $key=getenv('PULSE_BRIDGE_SECRET')?:'';
        if(strlen($key)<32||!getenv('MARATHON_URL')||!hash_equals($key,$_SERVER['HTTP_X_PULSE_BRIDGE']??''))fail('Запрос не подтверждён.',403);
        $db->exec('BEGIN IMMEDIATE');$result=communityImport($input);communityAudit('receive_marathon','directory',$result);$db->exec('COMMIT');out($result);
    }
    if(in_array($action,['pulse_telegram_request','pulse_telegram_status'],true)){
        require_once __DIR__.'/pulse-telegram.php';pulseTelegramSchema();
        if(!getenv('TELEGRAM_BOT_TOKEN')||!preg_match('/^[a-zA-Z0-9_]{5,32}$/',getenv('TELEGRAM_BOT_USERNAME')?:'')||!getenv('MARATHON_URL')||!getenv('PULSE_BRIDGE_SECRET'))fail('Подключите отдельного Telegram-бота Пульса в GitDeck.',503);
        if($action==='pulse_telegram_request'){
            session_start();$sessionHash=hash('sha256',session_id());session_write_close();
            $token=bin2hex(random_bytes(24));$expires=time()+600;
            query('DELETE FROM pulse_telegram_requests WHERE expires_at<? OR session_hash=?',[time(),$sessionHash]);
            query('INSERT INTO pulse_telegram_requests(token_hash,session_hash,expires_at) VALUES (?,?,?)',[hash('sha256',$token),$sessionHash,$expires]);
            out(['token'=>$token,'expires'=>$expires,'url'=>'https://t.me/'.getenv('TELEGRAM_BOT_USERNAME').'?start=pl_'.$token]);
        }
        $token=cleanText($input['token']??'',48);session_start();$sessionHash=hash('sha256',session_id());session_write_close();
        $r=query('SELECT * FROM pulse_telegram_requests WHERE token_hash=?',[hash('sha256',$token)])->fetch();
        if(!$r||!hash_equals($r['session_hash'],$sessionHash)||$r['expires_at']<time()||$r['consumed'])fail('Запрос истёк. Начните вход заново.',403);
        if(!$r['user_id'])out(['pending'=>true]);
        $identity=communityBridge('pulse_telegram_identity',['telegram_id'=>$r['telegram_id']]);
        $db->exec('BEGIN IMMEDIATE');
        $fresh=query('SELECT * FROM pulse_telegram_requests WHERE token_hash=?',[hash('sha256',$token)])->fetch();
        if(!$fresh||$fresh['consumed']||$fresh['expires_at']<time())fail('Запрос уже использован или истёк.',403);
        communityImport($identity);
        $u=query('SELECT * FROM pulse_accounts WHERE issuer=? AND external_id=? AND active=1',[$identity['issuer'],$identity['users'][0]['id']??''])->fetch();
        if(!$u||$u['id']!==$r['user_id'])fail('Привязка Telegram изменилась. Начните вход заново.',403);
        query('UPDATE pulse_telegram_requests SET consumed=1,telegram_id=NULL WHERE token_hash=?',[$r['token_hash']]);$db->exec('COMMIT');communityLogin($u);out(['ok'=>true]);
    }
    if ($action==='catalog') {
        $list=query("SELECT q.id,q.title,q.description,q.questions,q.created_at,a.name AS author FROM quizzes q LEFT JOIN pulse_accounts a ON a.id=q.owner_id WHERE q.visibility='public' ORDER BY q.created_at DESC LIMIT 500")->fetchAll();
        foreach ($list as &$q) { $raw=json_decode($q['questions'],true); $qs=$raw['questions']??$raw;$q['count']=count($qs);$q['mode']=$raw['mode']??'classic';unset($q['questions']); } unset($q);
        out(['quizzes'=>$list]);
    }
    if ($action==='register' || $action==='account_login') {
        $login=strtolower(cleanText($input['login']??'',40)); $password=$input['password']??'';
        if (!preg_match('/^[a-z0-9_.-]{3,40}$/',$login)||!is_string($password)||strlen($password)<8||strlen($password)>200) fail('Логин: 3–40 латинских символов. Пароль: от 8 символов.');
        $ip='account:'.($_SERVER['REMOTE_ADDR']??'local');
        $db->exec('BEGIN IMMEDIATE');
        $attempt=query('SELECT * FROM login_attempts WHERE ip=?',[$ip])->fetch();
        if ($attempt && $attempt['attempts']>=10 && $attempt['updated_at']>time()-900) fail('Повторите вход через 15 минут.',429);
        $user=query('SELECT * FROM pulse_accounts WHERE login=?',[$login])->fetch();
        if ($action==='register') {
            if ($user) fail('Этот логин уже занят.',409);
            $id=bin2hex(random_bytes(16));$name=cleanText($input['name']??'',80);
            query('INSERT INTO pulse_accounts(id,name,login,password,created_at) VALUES (?,?,?,?,?)',[$id,$name,$login,password_hash($password,PASSWORD_DEFAULT),time()]);
            $user=query('SELECT * FROM pulse_accounts WHERE id=?',[$id])->fetch();
        } elseif (!$user || !$user['active'] || !password_verify($password,$user['password']??'')) {
            $n=$attempt && $attempt['updated_at']>time()-900?(int)$attempt['attempts']+1:1;
            query('INSERT OR REPLACE INTO login_attempts VALUES (?,?,?)',[$ip,$n,time()]);$db->exec('COMMIT');fail('Неверный логин или пароль.',401);
        }
        query('DELETE FROM login_attempts WHERE ip=?',[$ip]);$db->exec('COMMIT');communityLogin($user);out(['ok'=>true]);
    }
    if ($action==='marathon_begin') {
        if (!getenv('MARATHON_URL') || strlen(getenv('PULSE_BRIDGE_SECRET')?:'')<32) fail('Сначала подключите марафон в GitDeck.',503);
        $state=bin2hex(random_bytes(32));$verifier=bin2hex(random_bytes(32));
        session_start();$_SESSION['marathon_auth']=['state'=>$state,'verifier'=>$verifier,'expires'=>time()+600];session_write_close();
        out(['url'=>communityUrl(getenv('MARATHON_URL')).'/?pulse_state='.$state.'&pulse_challenge='.hash('sha256',$verifier)]);
    }
    if ($action==='marathon_complete') {
        session_start();$auth=$_SESSION['marathon_auth']??[];unset($_SESSION['marathon_auth']);session_write_close();
        if (($auth['expires']??0)<time() || !is_string($input['state']??null) || !hash_equals($auth['state']??'',$input['state'])) fail('Вход истёк. Повторите вход через марафон.',403);
        $result=communityBridge('pulse_exchange',['code'=>$input['code']??'','state'=>$input['state'],'verifier'=>$auth['verifier']]);
        $db->exec('BEGIN IMMEDIATE');communityImport($result);$u=$result['users'][0]??[];
        $user=query('SELECT * FROM pulse_accounts WHERE issuer=? AND external_id=? AND active=1',[$result['issuer'],$u['id']??''])->fetch();
        if (!$user) fail('Аккаунт недоступен.',403);
        $db->exec('COMMIT');communityLogin($user);out(['ok'=>true]);
    }
    if ($action==='sync_marathon') {
        communityStaff();$result=communityBridge('pulse_directory');$db->exec('BEGIN IMMEDIATE');
        $count=communityImport($result);communityAudit('sync_marathon','directory',$count);$db->exec('COMMIT');out($count);
    }
    if ($action==='publish' || $action==='clone_quiz') {
        hostOnly();$q=communityQuiz((string)($input['id']??''),$action==='clone_quiz');
        if ($action==='publish') { $visibility=$input['visibility']??'private';if (!in_array($visibility,['private','public'],true)) fail('Некорректная видимость.');query('UPDATE quizzes SET visibility=? WHERE id=?',[$visibility,$q['id']]);out(['ok'=>true]); }
        $id=bin2hex(random_bytes(8));query('INSERT INTO quizzes(id,title,description,questions,created_at,owner_id,visibility) VALUES (?,?,?,?,?,?,?)',[$id,mb_substr($q['title'].' · копия',0,100),$q['description'],$q['questions'],time(),$me['id'],'private']);out(['id'=>$id]);
    }
    if ($action==='directory') {
        communityStaff();out(['users'=>query('SELECT id,name,role,active,issuer,external_id FROM pulse_accounts ORDER BY name')->fetchAll()]);
    }
    if ($action==='assessments') {
        hostOnly();$staff=in_array($me['role'],['admin','moderator'],true);
        $rows=$staff?query('SELECT * FROM assessments ORDER BY held_on DESC,created_at DESC')->fetchAll():query('SELECT a.* FROM assessments a JOIN assessment_scores s ON s.assessment_id=a.id WHERE s.user_id=? AND (a.source_form_id IS NULL OR EXISTS(SELECT 1 FROM pulse_forms f WHERE f.id=a.source_form_id AND f.published=1)) ORDER BY a.held_on DESC,a.created_at DESC',[$me['id']])->fetchAll();
        foreach ($rows as &$a) {
            $a['can_link']=!empty($a['source_room_id'])&&communityOwn(query('SELECT * FROM rooms WHERE id=?',[$a['source_room_id']])->fetch()?:[]);
            $scores=$staff?query('SELECT s.*,u.name FROM assessment_scores s JOIN pulse_accounts u ON u.id=s.user_id WHERE s.assessment_id=? ORDER BY u.name',[$a['id']])->fetchAll():query('SELECT s.*,u.name FROM assessment_scores s JOIN pulse_accounts u ON u.id=s.user_id WHERE s.assessment_id=? AND s.user_id=?',[$a['id'],$me['id']])->fetchAll();
            foreach ($scores as &$s) {$s['percent']=round((float)$s['points']/(float)$a['max_points']*100,2);unset($s['editor_id']);}unset($s);$a['scores']=$scores;
        }unset($a);
        $games=query('SELECT p.name,p.score,r.id,r.code,r.quiz,r.status,r.created_at FROM players p JOIN rooms r ON r.id=p.room_id WHERE p.user_id=? ORDER BY r.created_at DESC LIMIT 100',[$me['id']])->fetchAll();
        foreach($games as &$g){$q=json_decode($g['quiz'],true);$g['title']=$q['title'];unset($g['quiz']);}unset($g);
        out(['assessments'=>$rows,'games'=>$games]);
    }
    if ($action==='save_assessment') {
        communityStaff();$title=cleanText($input['title']??'',100);$maximum=$input['max_points']??null;
        if(!is_numeric($maximum)||!is_finite((float)$maximum)||(float)$maximum<=0||(float)$maximum>100000000)fail('Максимум баллов должен быть больше нуля.');
        $date=$input['held_on']??date('Y-m-d');$d=is_string($date)?DateTimeImmutable::createFromFormat('!Y-m-d',$date):false;if(!$d||$d->format('Y-m-d')!==$date)fail('Укажите дату теста.');
        $id=$input['id']??bin2hex(random_bytes(8));if(!is_string($id)||!preg_match('/^[a-f0-9]{16}$/',$id))fail('Некорректный тест.');
        $scores=$input['scores']??[];if(!is_array($scores)||count($scores)>20000)fail('Слишком много результатов.');
        $db->exec('BEGIN IMMEDIATE');$old=query('SELECT * FROM assessments WHERE id=?',[$id])->fetch();
        if($old && (int)($input['revision']??0)!==(int)$old['revision'])fail('Ведомость уже изменена. Откройте её заново.',409);
        $seen=[];
        foreach($scores as $s){$uid=$s['user_id']??'';$points=$s['points']??null;
            if(!is_string($uid)||isset($seen[$uid])||!query('SELECT id FROM pulse_accounts WHERE id=?',[$uid])->fetchColumn())fail('Некорректный участник.');$seen[$uid]=true;
            if(!is_numeric($points)||!is_finite((float)$points)||(float)$points<0||(float)$points>(float)$maximum)fail('Баллы: от 0 до максимума теста.');
            if(!is_string($s['note']??'')||mb_strlen($s['note']??'')>500)fail('Примечание: до 500 символов.');
        }
        query('INSERT INTO assessments(id,title,max_points,owner_id,held_on,created_at) VALUES (?,?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,max_points=excluded.max_points,held_on=excluded.held_on,revision=assessments.revision+1',[$id,$title,(float)$maximum,$me['id'],$date,time()]);
        if($old&&(!empty($old['source_room_id'])||!empty($old['source_form_id'])))query('UPDATE assessments SET source_edited=1 WHERE id=?',[$id]);
        // Empty cells mean not entered, whereas a numeric zero is a real result.
        query('DELETE FROM assessment_scores WHERE assessment_id=?',[$id]);
        foreach($scores as $s)query('INSERT INTO assessment_scores VALUES (?,?,?,?,?,?)',[$id,$s['user_id'],(float)$s['points'],trim($s['note']??''),time(),$me['id']]);
        communityAudit('save_assessment',$id,['before'=>$old?:null,'participants'=>count($scores),'max_points'=>(float)$maximum]);$db->exec('COMMIT');out(['id'=>$id]);
    }
    if ($action==='delete_assessment') {
        communityStaff();$id=(string)($input['id']??'');$db->exec('BEGIN IMMEDIATE');
        $a=query('SELECT * FROM assessments WHERE id=?',[$id])->fetch();if(!$a)fail('Тест не найден.',404);
        if((int)($input['revision']??0)!==(int)$a['revision'])fail('Ведомость уже изменена. Откройте её заново.',409);
        communityAudit('delete_assessment',$id,['assessment'=>$a,'scores'=>query('SELECT * FROM assessment_scores WHERE assessment_id=?',[$id])->fetchAll()]);
        query('DELETE FROM assessment_scores WHERE assessment_id=?',[$id]);query('DELETE FROM assessments WHERE id=?',[$id]);$db->exec('COMMIT');out(['ok'=>true]);
    }
    if ($action==='link_player') {
        communityStaff();$db->exec('BEGIN IMMEDIATE');$p=query('SELECT p.*,r.owner_id FROM players p JOIN rooms r ON r.id=p.room_id WHERE p.id=?',[$input['player_id']??''])->fetch();
        if(!$p||!communityOwn($p))fail('Участник игры не найден.',404);
        $u=query('SELECT * FROM pulse_accounts WHERE id=?',[$input['user_id']??''])->fetch();if(!$u)fail('Аккаунт не найден.',404);
        if(query('SELECT id FROM players WHERE room_id=? AND user_id=? AND id<>?',[$p['room_id'],$u['id'],$p['id']])->fetchColumn())fail('Этот аккаунт уже связан с другим участником этой игры.',409);
        communityAudit('link_player',$p['id'],['before'=>$p['user_id'],'after'=>$u['id']]);query('UPDATE players SET user_id=? WHERE id=?',[$u['id'],$p['id']]);
        query('UPDATE rooms SET link_revision=link_revision+1 WHERE id=?',[$p['room_id']]);
        $report=syncRoomReport(query('SELECT * FROM rooms WHERE id=?',[$p['room_id']])->fetch());$db->exec('COMMIT');out(['ok'=>true]+$report);
    }
    if ($action==='room_participants') {
        communityStaff();$r=query('SELECT * FROM rooms WHERE id=?',[$_GET['room']??''])->fetch();if(!$r||!communityOwn($r))fail('Игра не найдена.',404);
        $quiz=json_decode($r['quiz'],true);$maximum=roomReportMaximum($r);$report=query('SELECT id,max_points,source_max_override FROM assessments WHERE source_room_id=?',[$r['id']])->fetch();
        out(['room'=>['id'=>$r['id'],'title'=>$quiz['title'],'code'=>$r['code'],'status'=>$r['status'],'created_at'=>(int)$r['created_at'],'revision'=>(int)$r['link_revision']], 'maximum'=>$maximum,'report'=>$report?:null,'players'=>query('SELECT p.id,p.name,p.score,p.user_id,a.name AS account_name FROM players p LEFT JOIN pulse_accounts a ON a.id=p.user_id WHERE p.room_id=? ORDER BY p.score DESC,p.name',[$r['id']])->fetchAll()]);
    }
}
