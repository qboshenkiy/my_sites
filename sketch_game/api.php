<?php
declare(strict_types=1);
require __DIR__.'/lib/core.php';require __DIR__.'/lib/ai.php';
$action=$_GET['action']??'state';
sql("UPDATE rounds SET status='open' WHERE status='processing' AND judged<?",[time()-180]);
try {
    if($action==='health')result(['ok'=>true]);
    if($action==='state'){
        $valid=!empty($_SESSION['uid'])&&hash_equals($_SESSION['access']??'',hash('sha256',getenv('GAME_ACCESS_CODE')?:''));
        $uid=$valid?(int)$_SESSION['uid']:0;
        $admin=!empty($_SESSION['admin'])&&hash_equals($_SESSION['admin'],hash('sha256',getenv('ADMIN_PASSWORD')?:''));
        $categories=sql('SELECT id,title,words FROM categories WHERE active=1 ORDER BY id')->fetchAll(PDO::FETCH_ASSOC);
        foreach($categories as &$c){$c['count']=count(json_decode($c['words'],true));if($admin)$c['words']=json_decode($c['words'],true);else unset($c['words']);}unset($c);
        $history=$uid?sql("SELECT id,category,target,stars,guess,feedback,judged FROM rounds WHERE player_id=? AND status='done' ORDER BY judged DESC LIMIT 30",[$uid])->fetchAll(PDO::FETCH_ASSOC):[];
        result(['csrf'=>$_SESSION['csrf'],'player'=>$uid?sql('SELECT id,name FROM players WHERE id=?',[$uid])->fetch(PDO::FETCH_ASSOC):null,'admin'=>$admin,'aiReady'=>(bool)getenv('OPENAI_API_KEY'),'categories'=>$categories,'history'=>$history,'round'=>$uid?(sql("SELECT id,category,target,status FROM rounds WHERE player_id=? AND status IN ('open','processing') ORDER BY created DESC LIMIT 1",[$uid])->fetch(PDO::FETCH_ASSOC)?:null):null]);
    }
    if($_SERVER['REQUEST_METHOD']!=='POST')result(['error'=>'Нужен POST-запрос'],405);
    if(!hash_equals($_SESSION['csrf'],$_SERVER['HTTP_X_CSRF_TOKEN']??''))result(['error'=>'Обновите страницу и повторите'],403);
    if((int)($_SERVER['CONTENT_LENGTH']??0)>1600000)result(['error'=>'Рисунок слишком большой'],413);
    $raw=file_get_contents('php://input',false,null,0,1600001);if(strlen($raw)>1600000)result(['error'=>'Рисунок слишком большой'],413);
    $input=json_decode($raw,true,32,JSON_THROW_ON_ERROR);if(!is_array($input))result(['error'=>'Некорректный запрос'],400);
    if($action==='join'){
        throttle('login:'.hash('sha256',$_SERVER['REMOTE_ADDR']??''),30,300);
        $code=getenv('GAME_ACCESS_CODE')?:'';$name=text($input['name']??'',40);
        if(strlen($code)<8||!hash_equals($code,(string)($input['code']??''))||$name==='')result(['error'=>'Проверьте имя и код игры'],401);
        session_regenerate_id(true);sql('INSERT INTO players(name) VALUES (?)',[$name]);$_SESSION['uid']=(int)$db->lastInsertId();$_SESSION['access']=hash('sha256',$code);result(['ok'=>true]);
    }
    if($action==='admin_login'){
        throttle('admin-login',10,300);$password=getenv('ADMIN_PASSWORD')?:'';
        if(strlen($password)<12||!hash_equals($password,(string)($input['password']??'')))result(['error'=>'Неверный пароль'],401);
        session_regenerate_id(true);$_SESSION['admin']=hash('sha256',$password);result(['ok'=>true]);
    }
    if($action==='logout'){$_SESSION=[];session_regenerate_id(true);result(['ok'=>true]);}
    if(in_array($action,['category_save','category_delete','category_import'],true)){
        administrator();
        if($action==='category_delete'){sql('UPDATE categories SET active=0 WHERE id=?',[(int)($input['id']??0)]);result(['ok'=>true]);}
        if($action==='category_import'){
            $items=$input['categories']??null;if(!is_array($items)||count($items)<1||count($items)>30)throw new DomainException('JSON должен содержать categories: от 1 до 30 категорий.');
            $checked=[];foreach($items as $item){if(!is_array($item))throw new DomainException('Некорректная категория.');$checked[]=categoryInput($item);}
            $db->beginTransaction();foreach($checked as $values)sql('INSERT INTO categories(title,words) VALUES (?,?)',$values);$db->commit();result(['ok'=>true]);
        }
        [$title,$words]=categoryInput($input);$id=(int)($input['id']??0);
        if($id)sql('UPDATE categories SET title=?,words=? WHERE id=? AND active=1',[$title,$words,$id]);else sql('INSERT INTO categories(title,words) VALUES (?,?)',[$title,$words]);result(['ok'=>true]);
    }
    $uid=member();
    if($action==='start'){
        $open=sql("SELECT id FROM rounds WHERE player_id=? AND status IN ('open','processing')",[$uid])->fetchColumn();
        if($open)result(['error'=>'Завершите или пропустите текущее задание'],409);
        throttle('start:'.$uid,60,3600);
        $category=sql('SELECT * FROM categories WHERE id=? AND active=1',[(int)($input['category']??0)])->fetch(PDO::FETCH_ASSOC);if(!$category)throw new DomainException('Выберите доступную категорию.');
        $words=json_decode($category['words'],true);$target=$words[random_int(0,count($words)-1)];
        sql('INSERT INTO rounds(id,player_id,category,target,created) VALUES (?,?,?,?,?)',[bin2hex(random_bytes(16)),$uid,$category['title'],$target,time()]);result(['ok'=>true]);
    }
    $round=sql('SELECT * FROM rounds WHERE id=? AND player_id=?',[(string)($input['round']??''),$uid])->fetch(PDO::FETCH_ASSOC);
    if(!$round)result(['error'=>'Задание не найдено'],404);
    if($action==='skip'){if($round['status']!=='open')result(['error'=>'Дождитесь оценки'],409);sql("UPDATE rounds SET status='skipped' WHERE id=? AND status='open'",[$round['id']]);result(['ok'=>true]);}
    if($action!=='judge')result(['error'=>'Действие не найдено'],404);
    if($round['status']==='done')result(['stars'=>(int)$round['stars'],'guess'=>$round['guess'],'feedback'=>$round['feedback']]);
    if($round['status']!=='open')result(['error'=>'Оценка уже выполняется'],409);
    if(!getenv('OPENAI_API_KEY'))throw new DomainException('Администратор ещё не подключил ИИ. Рисунок останется на экране.');
    $image=$input['image']??'';if(!is_string($image)||!str_starts_with($image,'data:image/png;base64,'))throw new DomainException('Отправьте рисунок с холста.');
    $bytes=base64_decode(substr($image,22),true);$info=$bytes?@getimagesizefromstring($bytes):false;
    if(!$info||$info[2]!==IMAGETYPE_PNG||$info[0]<32||$info[1]<32||$info[0]>1024||$info[1]>1024)throw new DomainException('Некорректное изображение.');
    $bitmap=@imagecreatefromstring($bytes);if(!$bitmap)throw new DomainException('Не удалось прочитать рисунок.');
    $thumb=imagecreatetruecolor(160,160);imagecopyresampled($thumb,$bitmap,0,0,0,0,160,160,$info[0],$info[1]);imagedestroy($bitmap);ob_start();imagepng($thumb);$thumbnail=ob_get_clean();imagedestroy($thumb);
    throttle('judge:'.$uid,20,3600);
    $limit=max(1,min(1000,(int)(getenv('AI_DAILY_LIMIT')?:100)));
    throttle('ai-budget:'.gmdate('Y-m-d'),$limit,86400);
    $db->exec('BEGIN IMMEDIATE');
    // Reserve before releasing the session: retries and parallel requests cannot double-charge a round.
    $limit=max(1,min(1000,(int)(getenv('AI_DAILY_LIMIT')?:100)));
    if((int)sql("SELECT count(*) FROM rounds WHERE judged>=?",[strtotime('today UTC')])->fetchColumn()>=$limit){$db->exec('ROLLBACK');result(['error'=>'Дневной лимит оценок исчерпан. Продолжим завтра.'],429);}
    $updated=sql("UPDATE rounds SET status='processing',judged=? WHERE id=? AND status='open'",[time(),$round['id']]);
    if($updated->rowCount()!==1){$db->exec('ROLLBACK');result(['error'=>'Оценка уже выполняется'],409);}$db->exec('COMMIT');session_write_close();
    try{
        $evaluation=judgeDrawing($image,$round['target']);
        $statement=$db->prepare("UPDATE rounds SET status='done',stars=?,guess=?,feedback=?,image=? WHERE id=?");
        $statement->execute([$evaluation['stars'],$evaluation['guess'],$evaluation['feedback'],$thumbnail,$round['id']]);result($evaluation);
    }catch(Throwable $error){sql("UPDATE rounds SET status='open' WHERE id=?",[$round['id']]);throw $error;}
}catch(DomainException $error){result(['error'=>$error->getMessage()],422);}
catch(Throwable $error){if($db->inTransaction())$db->rollBack();error_log('Sketch request failed: '.get_class($error));result(['error'=>'Не удалось выполнить действие. Повторите позже.'],500);}
