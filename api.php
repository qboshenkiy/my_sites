<?php
declare(strict_types=1);
ini_set('display_errors', '0');
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');
$https = (!empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off') || (getenv('QUIZ_TRUST_PROXY') === '1' && ($_SERVER['HTTP_X_FORWARDED_PROTO'] ?? '') === 'https');
ini_set('session.use_strict_mode','1');
session_set_cookie_params(['httponly'=>true,'samesite'=>'Lax','secure'=>$https]);
session_start();
$admin = !empty($_SESSION['admin']);
$csrf = $_SESSION['csrf'] ??= bin2hex(random_bytes(24));
session_write_close();
function fail(string $message, int $status = 400): never { http_response_code($status); echo json_encode(['error'=>$message], JSON_UNESCAPED_UNICODE); exit; }
function out(array $data): never { echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR); exit; }
function query(string $sql, array $args=[]): PDOStatement { global $db; $s=$db->prepare($sql); $s->execute($args); return $s; }
function hostOnly(): void { global $admin; if (!$admin) fail('Войдите в админку.',401); }
function cleanText(mixed $text, int $max): string { if (!is_string($text)) fail('Некорректный текст.'); $text=trim($text); if ($text==='' || mb_strlen($text)>$max) fail('Заполните текст (до '.$max.' символов).'); return $text; }
try {
    if (!extension_loaded('pdo_sqlite') || !extension_loaded('mbstring')) fail('На сервере нужны PHP-модули pdo_sqlite и mbstring. Включите их в настройках хостинга.',503);
    $dataDir = getenv('QUIZ_DATA_DIR') ?: __DIR__.'/storage';
    if (!is_dir($dataDir)) mkdir($dataDir, 0700, true);
    if (!is_writable($dataDir)) fail('Папка хранения недоступна для записи. Проверьте права папки storage.',503);
    $db=new PDO('sqlite:'.$dataDir.'/quiz.sqlite',null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $db->exec('PRAGMA journal_mode=WAL; PRAGMA busy_timeout=5000; PRAGMA foreign_keys=ON;');
    $db->exec('CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY,value TEXT NOT NULL);
    CREATE TABLE IF NOT EXISTS quizzes (id TEXT PRIMARY KEY,title TEXT NOT NULL,description TEXT NOT NULL,questions TEXT NOT NULL,created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS rooms (id TEXT PRIMARY KEY,code TEXT UNIQUE NOT NULL,quiz TEXT NOT NULL,status TEXT NOT NULL,current_index INTEGER NOT NULL DEFAULT -1,started_at REAL,deadline REAL,created_at INTEGER NOT NULL);
    CREATE TABLE IF NOT EXISTS players (id TEXT PRIMARY KEY,room_id TEXT NOT NULL REFERENCES rooms(id),name TEXT NOT NULL,token TEXT UNIQUE NOT NULL,score INTEGER NOT NULL DEFAULT 0,UNIQUE(room_id,name));
    CREATE TABLE IF NOT EXISTS answers (player_id TEXT NOT NULL REFERENCES players(id),room_id TEXT NOT NULL REFERENCES rooms(id),question_index INTEGER NOT NULL,choice INTEGER NOT NULL,points INTEGER NOT NULL,created_at REAL NOT NULL,PRIMARY KEY(player_id,question_index));
    CREATE TABLE IF NOT EXISTS login_attempts (ip TEXT PRIMARY KEY,attempts INTEGER NOT NULL,updated_at INTEGER NOT NULL);');
    $db->exec('CREATE TABLE IF NOT EXISTS images(id TEXT PRIMARY KEY,mime TEXT NOT NULL,data BLOB NOT NULL); CREATE TABLE IF NOT EXISTS room_meta(room_id TEXT PRIMARY KEY REFERENCES rooms(id),played TEXT NOT NULL DEFAULT \'[]\',projector_token TEXT NOT NULL);');
    require __DIR__.'/seed.php';
    $action=$_GET['action']??'bootstrap';
    $input=[];
    if ($_SERVER['REQUEST_METHOD']==='POST') {
        if ((int)($_SERVER['CONTENT_LENGTH']??0)>(($action==='import_preview')?20000000:3000000)) fail('Слишком большой запрос.',413);
        $input=json_decode(file_get_contents('php://input'),true);
        if (!is_array($input)) fail('Некорректный запрос.');
        if (!in_array($action,['join','answer','bluff_select','bluff_lie','bluff_vote'],true) && !hash_equals($csrf,$_SERVER['HTTP_X_CSRF_TOKEN']??'')) fail('Обновите страницу и повторите.',403);
    } elseif (!in_array($action,['bootstrap','quizzes','state','image'],true)) fail('Требуется POST.',405);
    if ($action==='image') {
        $img=query('SELECT * FROM images WHERE id=?',[$_GET['id']??''])->fetch(); if(!$img)fail('Изображение не найдено.',404);
        header('Content-Type: '.$img['mime']);header('X-Content-Type-Options: nosniff');header('Cache-Control: public, max-age=86400');echo $img['data'];exit;
    }
    if ($action==='upload_image') {
        hostOnly();$content=$input['content']??'';
        if(!is_string($content)||!preg_match('~^data:image/(?:png|jpeg|webp|gif);base64,(.+)$~s',$content,$match))fail('Загрузите PNG, JPEG, WebP или GIF.');
        $bytes=base64_decode($match[1],true);$info=$bytes?@getimagesizefromstring($bytes):false;
        if(!$info||strlen($bytes)>2000000||$info[0]>4096||$info[1]>4096||!in_array($info['mime'],['image/png','image/jpeg','image/webp','image/gif'],true))fail('Изображение: до 2 МБ и 4096×4096 пикселей.');
        $id=bin2hex(random_bytes(16));query('INSERT INTO images VALUES (?,?,?)',[$id,$info['mime'],$bytes]);out(['id'=>$id]);
    }
    if ($action==='bootstrap') out(['admin'=>$admin,'configured'=>(bool)query("SELECT value FROM settings WHERE key='password'")->fetchColumn(),'csrf'=>$csrf]);
    if ($action==='setup' || $action==='login') {
        $password=$input['password']??'';
        if (!is_string($password) || strlen($password)<8 || strlen($password)>200) fail('Пароль должен содержать от 8 до 200 символов.');
        $db->exec('BEGIN IMMEDIATE');
        $hash=query("SELECT value FROM settings WHERE key='password'")->fetchColumn();
        if ($action==='setup') {
            if ($hash) fail('Администратор уже создан.',409);
            query('INSERT INTO settings(key,value) VALUES (?,?)',['password',password_hash($password,PASSWORD_DEFAULT)]);
        } else {
            $ip=$_SERVER['REMOTE_ADDR']??'local';
            $attempt=query('SELECT * FROM login_attempts WHERE ip=?',[$ip])->fetch();
            if ($attempt && (int)$attempt['attempts']>=10 && (int)$attempt['updated_at']>time()-900) fail('Слишком много попыток. Повторите через 15 минут.',429);
            if (!$hash || !password_verify($password,$hash)) {
                $count=$attempt && (int)$attempt['updated_at']>time()-900 ? (int)$attempt['attempts']+1 : 1;
                query('INSERT INTO login_attempts VALUES (?,?,?) ON CONFLICT(ip) DO UPDATE SET attempts=excluded.attempts,updated_at=excluded.updated_at',[$ip,$count,time()]);
                $db->exec('COMMIT'); fail('Неверный пароль.',401);
            }
            query('DELETE FROM login_attempts WHERE ip=?',[$ip]);
        }
        $db->exec('COMMIT'); session_start(); session_regenerate_id(true); $_SESSION['admin']=true; session_write_close(); out(['ok'=>true]);
    }
    if ($action==='logout') { session_start(); $_SESSION['admin']=false; session_regenerate_id(true); session_write_close(); out(['ok'=>true]); }
    if ($action==='quizzes') {
        hostOnly(); $quizzes=query('SELECT * FROM quizzes ORDER BY created_at DESC')->fetchAll();
        foreach ($quizzes as &$q) { $raw=json_decode($q['questions'],true);$q['questions']=$raw['questions']??$raw;$q['mode']=$raw['mode']??'classic';$q['scoring']=$raw['scoring']??'speed'; }
        $rooms=query('SELECT id,code,status,created_at,quiz FROM rooms ORDER BY created_at DESC LIMIT 12')->fetchAll();
        foreach ($rooms as &$r) { $r['title']=json_decode($r['quiz'],true)['title']; unset($r['quiz']); }
        out(['quizzes'=>$quizzes,'rooms'=>$rooms]);
    }
    if($action==='import_preview'){
        hostOnly();require __DIR__.'/assets/quiz-import.php';if(!is_string($input['json']??null))fail('Вставьте JSON текстом.');
        try{out(normalizeQuizImport($input['json'],$input));}catch(DomainException $e){fail($e->getMessage());}
    }
    if ($action==='save') {
        hostOnly(); $title=cleanText($input['title']??'',100); $description=trim((string)($input['description']??''));
        if (mb_strlen($description)>300) fail('Описание: максимум 300 символов.');
        $questions=$input['questions']??[];
        if (!is_array($questions) || count($questions)<1 || count($questions)>50) fail('Добавьте от 1 до 50 вопросов.');
        $valid=[];
        $mode=$input['mode']??'classic';$scoring=$input['scoring']??'speed';
        if(!in_array($mode,['classic','board','bluff'],true)||!in_array($scoring,['speed','fixed'],true))fail('Некорректный режим игры.');
        $cells=[];
        foreach ($questions as $q) {
            if($mode==='bluff'){
                $truth=cleanText($q['truth']??'',120);$aliases=$q['aliases']??[];
                if(!is_array($aliases)||count($aliases)>10)fail('Добавьте не больше 10 допустимых написаний ответа.');
                $aliases=array_map(fn($v)=>cleanText($v,120),array_values($aliases));
                $seconds=filter_var($q['seconds']??60,FILTER_VALIDATE_INT);if($seconds===false||$seconds<5||$seconds>120)fail('Время ввода: 5–120 секунд.');
                $reference=$q['reference']??'';if(!is_string($reference)||mb_strlen($reference)>200)fail('Источник: до 200 символов.');
                $image=$q['image']??null;if($image&&!query('SELECT id FROM images WHERE id=?',[$image])->fetchColumn())fail('Изображение не найдено.');
                $valid[]=['text'=>cleanText($q['text']??'',250),'category'=>cleanText($q['category']??'',60),'truth'=>$truth,'aliases'=>$aliases,'seconds'=>$seconds,'type'=>'quiz','points'=>1000,'options'=>[],'correct'=>null,'image'=>$image,'reference'=>trim($reference)];continue;
            }

            $type=$q['type']??'quiz'; if (!in_array($type,['quiz','poll'],true)) fail('Неизвестный тип вопроса.');
            $options=$q['options']??[]; if (!is_array($options) || count($options)<2 || count($options)>4) fail('Нужно 2–4 варианта ответа.');
            $options=array_map(fn($o)=>cleanText($o,120),array_values($options));
            $seconds=filter_var($q['seconds']??20,FILTER_VALIDATE_INT); if (!$seconds || $seconds<5 || $seconds>120) fail('Время ответа: 5–120 секунд.');
            $correct=$type==='quiz'?filter_var($q['correct']??null,FILTER_VALIDATE_INT):null;
            if ($type==='quiz' && ($correct===false || $correct===null || $correct<0 || $correct>=count($options))) fail('Выберите правильный ответ.');
            $points=filter_var($q['points']??1000,FILTER_VALIDATE_INT);if($points===false||$points<1||$points>10000)fail('Баллы за вопрос: 1–10000.');
            $category=$mode==='board'?cleanText($q['category']??'',60):trim((string)($q['category']??''));
            if($mode==='board'){ $cell=$category.'|'.$points;if(isset($cells[$cell]))fail('В категории не должно быть двух вопросов с одинаковыми баллами.');$cells[$cell]=true; }
            $image=$q['image']??null;if($image&&!query('SELECT id FROM images WHERE id=?',[$image])->fetchColumn())fail('Изображение не найдено.');
            $reference=$q['reference']??'';if(!is_string($reference)||mb_strlen($reference)>200)fail('Ссылка на источник: максимум 200 символов.');
            $valid[]=['reference'=>trim($reference),'text'=>cleanText($q['text']??'',250),'type'=>$type,'seconds'=>$seconds,'options'=>$options,'correct'=>$correct,'category'=>$category,'points'=>$points,'image'=>$image];
        }
        $id=$input['id']??bin2hex(random_bytes(8));
        if (!is_string($id) || !preg_match('/^[a-f0-9]{16}$/',$id)) fail('Некорректный идентификатор.');
        query('INSERT INTO quizzes VALUES (?,?,?,?,?) ON CONFLICT(id) DO UPDATE SET title=excluded.title,description=excluded.description,questions=excluded.questions',[$id,$title,$description,json_encode(['mode'=>$mode,'scoring'=>in_array($mode,['board','bluff'],true)?'fixed':$scoring,'questions'=>$valid],JSON_UNESCAPED_UNICODE),time()]); out(['id'=>$id]);
    }
    if ($action==='delete') { hostOnly(); query('DELETE FROM quizzes WHERE id=?',[$input['id']??'']); out(['ok'=>true]); }
    if ($action==='create_room') {
        hostOnly(); $quiz=query('SELECT * FROM quizzes WHERE id=?',[$input['id']??''])->fetch(); if (!$quiz) fail('Опросник не найден.',404);
        $raw=json_decode($quiz['questions'],true);$quiz['questions']=$raw['questions']??$raw;$quiz['mode']=$raw['mode']??'classic';$quiz['scoring']=$raw['scoring']??'speed'; $id=bin2hex(random_bytes(8));
        do { $code=(string)random_int(100000,999999); } while (query('SELECT id FROM rooms WHERE code=?',[$code])->fetchColumn());
        query('INSERT INTO rooms(id,code,quiz,status,created_at) VALUES (?,?,?,?,?)',[$id,$code,json_encode($quiz,JSON_UNESCAPED_UNICODE),'lobby',time()]);
        query('INSERT INTO room_meta(room_id,projector_token) VALUES (?,?)',[$id,bin2hex(random_bytes(24))]);out(['id'=>$id,'code'=>$code]);
    }
    if ($action==='join') {
        $code=cleanText($input['code']??'',6); $name=cleanText($input['name']??'',24);
        $db->exec('BEGIN IMMEDIATE'); $room=query('SELECT * FROM rooms WHERE code=?',[$code])->fetch();
        if (!$room) fail('Комната с таким кодом не найдена.',404); if ($room['status']==='finished') fail('Эта игра уже завершена.');
        if (query('SELECT id FROM players WHERE room_id=? AND name=?',[$room['id'],$name])->fetchColumn()) fail('Это имя уже занято. Выберите другое.');
        if ((int)query('SELECT count(*) FROM players WHERE room_id=?',[$room['id']])->fetchColumn()>=500) fail('Комната заполнена.');
        $id=bin2hex(random_bytes(8)); $token=bin2hex(random_bytes(32));
        query('INSERT INTO players(id,room_id,name,token) VALUES (?,?,?,?)',[$id,$room['id'],$name,$token]); $db->exec('COMMIT'); out(['token'=>$token,'room'=>$room['id'],'name'=>$name]);
    }
    if (in_array($action,['state','control','answer','bluff_select','bluff_lie','bluff_vote'],true)) {
        $db->exec('BEGIN IMMEDIATE');
        $player=null;
        $projector=false;
        if($action==='state'&&!empty($_GET['projector'])) { $meta=query('SELECT * FROM room_meta WHERE projector_token=?',[$_GET['projector']])->fetch();if(!$meta)fail('Экран недоступен.',403);$roomId=$meta['room_id'];$projector=true; }
        elseif (in_array($action,['answer','bluff_select','bluff_lie','bluff_vote'],true) || (!$admin && $action==='state') || !empty($_SERVER['HTTP_X_PLAYER_TOKEN'])) {
            $player=query('SELECT * FROM players WHERE token=?',[$_SERVER['HTTP_X_PLAYER_TOKEN']??''])->fetch(); if (!$player) fail('Подключитесь к игре заново.',401);
            $roomId=$player['room_id'];
        } else { hostOnly(); $roomId=$input['room']??$_GET['room']??''; }
        $room=query('SELECT * FROM rooms WHERE id=?',[$roomId])->fetch(); if (!$room) fail('Комната не найдена.',404);
        $quiz=json_decode($room['quiz'],true); $index=(int)$room['current_index']; $question=$quiz['questions'][$index]??null;
        $meta=query('SELECT * FROM room_meta WHERE room_id=?',[$roomId])->fetch();
        if(!$meta){query('INSERT INTO room_meta(room_id,projector_token) VALUES (?,?)',[$roomId,bin2hex(random_bytes(24))]);$meta=query('SELECT * FROM room_meta WHERE room_id=?',[$roomId])->fetch();}
        if(($quiz['mode']??'classic')==='bluff'){require __DIR__.'/assets/bluff.php';$result=bluffHandle($action,$input,$room,$quiz,$meta,$player,$projector);$db->exec('COMMIT');out($result);}
        if(str_starts_with($action,'bluff_'))fail('Это действие доступно только в Бредовухе.');
        $played=json_decode($meta['played'],true);$boardMode=($quiz['mode']??'classic')==='board';
        if ($room['status']==='question' && microtime(true)>=(float)$room['deadline']) { query("UPDATE rooms SET status='results' WHERE id=?",[$roomId]); $room['status']='results'; }
        if ($action==='control') {
            hostOnly(); $command=$input['command']??'';
            if ($command==='next') {
                if (!in_array($room['status'],['lobby','results'],true)) fail('Сначала покажите результаты текущего вопроса.');
                if($boardMode){query('UPDATE rooms SET status=? WHERE id=?',[count($played)>=count($quiz['questions'])?'finished':'board',$roomId]);$db->exec('COMMIT');out(['ok'=>true]);}
                $index++;
                if ($index>=count($quiz['questions'])) { query("UPDATE rooms SET status='finished' WHERE id=?",[$roomId]); }
                else { $now=microtime(true); query("UPDATE rooms SET status='question',current_index=?,started_at=?,deadline=? WHERE id=?",[$index,$now,$now+$quiz['questions'][$index]['seconds'],$roomId]); }
            } elseif ($command==='select'&&$boardMode&&$room['status']==='board') {
                $selected=filter_var($input['index']??null,FILTER_VALIDATE_INT);
                if($selected===false||$selected===null||!isset($quiz['questions'][$selected])||in_array($selected,$played,true))fail('Этот вопрос недоступен.');
                $played[]=$selected;query('UPDATE room_meta SET played=? WHERE room_id=?',[json_encode($played),$roomId]);$now=microtime(true);
                query("UPDATE rooms SET status='question',current_index=?,started_at=?,deadline=? WHERE id=?",[$selected,$now,$now+$quiz['questions'][$selected]['seconds'],$roomId]);
            } elseif ($command==='reveal' && $room['status']==='question') query("UPDATE rooms SET status='results' WHERE id=?",[$roomId]);
            elseif ($command==='finish') query("UPDATE rooms SET status='finished' WHERE id=?",[$roomId]);
            else fail('Это действие сейчас недоступно.');
            $db->exec('COMMIT'); out(['ok'=>true]);
        }
        if ($action==='answer') {
            if ($room['status']!=='question' || (int)($input['index']??-1)!==$index) fail('Время ответа истекло.');
            $choice=filter_var($input['choice']??null,FILTER_VALIDATE_INT);
            if ($choice===false || $choice===null || $choice<0 || $choice>=count($question['options'])) fail('Выберите вариант ответа.');
            if (query('SELECT choice FROM answers WHERE player_id=? AND question_index=?',[$player['id'],$index])->fetch()) fail('Ваш ответ уже принят.',409);
            $maxPoints=(int)($question['points']??1000);
            $points=$question['type']==='quiz' && $choice===$question['correct'] ? (($quiz['scoring']??'speed')==='fixed'?$maxPoints:(int)round($maxPoints*(.5+.5*max(0,((float)$room['deadline']-microtime(true))/$question['seconds'])))) : 0;
            query('INSERT INTO answers VALUES (?,?,?,?,?,?)',[$player['id'],$roomId,$index,$choice,$points,microtime(true)]);
            query('UPDATE players SET score=score+? WHERE id=?',[$points,$player['id']]); $db->exec('COMMIT'); out(['ok'=>true]);
        }
        $players=query('SELECT id,name,score FROM players WHERE room_id=? ORDER BY score DESC,name ASC',[$roomId])->fetchAll();
        $counts=$question?array_fill(0,count($question['options']),0):[];
        foreach(query('SELECT choice,count(*) AS total FROM answers WHERE room_id=? AND question_index=? GROUP BY choice',[$roomId,$index])->fetchAll() as $a) $counts[(int)$a['choice']]=(int)$a['total'];
        $answer=$player?query('SELECT choice,points FROM answers WHERE player_id=? AND question_index=?',[$player['id'],$index])->fetch():null;
        $revealed=in_array($room['status'],['results','finished'],true);
        if ($question && !$revealed) unset($question['correct'],$question['reference']);
        if ($player && !$revealed) {
            $counts=[]; if ($answer) unset($answer['points']);
            // Current-question scores would reveal correctness before the host reveals results.
            $pending=[];
            foreach(query('SELECT player_id,points FROM answers WHERE room_id=? AND question_index=?',[$roomId,$index])->fetchAll() as $a) $pending[$a['player_id']]=(int)$a['points'];
            foreach($players as &$p) $p['score']=(int)$p['score']-($pending[$p['id']]??0);
            unset($p);
            usort($players, fn($a,$b)=>$b['score']<=>$a['score'] ?: strcmp($a['name'],$b['name']));
        }
        $rank=0;$lastScore=null;foreach($players as $i=>&$p){if($lastScore!==$p['score'])$rank=$i+1;$p['rank']=$rank;$lastScore=$p['score'];}unset($p);
        $board=[];foreach($quiz['questions'] as $i=>$item)$board[]=['index'=>$i,'category'=>$item['category']??'Вопросы','points'=>$item['points']??1000,'played'=>in_array($i,$played,true)];
        $db->exec('COMMIT');
        out(['id'=>$roomId,'code'=>$room['code'],'title'=>$quiz['title'],'status'=>$room['status'],'mode'=>$quiz['mode']??'classic','scoring'=>$quiz['scoring']??'speed','board'=>$board,'played'=>count($played),'projectorToken'=>$admin&&!$player&&!$projector?$meta['projector_token']:null,'index'=>$index,'total'=>count($quiz['questions']),'question'=>$question,'remaining'=>$room['status']==='question'?max(0,(float)$room['deadline']-microtime(true)):0,'players'=>$players,'counts'=>$counts,'answered'=>(int)query('SELECT count(*) FROM answers WHERE room_id=? AND question_index=?',[$roomId,$index])->fetchColumn(),'answer'=>$answer?:null,'playerId'=>$player['id']??null]);
    }
    fail('Неизвестное действие.',404);
} catch(Throwable $e) { if (isset($db) && $db->inTransaction()) $db->rollBack(); error_log((string)$e); fail('Ошибка сервера. Повторите попытку.',500); }
