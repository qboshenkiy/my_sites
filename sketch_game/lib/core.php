<?php
declare(strict_types=1);
$storage=getenv('DRAW_DATA_DIR')?:dirname(__DIR__).'/storage';
if(!is_dir($storage))mkdir($storage,0770,true);
if(!is_dir($storage.'/sessions'))mkdir($storage.'/sessions',0770,true);
session_save_path($storage.'/sessions');session_name('sketch_session');
ini_set('session.gc_maxlifetime','31536000');ini_set('session.use_strict_mode','1');
session_set_cookie_params(['lifetime'=>31536000,'path'=>'/','secure'=>str_starts_with(getenv('APP_URL')?:'','https://'),'httponly'=>true,'samesite'=>'Lax']);session_start();
$_SESSION['csrf']??=bin2hex(random_bytes(24));
$db=new PDO('sqlite:'.$storage.'/game.sqlite');$db->setAttribute(PDO::ATTR_ERRMODE,PDO::ERRMODE_EXCEPTION);$db->exec('PRAGMA busy_timeout=10000');$db->exec('PRAGMA journal_mode=WAL');
$db->exec("CREATE TABLE IF NOT EXISTS categories(id INTEGER PRIMARY KEY,title TEXT NOT NULL,words TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1);
CREATE TABLE IF NOT EXISTS players(id INTEGER PRIMARY KEY,name TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS rounds(id TEXT PRIMARY KEY,player_id INTEGER NOT NULL,category TEXT NOT NULL,target TEXT NOT NULL,status TEXT NOT NULL DEFAULT 'open',created INTEGER NOT NULL,judged INTEGER,stars INTEGER,guess TEXT,feedback TEXT,image BLOB);
CREATE TABLE IF NOT EXISTS limits(key TEXT PRIMARY KEY,started INTEGER NOT NULL,hits INTEGER NOT NULL);");
if((int)$db->query('SELECT count(*) FROM categories')->fetchColumn()===0){
    $q=$db->prepare('INSERT INTO categories(title,words) VALUES (?,?)');
    foreach(['Животные'=>['Кот','Слон','Черепаха','Жираф','Рыба','Бабочка'],'Природа'=>['Гора','Дерево','Радуга','Цветок','Вулкан','Снежинка'],'Транспорт'=>['Велосипед','Самолёт','Парусник','Поезд','Ракета'],'Бытие'=>['Ноев ковчег','Вавилонская башня','Лестница Иакова','Радуга после потопа','Семь тучных и семь тощих коров']] as $title=>$words)$q->execute([$title,json_encode($words,JSON_UNESCAPED_UNICODE)]);
}
function result(array $data,int $code=200): never {http_response_code($code);header('Content-Type: application/json; charset=utf-8');header('Cache-Control: no-store');echo json_encode($data,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);exit;}
function sql(string $query,array $args=[]): PDOStatement {global $db;$s=$db->prepare($query);$s->execute($args);return $s;}
function text(mixed $value,int $max): string {return is_string($value)?trim(mb_substr($value,0,$max)):'';}
function member(): int {
    if(empty($_SESSION['uid'])||!hash_equals($_SESSION['access']??'',hash('sha256',getenv('GAME_ACCESS_CODE')?:'')))result(['error'=>'Войдите с кодом игры'],401);
    return (int)$_SESSION['uid'];
}
function administrator(): void {if(empty($_SESSION['admin'])||!hash_equals($_SESSION['admin'],hash('sha256',getenv('ADMIN_PASSWORD')?:'')))result(['error'=>'Нужен вход администратора'],403);}
function throttle(string $key,int $max,int $window): void {
    $now=time();sql('INSERT INTO limits(key,started,hits) VALUES (?,?,1) ON CONFLICT(key) DO UPDATE SET hits=CASE WHEN started<? THEN 1 ELSE hits+1 END,started=CASE WHEN started<? THEN excluded.started ELSE started END',[$key,$now,$now-$window,$now-$window]);
    if((int)sql('SELECT hits FROM limits WHERE key=?',[$key])->fetchColumn()>$max)result(['error'=>'Слишком часто. Подождите немного.'],429);
}
function categoryInput(array $input): array {
    $title=text($input['title']??'',70);$words=$input['words']??[];
    if($title===''||!is_array($words)||count($words)<1||count($words)>200)throw new DomainException('Укажите название и от 1 до 200 заданий в категории.');
    $clean=[];foreach($words as $word){if(!is_string($word)||trim($word)===''||mb_strlen($word)>100)throw new DomainException('Каждое задание должно быть текстом длиной до 100 символов.');$clean[]=trim($word);}
    return [$title,json_encode(array_values(array_unique($clean)),JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR)];
}
