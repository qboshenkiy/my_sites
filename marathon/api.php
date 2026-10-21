<?php
declare(strict_types=1);
ini_set('display_errors','0');
require __DIR__.'/lib/core.php';
$GLOBALS['audit_transport']=['source'=>'site','request_id'=>bin2hex(random_bytes(8))];
header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');
// Container probes must not create long-lived guest sessions.
if($_SERVER['REQUEST_METHOD']==='GET'&&($_GET['action']??'')==='health'){
    try{db();echo json_encode(['ok'=>true]);}catch(Throwable $e){http_response_code(503);echo json_encode(['ok'=>false]);}exit;
}
sessionStart();$uid=$_SESSION['uid']??null;$epoch=$_SESSION['epoch']??0;$clientChannel=$_SESSION['channel']??'site';$csrf=$_SESSION['csrf']??=bin2hex(random_bytes(24));$sessionHash=hash('sha256',session_id());session_write_close();
function fail(string $message,int $status=400): never { http_response_code($status);echo json_encode(['error'=>$message],JSON_UNESCAPED_UNICODE);exit; }
function send(array $data): never { echo json_encode($data,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);exit; }
function text(mixed $value,int $limit,bool $required=true): string { if(!is_string($value))fail('Некорректный текст.');$v=trim($value);if(($required&&$v==='')||mb_strlen($v)>$limit)fail('Заполните текст, максимум '.$limit.' символов.');return $v; }
function guard(bool $admin=false): array { global $me;if(!$me)fail('Войдите в систему.',401);if($me['role']==='participant'||($admin&&$me['role']!=='admin'))fail('Недостаточно прав.',403);return $me; }
function number(mixed $value,int $min,int $max): int { $v=filter_var($value,FILTER_VALIDATE_INT);if($v===false||$v<$min||$v>$max)fail('Некорректное число.');return $v; }
function assertInputRound(string $id,array $input): void {
    $current=(int)(activeRound($id)['number']??1);
    $week=(int)($input['week']??0);if(!$week&&isset($input['date'])){$c=calendar($id);$d=DateTimeImmutable::createFromFormat('!Y-m-d',(string)$input['date']);if($d)$week=intdiv((int)(new DateTimeImmutable($c['start']))->diff($d)->format('%r%a'),7)+1;}
    if($week>=1&&$week<=22){$cycle=weekResults($id)[$week-1]['cycle'];if(($cycle>1&&!isset($input['cycle']))||(isset($input['cycle'])&&(int)$input['cycle']!==$cycle))fail('Круг недели изменился. Обновите страницу.',409);}
    if(($current>1&&!isset($input['round']))||(isset($input['round'])&&(int)$input['round']!==$current))fail('Круг изменился. Обновите страницу и проверьте план.',409);
}
function loginAs(string $id,string $channel='site'): void { $u=user($id);sessionStart();session_regenerate_id(true);$_SESSION['uid']=$id;$_SESSION['channel']=$channel;$_SESSION['epoch']=(int)$u['session_epoch'];$_SESSION['csrf']=bin2hex(random_bytes(24));session_write_close();marathonLogEvent('login_success',['user_id'=>$u['id'],'name'=>$u['name'],'role'=>$u['role'],'channel'=>$channel]); }
try {
    if(!extension_loaded('pdo_sqlite')||!extension_loaded('mbstring'))fail('На сервере нужны PHP-модули pdo_sqlite и mbstring.',503);
    db();$me=$uid?user($uid):null;if($me&&(!(int)$me['active']||(int)$me['session_epoch']!==(int)$epoch))$me=null;if($me&&$clientChannel==='miniapp')$GLOBALS['audit_transport']['channel']='miniapp';
    $action=$_GET['action']??'bootstrap';$input=[];
    require __DIR__.'/lib/pulse.php';pulseHandle($action,$me?:null);
    if($_SERVER['REQUEST_METHOD']==='POST') {
        if((int)($_SERVER['CONTENT_LENGTH']??0)>100000)fail('Запрос слишком большой.',413);
        if(!hash_equals($csrf,$_SERVER['HTTP_X_CSRF_TOKEN']??''))fail('Обновите страницу и повторите.',403);
        $input=json_decode(file_get_contents('php://input'),true);if(!is_array($input))fail('Некорректный запрос.');
    } elseif(!in_array($action,['bootstrap','overview','profile','audit','export','export_xlsx','archived_users','round_history'],true))fail('Нужен POST.',405);
    if($action==='client_log'){
        $event=$input['event']??'';if(!in_array($event,['visit','client_error'],true))fail('Неизвестный тип журнала.');
        $details=['page'=>parse_url((string)($input['page']??''),PHP_URL_PATH)?:'','channel'=>$clientChannel];if($me){$details['user_id']=$me['id'];$details['name']=$me['name'];$details['role']=$me['role'];}
        if($event==='client_error'){$details['message']=$input['message']??'Ошибка браузера';$details['source']=basename((string)($input['source']??''));$details['line']=filter_var($input['line']??0,FILTER_VALIDATE_INT)?:0;$details['status']=filter_var($input['status']??0,FILTER_VALIDATE_INT)?:0;}
        marathonLogEvent($event,$details);send(['ok'=>true]);
    }
    if($action==='bootstrap')send(['user'=>$me?publicUser($me):null,'csrf'=>$csrf,'configured'=>(bool)sql("SELECT id FROM users WHERE role='admin' LIMIT 1")->fetchColumn(),'marathon'=>visibleCalendar(calendar($me&&$me['role']==='participant'?$me['id']:null),$me&&$me['role']==='admin'),'pulse'=>['configured'=>(bool)(getenv('PULSE_URL')&&getenv('PULSE_BRIDGE_SECRET')),'url'=>getenv('PULSE_URL')?:null],'telegram'=>['configured'=>(bool)(getenv('TELEGRAM_BOT_TOKEN')&&getenv('TELEGRAM_BOT_USERNAME')),'username'=>getenv('TELEGRAM_BOT_USERNAME')?:null,'miniapp_url'=>telegramMiniAppUrl()]]);
    if($action==='setup'||$action==='login') {
        $login=strtolower(text($input['login']??'',40));$password=text($input['password']??'',200);
        if(!preg_match('/^[a-z0-9_.-]{3,40}$/',$login)||strlen($password)<8)fail('Логин: 3–40 латинских символов. Пароль: минимум 8 символов.');
        db()->exec('BEGIN IMMEDIATE');
        if($action==='setup') {
            if(sql("SELECT id FROM users WHERE role='admin'")->fetchColumn())fail('Администратор уже создан.',409);
            $id=bin2hex(random_bytes(12));$name=text($input['name']??'Администратор',80);
            sql('INSERT INTO users(id,name,login,password,role,created_at) VALUES (?,?,?,?,?,?)',[$id,$name,$login,password_hash($password,PASSWORD_DEFAULT),'admin',time()]);
        } else {
            $ip=$_SERVER['REMOTE_ADDR']??'local';$attempt=sql('SELECT * FROM login_attempts WHERE ip=?',[$ip])->fetch();
            if($attempt&&(int)$attempt['attempts']>=10&&(int)$attempt['updated_at']>time()-900)fail('Повторите вход через 15 минут.',429);
            $u=sql("SELECT * FROM users WHERE login=? AND role IN ('admin','moderator') AND active=1 AND deleted_at IS NULL",[$login])->fetch();
            if(!$u||!password_verify($password,$u['password']??'')) {
                $n=$attempt&&(int)$attempt['updated_at']>time()-900?(int)$attempt['attempts']+1:1;
                sql('INSERT INTO login_attempts VALUES (?,?,?) ON CONFLICT(ip) DO UPDATE SET attempts=excluded.attempts,updated_at=excluded.updated_at',[$ip,$n,time()]);db()->exec('COMMIT');fail('Неверный логин или пароль.',401);
            }
            $id=$u['id'];sql('DELETE FROM login_attempts WHERE ip=?',[$ip]);
        }
        db()->exec('COMMIT');loginAs($id);send(['ok'=>true]);
    }
    if($action==='logout'){sessionStart();$_SESSION=[];session_regenerate_id(true);session_write_close();send(['ok'=>true]);}
    if($action==='telegram_miniapp_login') {
        $token=getenv('TELEGRAM_BOT_TOKEN')?:'';if($token==='')fail('Telegram ещё не настроен администратором.',503);
        $proof=validateTelegramInitData(text($input['init_data']??'',16384),$token);
        db()->exec('BEGIN IMMEDIATE');
        $u=sql('SELECT * FROM users WHERE telegram_id=? AND active=1 AND deleted_at IS NULL',[$proof['telegram_id']])->fetch();
        if(!$u)fail('Этот Telegram не привязан к активному участнику. Получите персональное приглашение у команды марафона и подтвердите привязку в боте.',403);
        $sameMiniApp=$me&&$me['id']===$u['id']&&$clientChannel==='miniapp';
        if(!$sameMiniApp)audit($u['id'],'telegram_miniapp_login',$u['id'],'Вход в Telegram Mini App',['source'=>'telegram','channel'=>'miniapp']);
        db()->exec('COMMIT');if(!$sameMiniApp)loginAs($u['id'],'miniapp');send(['ok'=>true]);
    }
    if($action==='telegram_request') {
        if(!getenv('TELEGRAM_BOT_TOKEN')||!getenv('TELEGRAM_BOT_USERNAME'))fail('Telegram ещё не настроен администратором.');
        $kind=$input['kind']??'login';$target=null;
        if($kind==='invite') {
            if(!$me)fail('Войдите в систему.',401);
            $target=$input['user']??$me['id'];
            if($target!==$me['id'])guard();
            $u=user($target);if(!$u||!(int)$u['active'])fail('Аккаунт не найден.',404);
            if($u['role']!=='participant'&&$target!==$me['id'])guard(true);
            if($u['telegram_id'])fail('Telegram уже привязан к этому аккаунту.');
        } elseif($kind!=='login')fail('Неизвестное действие.');
        $token=bin2hex(random_bytes(24));$expires=time()+($kind==='invite'?86400:300);
        // Only one outstanding invitation per account; each login is tied to this browser session.
        if($target)sql('DELETE FROM requests WHERE user_id=? AND kind=?',[$target,'invite']);
        sql('DELETE FROM requests WHERE expires_at<?',[time()-86400]);
        sql('INSERT INTO requests(token_hash,kind,user_id,session_hash,expires_at) VALUES (?,?,?,?,?)',[hash('sha256',$token),$kind,$target,$kind==='login'?$sessionHash:null,$expires]);
        send(['token'=>$token,'expires'=>$expires,'url'=>'https://t.me/'.getenv('TELEGRAM_BOT_USERNAME').'?start='.($kind==='login'?'a_':'i_').$token]);
    }
    if($action==='telegram_status') {
        $token=text($input['token']??'',48);db()->exec('BEGIN IMMEDIATE');
        $r=sql('SELECT * FROM requests WHERE token_hash=?',[hash('sha256',$token)])->fetch();
        if(!$r||$r['kind']!=='login'||!hash_equals($sessionHash,$r['session_hash']??'')||$r['expires_at']<time()||$r['consumed'])fail('Запрос входа истёк. Создайте новый.');
        if(!$r['approved']){db()->exec('COMMIT');send(['pending'=>true]);}
        $u=user($r['user_id']);if(!$u||!$u['active'])fail('Аккаунт недоступен.',403);
        sql('UPDATE requests SET consumed=1 WHERE token_hash=?',[$r['token_hash']]);db()->exec('COMMIT');loginAs($u['id']);send(['ok'=>true]);
    }
    if(!$me)fail('Войдите в систему.',401);
    if($action==='round_history'){$id=$_GET['user']??$me['id'];if($id!==$me['id'])guard();if(!user($id))fail('Участник не найден.',404);$history=archivedReadingRound($id,number($_GET['round']??0,1,100000));unset($history['raw']);send($history);}
    if($action==='start_round')fail('Повторное чтение относится к отдельной неделе. Обновите сайт или откройте меню бота.');
    if(in_array($action,['delete_week_cycle','restore_week_cycle'],true)){$id=$input['user']??$me['id'];if($id!==$me['id'])guard(true);db()->exec('BEGIN IMMEDIATE');$w=changeWeeklyCycle($id,$me['id'],number($input['week']??0,1,22),number($input['cycle']??0,1,1000000),number($input['active_cycle']??0,1,1000000),$action==='restore_week_cycle');db()->exec('COMMIT');send(['ok'=>true,'week'=>$w]);}
    if($action==='start_week_repeat'){$id=$input['user']??$me['id'];if($id!==$me['id'])guard(true);db()->exec('BEGIN IMMEDIATE');$w=startWeeklyRepeat($id,$me['id'],number($input['week']??0,1,22),number($input['cycle']??0,1,100000));db()->exec('COMMIT');send(['ok'=>true,'week'=>$w]);}
    if(in_array($action,['week_result','complete_week','clear_week_result','add_reading','save_report'],true)){
        assertInputRound($input['user']??$me['id'],$input);
    }
    if($action==='overview'){guard();$list=staff();if($me['role']!=='admin')foreach($list as &$u)$u['weekly']=array_values(array_filter($u['weekly'],fn($w)=>$w['week']<=calendar($u['id'])['current']));unset($u);send(['users'=>$list,'marathon'=>visibleCalendar(calendar(),$me['role']==='admin')]);}
    if($action==='profile') {
        $id=$_GET['user']??$me['id'];if($id!==$me['id'])guard();$u=user($id);if(!$u)fail('Участник не найден.',404);
        $results=stats($id);if($me['role']==='participant')foreach($results['reports'] as &$weekResult)$weekResult['canComplete']=$weekResult['canComplete']&&$weekResult['week']>=calendar($id)['current']-1;unset($weekResult);
        if($me['role']!=='admin'){$limit=calendar($id)['current'];$results['reports']=array_values(array_filter($results['reports'],fn($w)=>$w['week']<=$limit));$results['entries']=array_values(array_filter($results['entries'],fn($e)=>(int)$e['week']<=$limit));$results['legacy']['reports']=array_values(array_filter($results['legacy']['reports'],fn($w)=>(int)$w['week']<=$limit));}
        send(['user'=>publicUser($u),'stats'=>$results,'marathon'=>visibleCalendar(calendar($id),$me['role']==='admin'),'rounds'=>readingRounds($id)]);
    }
    if($action==='add_reading') {
        $id=$input['user']??$me['id'];if($id!==$me['id'])guard();
        $u=user($id);if(!$u||!$u['active'])fail('Участник недоступен.',404);
        $chapters=number($input['chapters']??0,1,100000);$date=text($input['date']??calendar()['today'],10);$title=text($input['title']??'',200,false);$note=text($input['note']??'',1000,false);
        $key=text($input['key']??'',80);if(!preg_match('/^[a-zA-Z0-9_-]{8,80}$/',$key))fail('Некорректный идентификатор записи.');
        db()->exec('BEGIN IMMEDIATE');assertInputRound($id,$input);$result=addReading($id,$me['id'],$chapters,$date,$title,$note,'site','web_'.$id.'_'.$key);db()->exec('COMMIT');send(['ok'=>true,'week'=>$result]);
    }
    if($action==='delete_reading') {
        $r=sql('SELECT * FROM reading_entries WHERE id=?',[$input['id']??''])->fetch();if(!$r)fail('Запись не найдена.',404);
        if($r['user_id']!==$me['id'])guard();db()->exec('BEGIN IMMEDIATE');if(!sql('SELECT id FROM reading_entries WHERE id=?',[$r['id']])->fetchColumn())fail('Запись уже перенесена в историю. Обновите страницу.',409);assertWeekEditable((int)$r['week'],$r['user_id']);$before=auditWeekSnapshot($r['user_id'],(int)$r['week']);sql('DELETE FROM reading_entries WHERE id=?',[$r['id']]);sql('UPDATE reports SET chapters_override=MAX(0,chapters_override-?) WHERE user_id=? AND week=? AND chapters_override IS NOT NULL',[(int)$r['chapters'],$r['user_id'],(int)$r['week']]);syncCompletion($r['user_id'],(int)$r['week']);auditWeekChange($me['id'],'delete_reading',$r['user_id'],(int)$r['week'],'Удалена отметка '.$r['date'],$before,['entry_id'=>$r['id'],'removed_chapters'=>(int)$r['chapters'],'date'=>$r['date']]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='complete_week') {
        if($me['role']!=='admin'&&($input['days']??'')!=='')fail('Дни чтения рассчитываются автоматически. Менять их вручную может только администратор.',403);
        $id=$input['user']??$me['id'];if($id!==$me['id'])guard();$u=user($id);if(!$u||!(int)$u['active']||$u['deleted_at']!==null)fail('Участник недоступен.',404);
        $week=number($input['week']??0,1,22);$days=$me['role']!=='admin'||($input['days']??'')===''?null:number($input['days'],1,3660);
        db()->exec('BEGIN IMMEDIATE');assertInputRound($id,$input);$result=completeWeek($id,$me['id'],$week,$days);db()->exec('COMMIT');send(['ok'=>true,'week'=>$result]);
    }
    if($action==='week_result') {
        if($me['role']!=='admin'&&($input['days']??'')!=='')fail('Менять дни вручную может только администратор.',403);
        $id=$input['user']??$me['id'];if($id!==$me['id'])guard();$u=user($id);if(!$u||!(int)$u['active']||$u['deleted_at']!==null)fail('Участник не найден.',404);$week=number($input['week']??0,1,22);
        db()->exec('BEGIN IMMEDIATE');assertInputRound($id,$input);$w=assertWeekEditable($week,$id);$total=number($input['chapters']??0,0,$w['goal']);
        $before=weekResults($id)[$week-1];
        $days=$me['role']!=='admin'?($total>0?$before['daysManual']:null):(($input['days']??'')===''?null:number($input['days'],$total?1:0,3660));$title=text($input['title']??'',200,false);$note=text($input['note']??'',1000,false);
        $result=saveWeeklyResult($id,$me['id'],$week,$total,$days,$title,$note);db()->exec('COMMIT');send(['ok'=>true,'week'=>$result]);
    }
    if($action==='clear_week_result') {
        $id=$input['user']??$me['id'];if($id!==$me['id'])guard();$u=user($id);if(!$u||!(int)$u['active']||$u['deleted_at']!==null)fail('Участник не найден.',404);$week=number($input['week']??0,1,22);
        db()->exec('BEGIN IMMEDIATE');assertInputRound($id,$input);assertWeekEditable($week,$id);$before=weekResults($id)[$week-1];
        sql('DELETE FROM reading_entries WHERE user_id=? AND week=?',[$id,$week]);sql('DELETE FROM week_completions WHERE user_id=? AND week=?',[$id,$week]);
        sql('UPDATE reports SET chapters_manual=0,chapters_override=NULL,days_manual=NULL,reading_on=NULL,title=CASE WHEN pages>0 OR minutes>0 OR books>0 THEN title ELSE \'\' END,note=CASE WHEN pages>0 OR minutes>0 OR books>0 THEN note ELSE \'\' END,editor_id=?,updated_at=? WHERE user_id=? AND week=?',[$me['id'],time(),$id,$week]);
        sql('DELETE FROM reports WHERE user_id=? AND week=? AND pages=0 AND minutes=0 AND books=0',[$id,$week]);
        auditWeekChange($me['id'],'clear_week_result',$id,$week,'Сброшен результат недели '.$week.': '.$before['chapters'].' глав, '.$before['days'].' дн.',array_intersect_key($before,array_flip(array_keys(auditWeekSnapshot($id,$week)))));$result=weekResults($id)[$week-1];db()->exec('COMMIT');send(['ok'=>true,'week'=>$result]);
    }
    if($action==='week_plan') {
        guard(true);$week=number($input['week']??0,1,22);$books=null;
        if(array_key_exists('books',$input)){
            if(!is_array($input['books'])||count($input['books'])>100)fail('Можно добавить до 100 книг в неделю.');$books=[];$goal=0;
            foreach($input['books'] as $position=>$book){if(!is_array($book))fail('Некорректная книга.');$title=text($book['title']??'',200);$from=number($book['chapter_from']??0,1,100000);$to=number($book['chapter_to']??0,$from,100000);
                foreach($books as $prior){if(mb_strtolower($prior['title'])===mb_strtolower($title)&&$from<=$prior['chapter_to']&&$to>=$prior['chapter_from'])fail('Главы одной книги не должны повторяться в плане недели.');}
                $books[]=['title'=>$title,'chapter_from'=>$from,'chapter_to'=>$to];$goal+=$to-$from+1;
            }
            if(!$books)$goal=number($input['goal']??0,1,100000);if($goal>100000)fail('Недельный план не должен превышать 100000 глав.');
        }else{$goal=number($input['goal']??0,1,100000);$bookGoal=(int)(sql('SELECT SUM(chapter_to-chapter_from+1) FROM week_plan_books WHERE week=?',[$week])->fetchColumn()?:0);if($bookGoal&&$bookGoal!==$goal)fail('План рассчитан по книгам. Измените книги и главы в плане чтения.');}
        db()->exec('BEGIN IMMEDIATE');
        $w=calendar()['calendar'][$week-1];if($week<calendar()['current']&&!$w['reopened'])fail('Откройте завершённую неделю перед изменением плана.');
        foreach(staff() as $u){if($u['round']===1&&$u['weekly'][$week-1]['chapters']>$goal)fail('План меньше уже внесённого результата участника '.$u['name'].'.');}
        if($books!==null){sql('DELETE FROM week_plan_books WHERE week=?',[$week]);foreach($books as $position=>$book)sql('INSERT INTO week_plan_books VALUES (?,?,?,?,?,?)',[bin2hex(random_bytes(12)),$week,$position,$book['title'],$book['chapter_from'],$book['chapter_to']]);}
        sql('UPDATE week_plans SET chapters=? WHERE week=?',[$goal,$week]);foreach(sql('SELECT id FROM users WHERE deleted_at IS NULL')->fetchAll() as $participant)if((int)(activeRound($participant['id'])['number']??1)===1)syncCompletion($participant['id'],$week);audit($me['id'],'week_plan',null,'План недели '.$week.': '.$goal.' глав'.($books?' · '.planBookText($books):''),['week'=>$week,'before'=>['goal'=>$w['goal'],'books'=>$w['books']],'after'=>['goal'=>$goal,'books'=>calendar()['calendar'][$week-1]['books']]]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='week_lock') {
        guard(true);$week=number($input['week']??0,1,22);$open=number($input['open']??0,0,1);db()->exec('BEGIN IMMEDIATE');
        if(isset($input['user'])&&(int)(activeRound($input['user'])['number']??1)>1){$id=text($input['user'],80);$r=activeRound($id);if((int)($input['round']??0)!==(int)$r['number'])fail('Круг изменился. Обновите страницу.',409);$c=calendar($id);if($week>=$c['current'])fail('Открытие нужно только для завершённых недель.');$opened=json_decode($r['opened'],true);$opened=array_values(array_diff($opened,[$week]));if($open)$opened[]=$week;sql('UPDATE reading_rounds SET opened=? WHERE user_id=? AND number=?',[json_encode($opened),$id,$r['number']]);audit($me['id'],'week_lock',$id,'Круг '.$r['number'].', неделя '.$week.($open?' открыта':' закрыта'),['week'=>$week,'round'=>(int)$r['number'],'before'=>['reopened'=>$c['calendar'][$week-1]['reopened']],'after'=>['reopened'=>(bool)$open]]);db()->exec('COMMIT');send(['ok'=>true]);}
        if($week>=calendar()['current'])fail('Открытие нужно только для завершённых недель.');
        $wasOpen=(bool)sql('SELECT reopened FROM week_plans WHERE week=?',[$week])->fetchColumn();sql('UPDATE week_plans SET reopened=? WHERE week=?',[$open,$week]);audit($me['id'],'week_lock',null,'Неделя '.$week.($open?' открыта для исправлений':' закрыта'),['week'=>$week,'before'=>['reopened'=>$wasOpen],'after'=>['reopened'=>(bool)$open]]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='create_user') {
        guard();$role=$input['role']??'participant';if(!in_array($role,['participant','moderator','admin'],true))fail('Неизвестная роль.');if($role!=='participant')guard(true);
        $name=text($input['name']??'',80);$id=bin2hex(random_bytes(12));$login=null;$hash=null;
        if($role!=='participant'){
            $login=strtolower(text($input['login']??'',40));$password=text($input['password']??'',200);
            if(!preg_match('/^[a-z0-9_.-]{3,40}$/',$login)||strlen($password)<8)fail('Логин: 3–40 латинских символов. Пароль: минимум 8 символов.');
            if(sql('SELECT id FROM users WHERE login=?',[$login])->fetchColumn())fail('Логин уже занят.');$hash=password_hash($password,PASSWORD_DEFAULT);
        }
        db()->exec('BEGIN IMMEDIATE');sql('INSERT INTO users(id,name,login,password,role,created_at) VALUES (?,?,?,?,?,?)',[$id,$name,$login,$hash,$role,time()]);audit($me['id'],'create_user',$id,'Создан аккаунт: '.$name,['after'=>auditUserSnapshot(user($id))]);db()->exec('COMMIT');send(['id'=>$id]);
    }
    if($action==='save_report') {
        guard();$id=$input['user']??'';$u=user($id);if(!$u||$u['deleted_at']!==null)fail('Участник не найден.',404);
        $week=number($input['week']??0,1,22);assertWeekEditable($week,$id);
        $pages=number($input['pages']??0,0,100000);$minutes=number($input['minutes']??0,0,10080);$books=number($input['books']??0,0,100);
        $title=text($input['title']??'',200,false);$note=text($input['note']??'',1000,false);
        db()->exec('BEGIN IMMEDIATE');
        assertInputRound($id,$input);assertWeekEditable($week,$id);$before=auditWeekSnapshot($id,$week);
        sql('INSERT INTO reports(user_id,week,pages,minutes,books,title,note,editor_id,updated_at) VALUES (?,?,?,?,?,?,?,?,?) ON CONFLICT(user_id,week) DO UPDATE SET pages=excluded.pages,minutes=excluded.minutes,books=excluded.books,title=excluded.title,note=excluded.note,editor_id=excluded.editor_id,updated_at=excluded.updated_at',[$id,$week,$pages,$minutes,$books,$title,$note,$me['id'],time()]);
        auditWeekChange($me['id'],'save_report',$id,$week,'Неделя '.$week.': '.$pages.' страниц, '.$minutes.' минут, '.$books.' книг',$before,['legacy'=>['pages'=>$pages,'minutes'=>$minutes,'books'=>$books]]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='archived_users') {
        guard(true);send(['users'=>sql('SELECT id,name,role,deleted_at FROM users WHERE deleted_at IS NOT NULL ORDER BY deleted_at DESC,name')->fetchAll()]);
    }
    if($action==='delete_user') {
        guard(true);$id=text($input['user']??'',80);db()->exec('BEGIN IMMEDIATE');$u=user($id);if(!$u)fail('Аккаунт не найден.',404);
        if($id===$me['id'])fail('Нельзя удалить свой аккаунт.');
        if($u['role']==='admin'&&(int)$u['active']&&(int)sql("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1 AND deleted_at IS NULL")->fetchColumn()<=1)fail('Нельзя удалить последнего администратора.');
        sql('UPDATE users SET deleted_at=?,active=0,telegram_id=NULL,telegram_name=NULL,session_epoch=session_epoch+1 WHERE id=?',[time(),$id]);sql('DELETE FROM requests WHERE user_id=?',[$id]);
        audit($me['id'],'delete_user',$id,'Аккаунт удалён в архив: '.$u['name'],['before'=>auditUserSnapshot($u),'after'=>auditUserSnapshot(sql('SELECT * FROM users WHERE id=?',[$id])->fetch())]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='restore_user') {
        guard(true);$id=text($input['user']??'',80);db()->exec('BEGIN IMMEDIATE');$u=sql('SELECT * FROM users WHERE id=? AND deleted_at IS NOT NULL',[$id])->fetch();if(!$u)fail('Аккаунт в архиве не найден.',404);
        sql('UPDATE users SET deleted_at=NULL,active=1 WHERE id=?',[$id]);audit($me['id'],'restore_user',$id,'Аккаунт восстановлен: '.$u['name'],['before'=>auditUserSnapshot($u),'after'=>auditUserSnapshot(sql('SELECT * FROM users WHERE id=?',[$id])->fetch())]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='unlink_telegram') {
        guard(true);$id=text($input['user']??'',80);db()->exec('BEGIN IMMEDIATE');$u=user($id);if(!$u)fail('Аккаунт не найден.',404);
        if(!$u['telegram_id']){db()->exec('COMMIT');send(['ok'=>true]);}
        if($u['role']!=='participant'&&(!$u['login']||!$u['password']))fail('Сначала сохраните логин и пароль сотрудника, чтобы он мог войти после отвязки Telegram.');
        sql('UPDATE users SET telegram_id=NULL,telegram_name=NULL,session_epoch=session_epoch+1 WHERE id=?',[$id]);
        sql('DELETE FROM requests WHERE user_id=?',[$id]);audit($me['id'],'telegram_unlink',$id,'Telegram отвязан от аккаунта: '.$u['name'],['before'=>auditUserSnapshot($u),'after'=>auditUserSnapshot(sql('SELECT * FROM users WHERE id=?',[$id])->fetch())]);db()->exec('COMMIT');
        if($id===$me['id'])loginAs($id);send(['ok'=>true]);
    }
    if($action==='update_user') {
        guard(true);$id=$input['user']??'';$u=user($id);if(!$u)fail('Аккаунт не найден.',404);
        $name=text($input['name']??$u['name'],80);$role=$input['role']??$u['role'];$active=number($input['active']??$u['active'],0,1);
        if(!in_array($role,['participant','moderator','admin'],true))fail('Неизвестная роль.');
        $login=$u['login'];$password=$u['password'];
        if(isset($input['login'])&&trim($input['login'])!==''){$login=strtolower(text($input['login'],40));if(!preg_match('/^[a-z0-9_.-]{3,40}$/',$login))fail('Некорректный логин.');if(sql('SELECT id FROM users WHERE login=? AND id!=?',[$login,$id])->fetchColumn())fail('Этот логин занят.');}
        if(!empty($input['password'])){if(strlen($input['password'])<8)fail('Пароль: минимум 8 символов.');$password=password_hash(text($input['password'],200),PASSWORD_DEFAULT);}
        if($role!=='participant'&&!$u['telegram_id']&&(!$login||!$password))fail('Привяжите Telegram или задайте логин и пароль для сотрудника.');
        db()->exec('BEGIN IMMEDIATE');
        if($u['role']==='admin'&&($role!=='admin'||!$active)&&(int)sql("SELECT COUNT(*) FROM users WHERE role='admin' AND active=1")->fetchColumn()<=1)fail('Нельзя отключить последнего администратора.');
        if($id===$me['id']&&(!$active||$role!=='admin'))fail('Нельзя отключить или понизить свой аккаунт.');
        sql('UPDATE users SET name=?,role=?,active=?,login=?,password=? WHERE id=?',[$name,$role,$active,$login,$password,$id]);audit($me['id'],'update_user',$id,'Изменён аккаунт: '.$name,['before'=>auditUserSnapshot($u),'after'=>auditUserSnapshot(user($id)),'password_changed'=>!empty($input['password'])]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='settings') {
        guard(true);$title=text($input['title']??'',100);$beforeTitle=setting('title');db()->exec('BEGIN IMMEDIATE');sql("UPDATE settings SET value=? WHERE key='title'",[$title]);audit($me['id'],'settings',null,'Изменено название марафона',['before'=>['title'=>$beforeTitle],'after'=>['title'=>$title]]);db()->exec('COMMIT');send(['ok'=>true]);
    }
    if($action==='audit'){
        guard();$cursor=number($_GET['cursor']??0,0,PHP_INT_MAX);$week=number($_GET['week']??0,0,22);$target=isset($_GET['target'])&&$_GET['target']!==''?text($_GET['target'],80):null;$direction=($_GET['direction']??'b')==='n'?'n':'b';
        send(array_merge(auditEvents($cursor,$direction,$target,$week),['people'=>sql('SELECT id,name,deleted_at FROM users ORDER BY name')->fetchAll()]));
    }
    if($action==='export_xlsx'){guard();require __DIR__.'/lib/xlsx.php';exportReading(number($_GET['week']??max(1,min(22,calendar()['current'])),1,22),$me['role']==='admin');}
    if($action==='export') {
        guard();header('Content-Type: text/csv; charset=utf-8');header('Content-Disposition: attachment; filename="marathon-results.csv"');$f=fopen('php://output','w');fwrite($f,"\xEF\xBB\xBF");fputcsv($f,['Участник','Страницы','Минуты','Книги','Недель с отчётом','Telegram привязан'],';', '"','');
        foreach(staff() as $u){$name=preg_match('/^[=+@-]/',$u['name'])?"'".$u['name']:$u['name'];fputcsv($f,[$name,$u['pages'],$u['minutes'],$u['books'],$u['recorded'],$u['telegram_id']?'Да':'Нет'],';', '"','');}exit;
    }
    fail('Действие не найдено.',404);
} catch(DomainException $e){fail($e->getMessage());}catch(Throwable $e){marathonLogEvent('server_error',['action'=>$action??'unknown','error'=>get_class($e),'message'=>$e->getMessage(),'request_id'=>$GLOBALS['audit_transport']['request_id']??'']);fail('Ошибка сервера. Проверьте подключение и повторите.',500);}
