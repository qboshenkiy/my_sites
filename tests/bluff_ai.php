<?php
declare(strict_types=1);
require dirname(__DIR__).'/assets/bluff.php';
function check(bool $value,string $message): void {if(!$value)throw new RuntimeException($message);}
function fail(string $message,int $status=400): never {throw new DomainException($message,$status);}
function query(string $sql,array $args=[]): PDOStatement {global $db;$s=$db->prepare($sql);$s->execute($args);return $s;}
$q=['text'=>'Кто построил ковчег?','truth'=>'Ной','aliases'=>['Ноах'],'category'=>'Бытие','seconds'=>60];
foreach(['same','different','uncertain'] as $verdict){
    $result=bluffSemanticVerdict('Отец Сима, Хама и Иафета',$q,static function($body) use($verdict){
        check($body['store']===false&&$body['text']['format']['strict']===true,'Missing privacy/schema settings');
        check($body['text']['format']['schema']['additionalProperties']===false,'Loose schema');
        $data=json_decode($body['input'][0]['content'][0]['text'],true);
        check($data['canonical']==='Ной'&&$data['candidate']==='Отец Сима, Хама и Иафета','Comparison context missing');
        return ['verdict'=>$verdict];
    });check($result===$verdict,'Verdict lost');
}
foreach([[],['verdict'=>true],['verdict'=>'same','answer'=>'Ной'],['verdict'=>'yes']] as $bad)check(bluffSemanticVerdict('текст',$q,fn()=> $bad)==='uncertain','Malformed model response accepted');
check(bluffSemanticVerdict('текст',$q,fn()=>throw new RuntimeException('private provider response'))==='uncertain','Provider error bypassed review');
$file=tempnam(sys_get_temp_dir(),'bluff-ai-');
try{
    $db=new PDO('sqlite:'.$file,null,null,[PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION,PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC]);
    $db->exec('PRAGMA journal_mode=WAL; CREATE TABLE rooms(id TEXT PRIMARY KEY); CREATE TABLE players(id TEXT PRIMARY KEY,room_id TEXT,score INTEGER NOT NULL DEFAULT 0);');
    query("INSERT INTO rooms VALUES ('room')");foreach(['a','b','c'] as $id)query('INSERT INTO players VALUES (?,?,0)',[$id,'room']);bluffSchema();
    query("INSERT INTO bluff_rooms(room_id,phase,round_no,question_index,deadline,roster) VALUES ('room','write',1,0,?,?)",[microtime(true)+60,json_encode(['a','b'])]);
    $b=bluffRow('room');$player=['id'=>'a'];
    $db->exec('BEGIN IMMEDIATE');
    $called=0;$verdict=bluffCheckLie($b,$q,$player,'Отец Сима, Хама и Иафета',function() use($file,&$called){
        $called++;$other=new PDO('sqlite:'.$file);$other->exec('PRAGMA busy_timeout=50; BEGIN IMMEDIATE; COMMIT');return ['verdict'=>'same'];
    });check($verdict==='same'&&$called===1,'Semantic rejection missing');$db->exec('COMMIT');
    check((int)query('SELECT count(*) FROM bluff_lies')->fetchColumn()===0,'Rejected truth was inserted');
    // Exact normalized repeats use a round-local cache instead of charging another request.
    $db->exec('BEGIN IMMEDIATE');check(bluffCheckLie($b,$q,['id'=>'b'],'ОТЕЦ СИМА, ХАМА И ИАФЕТА!',fn()=>throw new RuntimeException('Unexpected network'))==='same','Cache missed');$db->exec('COMMIT');
    // Reservations block concurrent requests, and four attempts cap paid calls per player/round.
    query("UPDATE bluff_ai_attempts SET pending='busy',last_attempt=?",[microtime(true)]);$db->exec('BEGIN IMMEDIATE');
    try{bluffCheckLie($b,$q,$player,'Другая выдумка',fn()=>['verdict'=>'different']);throw new RuntimeException('Concurrent request allowed');}catch(DomainException $e){check($e->getCode()===429,'Wrong concurrency status');}$db->exec('ROLLBACK');
    query("UPDATE bluff_ai_attempts SET pending='',attempts=4,last_attempt=0");$db->exec('BEGIN IMMEDIATE');check(bluffCheckLie($b,$q,$player,'Другая выдумка',fn()=>throw new RuntimeException('Unexpected network'))==='uncertain','Retry cap bypassed');$db->exec('COMMIT');
    // The round must still be open after a slow model response; a host transition wins.
    query('DELETE FROM bluff_ai_attempts');$db->exec('BEGIN IMMEDIATE');
    try{bluffCheckLie($b,$q,$player,'Моисей',function() use($file){$other=new PDO('sqlite:'.$file);$other->exec("UPDATE bluff_rooms SET phase='review' WHERE room_id='room'");return ['verdict'=>'different'];});throw new RuntimeException('Stale answer accepted');}catch(DomainException $e){check($e->getCode()===409,'Wrong stale phase status');}$db->exec('ROLLBACK');
    query("UPDATE bluff_rooms SET phase='write'");
    // Fully verified lies move straight to voting. Only uncertain groups go to the host.
    foreach(['a'=>'Моисей','b'=>'Авраам'] as $id=>$text){query('INSERT INTO bluff_lies VALUES (?,?,?,?,?)',['room',1,$id,$text,bluffNormal($text)]);query('INSERT INTO bluff_lie_checks VALUES (?,?,?,?)',['room',1,$id,'different']);}
    bluffStartVote($b,['questions'=>[$q]]);check(bluffRow('room')['phase']==='vote','Verified answers blocked on host');
    query("UPDATE bluff_lie_checks SET verdict='uncertain' WHERE player_id='b'");bluffStartVote($b,['questions'=>[$q]]);$review=bluffRow('room');check($review['phase']==='review','Uncertain answer bypassed host');
    $choices=json_decode($review['choices'],true);check(count(array_filter($choices,fn($choice)=>$choice['needsReview']??false))===1,'Verified lies unnecessarily flagged');
    // Historical lies without a check record remain pending review after an upgrade.
    query('DELETE FROM bluff_lie_checks');bluffStartVote($b,['questions'=>[$q]]);check(bluffRow('room')['phase']==='review','Historical answers bypassed review');
    // The Secret Author mode has no correct answer, keeps authors hidden through voting,
    // then awards points for votes, the best response, and a correct author guess.
    query('DELETE FROM bluff_lies');query('DELETE FROM bluff_votes');query('DELETE FROM bluff_author_guesses');
    query("UPDATE bluff_rooms SET phase='write',round_no=2,roster=?,question_index=0",[json_encode(['a','b','c'])]);
    foreach(['a'=>'Ответ А','b'=>'Ответ Б','c'=>'Ответ В'] as $id=>$text)query('INSERT INTO bluff_lies VALUES (?,?,?,?,?)',['room',2,$id,$text,bluffNormal($text)]);
    $authorQuiz=['mode'=>'author','questions'=>[['text'=>'Тестовая тема','category'=>'Юмор','seconds'=>60,'image'=>null]]];$b=bluffRow('room');bluffStartVote($b,$authorQuiz);$choices=json_decode(bluffRow('room')['choices'],true);
    check(bluffRow('room')['phase']==='vote'&&count($choices)===3&&!array_filter($choices,fn($choice)=>$choice['truth']),'Author answers exposed or incorrectly checked');
    $byAuthor=[];foreach($choices as $choice)$byAuthor[$choice['authors'][0]]=$choice['id'];
    query('INSERT INTO bluff_votes VALUES (?,?,?,?)',['room',2,'a',$byAuthor['b']]);query('INSERT INTO bluff_votes VALUES (?,?,?,?)',['room',2,'b',$byAuthor['a']]);query('INSERT INTO bluff_votes VALUES (?,?,?,?)',['room',2,'c',$byAuthor['a']]);
    query('INSERT INTO bluff_author_guesses VALUES (?,?,?,?,?)',['room',2,'a',$byAuthor['b'],'b']);query('INSERT INTO bluff_author_guesses VALUES (?,?,?,?,?)',['room',2,'b',$byAuthor['a'],'c']);query('INSERT INTO bluff_author_guesses VALUES (?,?,?,?,?)',['room',2,'c',$byAuthor['a'],'a']);
    bluffScore(bluffRow('room'),true);$scores=array_column(query('SELECT score,id FROM players')->fetchAll(),'score','id');
    check($scores['a']===5000&&$scores['b']===2000&&$scores['c']===2000,'Secret Author scoring or author-guess bonus is wrong');
    echo "PASS: strict semantic verdicts, private rejection, failure review, SQLite lock released during model call, cache/retry cap, stale-round protection and automatic verified voting.\n";
}finally{$db=null;foreach([$file,$file.'-wal',$file.'-shm'] as $path)if(is_file($path))unlink($path);}
