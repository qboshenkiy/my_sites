<?php
declare(strict_types=1);
date_default_timezone_set(getenv('MARATHON_TIMEZONE') ?: 'Asia/Bishkek');
function db(): PDO {
    static $db=null;
    if ($db) return $db;
    $dir=getenv('MARATHON_DATA_DIR') ?: dirname(__DIR__).'/storage';
    if (!is_dir($dir)) mkdir($dir,0700,true);
    $db=new PDO('sqlite:'.$dir.'/marathon.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $db->exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=10000; PRAGMA foreign_keys=ON;
    CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS users(id TEXT PRIMARY KEY,name TEXT NOT NULL,login TEXT UNIQUE,password TEXT,role TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,telegram_id TEXT UNIQUE,telegram_name TEXT,created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS reports(user_id TEXT NOT NULL REFERENCES users(id),week INTEGER NOT NULL,pages INTEGER NOT NULL DEFAULT 0,minutes INTEGER NOT NULL DEFAULT 0,books INTEGER NOT NULL DEFAULT 0,title TEXT NOT NULL DEFAULT \'\',note TEXT NOT NULL DEFAULT \'\',editor_id TEXT NOT NULL REFERENCES users(id),updated_at INTEGER NOT NULL,PRIMARY KEY(user_id,week));
    CREATE TABLE IF NOT EXISTS requests(token_hash TEXT PRIMARY KEY,kind TEXT NOT NULL,user_id TEXT REFERENCES users(id),session_hash TEXT,expires_at INTEGER NOT NULL,approved INTEGER NOT NULL DEFAULT 0,consumed INTEGER NOT NULL DEFAULT 0);
    CREATE TABLE IF NOT EXISTS audit(id INTEGER PRIMARY KEY AUTOINCREMENT,actor_id TEXT,event TEXT NOT NULL,target_id TEXT,details TEXT NOT NULL,created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS login_attempts(ip TEXT PRIMARY KEY,attempts INTEGER NOT NULL,updated_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS bot_updates(id INTEGER PRIMARY KEY,processed_at INTEGER NOT NULL);');
    foreach (['start'=>'2026-10-12','weeks'=>'22','weekly_goal'=>'100','title'=>'22 недели чтения'] as $k=>$v) sql('INSERT OR IGNORE INTO settings VALUES (?,?)',[$k,$v]);
    // Additive migration: retain the old page/minute reports as historical data.
    $db->exec('BEGIN IMMEDIATE');
    try {
        $userColumns=array_column(sql('PRAGMA table_info(users)')->fetchAll(),'name');
        if(!in_array('deleted_at',$userColumns,true))$db->exec('ALTER TABLE users ADD COLUMN deleted_at INTEGER');
        if(!in_array('session_epoch',$userColumns,true))$db->exec('ALTER TABLE users ADD COLUMN session_epoch INTEGER NOT NULL DEFAULT 0');
        $db->exec('UPDATE users SET telegram_id=NULL,telegram_name=NULL WHERE deleted_at IS NOT NULL AND (telegram_id IS NOT NULL OR telegram_name IS NOT NULL)');
        $columns=array_column(sql('PRAGMA table_info(reports)')->fetchAll(),'name');
        if(!in_array('chapters_manual',$columns,true))$db->exec('ALTER TABLE reports ADD COLUMN chapters_manual INTEGER NOT NULL DEFAULT 0');
        if(!in_array('days_manual',$columns,true))$db->exec('ALTER TABLE reports ADD COLUMN days_manual INTEGER');
        if(!in_array('chapters_override',$columns,true))$db->exec('ALTER TABLE reports ADD COLUMN chapters_override INTEGER');
        $db->exec('CREATE TABLE IF NOT EXISTS week_plans(week INTEGER PRIMARY KEY,chapters INTEGER NOT NULL DEFAULT 7,reopened INTEGER NOT NULL DEFAULT 0);
        CREATE TABLE IF NOT EXISTS reading_entries(id TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),week INTEGER NOT NULL,date TEXT NOT NULL,chapters INTEGER NOT NULL,title TEXT NOT NULL,note TEXT NOT NULL,actor_id TEXT NOT NULL REFERENCES users(id),source TEXT NOT NULL,created_at INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS migrations(version INTEGER PRIMARY KEY,created_at INTEGER NOT NULL);');
        $db->exec('CREATE TABLE IF NOT EXISTS week_plan_books(id TEXT PRIMARY KEY,week INTEGER NOT NULL REFERENCES week_plans(week),position INTEGER NOT NULL,title TEXT NOT NULL,chapter_from INTEGER NOT NULL,chapter_to INTEGER NOT NULL);
        CREATE TABLE IF NOT EXISTS week_completions(user_id TEXT NOT NULL REFERENCES users(id),week INTEGER NOT NULL,completed_on TEXT NOT NULL,plan_snapshot TEXT NOT NULL DEFAULT \'[]\',PRIMARY KEY(user_id,week));');
        $db->exec('CREATE TABLE IF NOT EXISTS telegram_reading_requests(token_hash TEXT PRIMARY KEY,user_id TEXT NOT NULL REFERENCES users(id),telegram_id TEXT NOT NULL,session_epoch INTEGER NOT NULL,chapters INTEGER NOT NULL,snapshot TEXT NOT NULL,expires_at INTEGER NOT NULL,consumed INTEGER NOT NULL DEFAULT 0)');
        for($week=1;$week<=22;$week++)sql('INSERT OR IGNORE INTO week_plans(week) VALUES (?)',[$week]);
        sql('INSERT OR IGNORE INTO migrations VALUES (2,?)',[time()]);
        sql('INSERT OR IGNORE INTO migrations VALUES (3,?)',[time()]);
        sql('INSERT OR IGNORE INTO migrations VALUES (4,?)',[time()]);
        if(!sql('SELECT version FROM migrations WHERE version=5')->fetchColumn()){
            // Participant-owned durations were automatically frozen from message dates.
            $db->exec("UPDATE reports SET days_manual=NULL WHERE days_manual<=0 OR (editor_id=user_id AND (user_id IN (SELECT id FROM users WHERE role='participant') OR (chapters_override IS NULL AND chapters_manual=0 AND EXISTS (SELECT 1 FROM reading_entries e WHERE e.user_id=reports.user_id AND e.week=reports.week AND e.source='telegram'))))");
            sql('INSERT INTO migrations VALUES (5,?)',[time()]);
        }
        $db->exec('COMMIT');
    }catch(Throwable $e){$db->exec('ROLLBACK');throw $e;}
    return $db;
}
function sql(string $query,array $params=[]): PDOStatement { $s=db()->prepare($query);$s->execute($params);return $s; }
function setting(string $key): string { return (string)sql('SELECT value FROM settings WHERE key=?',[$key])->fetchColumn(); }
function calendar(): array {
    $start=new DateTimeImmutable(setting('start'));$weeks=(int)setting('weeks');$end=$start->modify('+'.($weeks*7-1).' days');
    $today=new DateTimeImmutable(getenv('MARATHON_TEST_TODAY') ?: 'today');$offset=(int)$start->diff($today)->format('%r%a');
    $current=$offset<0?0:($offset>=$weeks*7?$weeks+1:intdiv($offset,7)+1);
    $plans=sql('SELECT * FROM week_plans ORDER BY week')->fetchAll();
    $books=[];foreach(sql('SELECT * FROM week_plan_books ORDER BY week,position')->fetchAll() as $book){$book['chapter_from']=(int)$book['chapter_from'];$book['chapter_to']=(int)$book['chapter_to'];$book['chapters']=$book['chapter_to']-$book['chapter_from']+1;$books[(int)$book['week']][]=$book;}
    $items=[];for($i=1;$i<=$weeks;$i++) { $s=$start->modify('+'.(($i-1)*7).' days');$plan=$plans[$i-1];$items[]=['number'=>$i,'start'=>$s->format('Y-m-d'),'end'=>$s->modify('+6 days')->format('Y-m-d'),'goal'=>(int)$plan['chapters'],'books'=>$books[$i]??[],'canComplete'=>$i<=$current,'reopened'=>(bool)$plan['reopened'],'editable'=>$i<=$current&&($i===$current||(bool)$plan['reopened'])]; }
    return ['title'=>setting('title'),'start'=>$start->format('Y-m-d'),'end'=>$end->format('Y-m-d'),'today'=>$today->format('Y-m-d'),'current'=>$current,'weeks'=>$weeks,'goal'=>$items[max(0,min(21,$current-1))]['goal'],'legacyGoal'=>(int)setting('weekly_goal'),'calendar'=>$items];
}
function publicUser(array $u): array { unset($u['password'],$u['session_epoch']);return $u; }
function user(string $id): ?array { return sql('SELECT * FROM users WHERE id=? AND deleted_at IS NULL',[$id])->fetch() ?: null; }
function audit(string $actor,string $event,?string $target,string $details): void { sql('INSERT INTO audit(actor_id,event,target_id,details,created_at) VALUES (?,?,?,?,?)',[$actor,$event,$target,$details,time()]); }
function legacyStats(string $id): array {
    $reports=sql('SELECT r.*,u.name AS editor FROM reports r JOIN users u ON u.id=r.editor_id WHERE r.user_id=? ORDER BY week',[$id])->fetchAll();
    $goal=(int)setting('weekly_goal');$pages=0;$minutes=0;$books=0;$done=0;
    foreach($reports as $r) {$pages+=(int)$r['pages'];$minutes+=(int)$r['minutes'];$books+=(int)$r['books'];if((int)$r['pages']>=$goal)$done++;}
    return ['reports'=>$reports,'pages'=>$pages,'minutes'=>$minutes,'books'=>$books,'recorded'=>count($reports),'goalWeeks'=>$done,'goal'=>$goal,'progress'=>min(100,(int)round($pages/max(1,$goal*(int)setting('weeks'))*100))];
}
function legacyStaff(): array {
    return sql("SELECT u.id,u.name,u.role,u.active,u.telegram_id,u.telegram_name,u.login,u.created_at,COALESCE(SUM(r.pages),0) AS pages,COALESCE(SUM(r.minutes),0) AS minutes,COALESCE(SUM(r.books),0) AS books,COUNT(r.week) AS recorded FROM users u LEFT JOIN reports r ON r.user_id=u.id WHERE u.deleted_at IS NULL GROUP BY u.id ORDER BY pages DESC,u.name")->fetchAll();
}
function weekResults(string $id): array {
    $c=calendar();$reports=sql('SELECT r.*,u.name AS editor FROM reports r JOIN users u ON u.id=r.editor_id WHERE r.user_id=?',[$id])->fetchAll();
    $daily=sql('SELECT week,SUM(chapters) AS chapters,COUNT(DISTINCT date) AS days FROM reading_entries WHERE user_id=? GROUP BY week',[$id])->fetchAll();
    $rmap=[];$dmap=[];foreach($reports as $r)$rmap[(int)$r['week']]=$r;foreach($daily as $d)$dmap[(int)$d['week']]=$d;
    $completions=[];foreach(sql('SELECT * FROM week_completions WHERE user_id=?',[$id])->fetchAll() as $row)$completions[(int)$row['week']]=$row;
    $result=[];
    foreach($c['calendar'] as $w){$n=$w['number'];$r=$rmap[$n]??[];$d=$dmap[$n]??[];$chapters=isset($r['chapters_override'])?(int)$r['chapters_override']:(int)($r['chapters_manual']??0)+(int)($d['chapters']??0);$days=$r['days_manual']??null;
        $remaining=max(0,$w['goal']-$chapters);$start=new DateTimeImmutable(max($c['today'],$w['start']));$end=new DateTimeImmutable($w['end']);$daysLeft=max(0,(int)$start->diff($end)->format('%r%a')+1);
        $completed=$chapters>=$w['goal'];$completion=$completions[$n]??null;
        // Infer older completion dates without modifying or reinterpreting their chapter counts.
        $completedOn=$completed?($completion['completed_on']??($r&&($r['chapters_manual']??0)>0?date('Y-m-d',(int)$r['updated_at']):null)):null;
        if($completed&&!$completedOn){$entries=sql('SELECT date,chapters FROM reading_entries WHERE user_id=? AND week=? ORDER BY date,created_at,id',[$id,$n])->fetchAll();$sum=0;foreach($entries as $entry){$sum+=(int)$entry['chapters'];if($sum>=$w['goal']){$completedOn=$entry['date'];break;}}}
        $elapsed=max(0,(int)(new DateTimeImmutable($w['start']))->diff(new DateTimeImmutable($c['today']))->format('%r%a')+1);$plannedByToday=(int)ceil($w['goal']*min(7,$elapsed)/7);$overdueDays=max(0,(int)(new DateTimeImmutable($w['end']))->diff(new DateTimeImmutable($c['today']))->format('%r%a'));
        $finish=$completedOn??$c['today'];$previous=$n>1?($result[$n-2]['completedOn']??null):null;
        $durationStart=$previous&&$previous<=$finish?$previous:$w['start'];
        $autoDays=max(1,(int)(new DateTimeImmutable($durationStart))->diff(new DateTimeImmutable($finish))->format('%r%a')+($durationStart===$previous?0:1));
        $actualDays=$days!==null&&(int)$days>0?(int)$days:($chapters>0?$autoDays:0);
        $late=$completed&&$completedOn&&$completedOn>$w['end'];$status=$completed?($late?'completed_late':'completed'):($c['today']<$w['start']?'upcoming':($overdueDays?'overdue':'in_progress'));
        $result[]=array_merge($w,['week'=>$n,'chapters'=>$chapters,'chaptersOverride'=>isset($r['chapters_override'])?(int)$r['chapters_override']:null,'chaptersDaily'=>(int)($d['chapters']??0),'days'=>$actualDays,'daysAuto'=>$autoDays,'dailyMarkedDays'=>(int)($d['days']??0),'durationFrom'=>$durationStart,'daysManual'=>$days,'completed'=>$completed,'completedOn'=>$completedOn,'completedBooks'=>$completion?json_decode($completion['plan_snapshot'],true):[],'status'=>$status,'late'=>(bool)$late,'overdueDays'=>$completed&&$completedOn?max(0,(int)(new DateTimeImmutable($w['end']))->diff(new DateTimeImmutable($completedOn))->format('%r%a')):$overdueDays,'elapsedDays'=>$elapsed,'plannedByToday'=>$plannedByToday,'behindChapters'=>max(0,$plannedByToday-$chapters),'plannedPerDay'=>round($w['goal']/7,2),'actualPerDay'=>$actualDays?round($chapters/$actualDays,2):0,'remaining'=>$remaining,'daysLeft'=>$daysLeft,'perDay'=>$remaining&&$daysLeft?(int)ceil($remaining/$daysLeft):0,'recorded'=>isset($rmap[$n])||isset($dmap[$n]),'title'=>$r['title']??'','note'=>$r['note']??'','editor'=>$r['editor']??'','legacyPages'=>(int)($r['pages']??0),'legacyMinutes'=>(int)($r['minutes']??0)]);
    }return $result;
}
function stats(string $id): array {
    $weeks=weekResults($id);$legacy=legacyStats($id);$entries=sql('SELECT e.*,u.name AS actor FROM reading_entries e JOIN users u ON u.id=e.actor_id WHERE e.user_id=? ORDER BY date DESC,created_at DESC',[$id])->fetchAll();
    $current=calendar()['current'];$goalTotal=array_sum(array_column($weeks,'goal'));$chapters=array_sum(array_column($weeks,'chapters'));
    return ['reports'=>$weeks,'entries'=>$entries,'chapters'=>$chapters,'days'=>array_sum(array_column($weeks,'days')),'recorded'=>count(array_filter($weeks,fn($w)=>$w['recorded'])),'goalWeeks'=>count(array_filter($weeks,fn($w)=>$w['completed'])),'overdueWeeks'=>count(array_filter($weeks,fn($w)=>$w['status']==='overdue')),'lateWeeks'=>count(array_filter($weeks,fn($w)=>$w['late'])),'progress'=>(int)round($chapters/max(1,$goalTotal)*100),'goalTotal'=>$goalTotal,'pace'=>$current>=1&&$current<=22?$weeks[$current-1]:null,'legacy'=>$legacy];
}
function staff(): array {
    $users=legacyStaff();foreach($users as &$u){$w=weekResults($u['id']);$u['chapters']=array_sum(array_column($w,'chapters'));$u['days']=array_sum(array_column($w,'days'));$u['completed']=count(array_filter($w,fn($w)=>$w['completed']));$u['weekly']=$w;}unset($u);
    usort($users,fn($a,$b)=>$b['chapters']<=>$a['chapters']?:strcmp($a['name'],$b['name']));return $users;
}
function assertWeekEditable(int $week): array {
    if($week<1||$week>22)throw new DomainException('Неделя должна быть от 1 до 22.');$w=calendar()['calendar'][$week-1];
    if(!$w['editable'])throw new DomainException('Эта неделя закрыта. Администратор может открыть её для исправления.');return $w;
}
function addReading(string $id,string $actor,int $chapters,string $date,string $title,string $note,string $source,string $entryId): array {
    $c=calendar();$d=DateTimeImmutable::createFromFormat('!Y-m-d',$date);if(!$d||$d->format('Y-m-d')!==$date||$date<$c['start']||$date>$c['end']||$date>$c['today'])throw new DomainException('Выберите дату марафона не позже сегодняшней.');
    $week=intdiv((int)(new DateTimeImmutable($c['start']))->diff($d)->format('%a'),7)+1;$w=assertWeekEditable($week);
    if($chapters<1||$chapters>100000)throw new DomainException('Укажите положительное число глав.');
    $existing=sql('SELECT * FROM reading_entries WHERE id=?',[$entryId])->fetch();if($existing){if($existing['user_id']!==$id)throw new DomainException('Запись недоступна.');return weekResults($id)[$week-1];}
    $total=weekResults($id)[$week-1]['chapters'];$left=max(0,$w['goal']-$total);if($chapters>$left)throw new DomainException('Можно зачесть не больше '.$left.' глав: недельный план — '.$w['goal'].'.');
    if($total+$chapters===$w['goal'])assertCompletionAllowed($actor,$week);
    sql('INSERT INTO reading_entries VALUES (?,?,?,?,?,?,?,?,?,?)',[$entryId,$id,$week,$date,$chapters,$title,$note,$actor,$source,time()]);sql('UPDATE reports SET chapters_override=chapters_override+? WHERE user_id=? AND week=? AND chapters_override IS NOT NULL',[$chapters,$id,$week]);syncCompletion($id,$week);audit($actor,'reading',$id,$date.': +'.$chapters.' глав ('.$source.')');return weekResults($id)[$week-1];
}

// Called inside the Telegram update transaction. Validate the complete allocation before writing.
function telegramReadingPlan(string $id,int $chapters): array {
    $c=calendar();$current=$c['current'];if($current<1||$current>23)throw new DomainException('Сейчас нет текущего или предыдущего плана для отметки.');
    if($chapters<1||$chapters>200000)throw new DomainException('Укажите положительное число глав, не больше 200000.');
    $weeks=weekResults($id);$eligible=array_values(array_filter($weeks,fn($w)=>$w['week']>=max(1,$current-1)&&$w['week']<=min(22,$current)&&$w['remaining']>0));
    $capacity=array_sum(array_column($eligible,'remaining'));if($chapters>$capacity)throw new DomainException('Можно зачесть не больше '.$capacity.' глав: это остаток предыдущей и текущей недель. Ничего не добавлено.');
    $left=$chapters;$result=[];foreach($eligible as $w){if(!$left)break;$w['added']=min($left,$w['remaining']);$result[]=$w;$left-=$w['added'];}return $result;
}
function addTelegramReading(string $id,int $chapters,int $updateId): array {
    $allocation=telegramReadingPlan($id,$chapters);$c=calendar();$result=[];
    foreach($allocation as $w){$amount=$w['added'];$week=$w['week'];
        sql('INSERT INTO reading_entries VALUES (?,?,?,?,?,?,?,?,?,?)',['tg_'.$updateId.'_w'.$week,$id,$week,$c['today'],$amount,'','Отметка из Telegram: распределение по планам',$id,'telegram',time()]);
        sql('UPDATE reports SET chapters_override=chapters_override+? WHERE user_id=? AND week=? AND chapters_override IS NOT NULL',[$amount,$id,$week]);
        syncCompletion($id,$week);$saved=weekResults($id)[$week-1];$saved['added']=$amount;$result[]=$saved;
        audit($id,'reading',$id,$c['today'].': +'.$amount.' глав (Telegram, неделя '.$week.')');
    }
    return $result;
}
function syncCompletion(string $id,int $week): void {
    $w=weekResults($id)[$week-1];
    if(!$w['completed']){sql('DELETE FROM week_completions WHERE user_id=? AND week=?',[$id,$week]);return;}
    sql('INSERT OR IGNORE INTO week_completions(user_id,week,completed_on,plan_snapshot) VALUES (?,?,?,?)',[$id,$week,calendar()['today'],json_encode($w['books'],JSON_UNESCAPED_UNICODE)]);

}
function assertCompletionAllowed(string $actor,int $week): void {
    $c=calendar();if(user($actor)['role']==='participant'&&($week<$c['current']-1||$week>$c['current']))throw new DomainException('Участник может завершить только текущую или предыдущую неделю.');
}
function planBookText(array $books): string {return implode('; ',array_map(fn($b)=>$b['title'].' '.$b['chapter_from'].'–'.$b['chapter_to'],$books));}
function completeWeek(string $id,string $actor,int $week,?int $days): array {
    $c=calendar();if($week<1||$week>22||!$c['calendar'][$week-1]['canComplete'])throw new DomainException('Эта неделя ещё не началась.');
    assertCompletionAllowed($actor,$week);
    $w=weekResults($id)[$week-1];if($w['completed'])return $w;
    $effectiveDays=$days??$w['daysAuto'];if($effectiveDays<1||$effectiveDays>3660)throw new DomainException('Количество дней должно быть от 1 до 3660.');
    $daily=(int)(sql('SELECT SUM(chapters) FROM reading_entries WHERE user_id=? AND week=?',[$id,$week])->fetchColumn()?:0);
    $title=mb_substr(planBookText($w['books']),0,200);
    sql('INSERT INTO reports(user_id,week,editor_id,updated_at,chapters_manual,days_manual,title) VALUES (?,?,?,?,?,?,?) ON CONFLICT(user_id,week) DO UPDATE SET chapters_manual=excluded.chapters_manual,days_manual=excluded.days_manual,editor_id=excluded.editor_id,updated_at=excluded.updated_at',[$id,$week,$actor,time(),max(0,$w['goal']-$daily),$days,$title]);
    sql('UPDATE reports SET chapters_override=? WHERE user_id=? AND week=?',[$w['goal'],$id,$week]);
    syncCompletion($id,$week);audit($actor,'complete_week',$id,'Неделя '.$week.': '.$w['goal'].' глав за '.$effectiveDays.' дн.'.($c['today']>$w['end']?' (с опозданием)':''));return weekResults($id)[$week-1];
}
function sessionStart(): void {
    $https=(!empty($_SERVER['HTTPS'])&&$_SERVER['HTTPS']!=='off')||(getenv('MARATHON_TRUST_PROXY')==='1'&&($_SERVER['HTTP_X_FORWARDED_PROTO']??'')==='https');
    // Store sessions in the existing persistent data volume, rather than the container filesystem.
    $dir=(getenv('MARATHON_DATA_DIR')?:dirname(__DIR__).'/storage').'/sessions';
    if(!is_dir($dir)&&!mkdir($dir,0700,true)&&!is_dir($dir))throw new RuntimeException('Cannot create session directory.');
    $lifetime=400*86400;
    ini_set('session.save_handler','files');session_save_path($dir);
    ini_set('session.use_strict_mode','1');ini_set('session.use_only_cookies','1');ini_set('session.use_trans_sid','0');
    ini_set('session.gc_maxlifetime',(string)$lifetime);session_name('marathon_session');
    $options=['path'=>'/','httponly'=>true,'samesite'=>'Lax','secure'=>$https];
    session_set_cookie_params(['lifetime'=>$lifetime]+$options);session_start();
    // Browsers cap persistent cookies; renew the deadline on every visit.
    setcookie(session_name(),session_id(),['expires'=>time()+$lifetime]+$options);
}
