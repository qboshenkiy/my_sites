<?php
declare(strict_types=1);
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){http_response_code(404);exit;}
require_once __DIR__.'/bluff-ai.php';
function bluffNormal(string $s): string {
    if(class_exists('Normalizer'))$s=Normalizer::normalize($s,Normalizer::FORM_KC)?:$s;
    $s=preg_replace('/\p{Cf}/u','',$s);
    $s=strtr(mb_strtolower($s),['ё'=>'е','a'=>'а','c'=>'с','e'=>'е','o'=>'о','p'=>'р','x'=>'х','y'=>'у','k'=>'к','m'=>'м','t'=>'т','b'=>'в','h'=>'н']);
    return trim(preg_replace('/[^\p{L}\p{N}]+/u',' ',$s));
}
function bluffMatchesTruth(string $answer,string $truth): bool {
    $a=bluffNormal($answer);$b=bluffNormal($truth);
    if($a===$b || str_replace(' ','',$a)===str_replace(' ','',$b))return true;
    $words=fn($s)=>array_values(array_filter(explode(' ',$s),fn($w)=>!in_array($w,['это','был','была','были','его','ее','именно','ответ'],true)));
    $aw=$words($a);$bw=$words($b);sort($aw);sort($bw);
    if($aw===$bw)return true;
    if(!in_array('не',$aw,true)&&count($bw)>0&&count($aw)<=count($bw)+2&&!array_diff($bw,$aw))return true;
    // Spelling guard only. Different numbers and short names remain distinct.
    $a=implode(' ',$aw);$b=implode(' ',$bw);$len=max(mb_strlen($a),mb_strlen($b));
    if(min(mb_strlen($a),mb_strlen($b))<6||preg_match('/\d/u',$a.$b)||in_array('не',$aw,true))return false;
    $x=preg_split('//u',$a,-1,PREG_SPLIT_NO_EMPTY);$y=preg_split('//u',$b,-1,PREG_SPLIT_NO_EMPTY);$row=range(0,count($y));
    foreach($x as $i=>$letter){$next=[$i+1];foreach($y as $j=>$other)$next[]=min($next[$j]+1,$row[$j+1]+1,$row[$j]+($letter===$other?0:1));$row=$next;}
    return end($row)<=($len>=12?2:1);
}
function bluffSchema(): void {
    query("CREATE TABLE IF NOT EXISTS bluff_rooms(room_id TEXT PRIMARY KEY REFERENCES rooms(id),phase TEXT NOT NULL DEFAULT 'lobby',round_no INTEGER NOT NULL DEFAULT 0,chooser TEXT,question_index INTEGER NOT NULL DEFAULT -1,deadline REAL NOT NULL DEFAULT 0,played TEXT NOT NULL DEFAULT '[]',roster TEXT NOT NULL DEFAULT '[]',choices TEXT NOT NULL DEFAULT '[]',scored INTEGER NOT NULL DEFAULT 0)");
    query('CREATE TABLE IF NOT EXISTS bluff_lies(room_id TEXT NOT NULL,round_no INTEGER NOT NULL,player_id TEXT NOT NULL REFERENCES players(id),text TEXT NOT NULL,normal TEXT NOT NULL,PRIMARY KEY(room_id,round_no,player_id))');
    query('CREATE TABLE IF NOT EXISTS bluff_votes(room_id TEXT NOT NULL,round_no INTEGER NOT NULL,player_id TEXT NOT NULL REFERENCES players(id),choice_id TEXT NOT NULL,PRIMARY KEY(room_id,round_no,player_id))');
    query('CREATE TABLE IF NOT EXISTS bluff_author_guesses(room_id TEXT NOT NULL,round_no INTEGER NOT NULL,player_id TEXT NOT NULL REFERENCES players(id),choice_id TEXT NOT NULL,author_id TEXT NOT NULL REFERENCES players(id),PRIMARY KEY(room_id,round_no,player_id))');
    query("CREATE TABLE IF NOT EXISTS bluff_lie_checks(room_id TEXT NOT NULL,round_no INTEGER NOT NULL,player_id TEXT NOT NULL,verdict TEXT NOT NULL,PRIMARY KEY(room_id,round_no,player_id))");
    query("CREATE TABLE IF NOT EXISTS bluff_ai_attempts(room_id TEXT NOT NULL,round_no INTEGER NOT NULL,player_id TEXT NOT NULL,attempts INTEGER NOT NULL,last_attempt REAL NOT NULL,pending TEXT NOT NULL,PRIMARY KEY(room_id,round_no,player_id))");
    query("CREATE TABLE IF NOT EXISTS bluff_ai_cache(room_id TEXT NOT NULL,round_no INTEGER NOT NULL,normal TEXT NOT NULL,verdict TEXT NOT NULL,PRIMARY KEY(room_id,round_no,normal))");
}
/** Called within the API transaction; never hold SQLite's write lock during HTTP. */
function bluffCheckLie(array $b,array $question,array $player,string $text,?callable $transport=null): string {
    global $db;
    if(!getenv('OPENAI_API_KEY')&&$transport===null)return 'uncertain';
    $args=[$b['room_id'],$b['round_no'],$player['id']];$normal=bluffNormal($text);
    $cached=query('SELECT verdict FROM bluff_ai_cache WHERE room_id=? AND round_no=? AND normal=?',[$b['room_id'],$b['round_no'],$normal])->fetchColumn();
    if($cached!==false)return $cached;
    $attempt=query('SELECT * FROM bluff_ai_attempts WHERE room_id=? AND round_no=? AND player_id=?',$args)->fetch();$now=microtime(true);
    if($attempt&&$attempt['pending']!==''&&(float)$attempt['last_attempt']>$now-15)fail('Предыдущий вариант ещё проверяется. Подождите несколько секунд.',429);
    if($attempt&&(int)$attempt['attempts']>=4)return 'uncertain';
    if($attempt&&(float)$attempt['last_attempt']>$now-2)fail('Подождите пару секунд перед новым вариантом.',429);
    $pending=bin2hex(random_bytes(12));
    query('INSERT INTO bluff_ai_attempts VALUES (?,?,?,?,?,?) ON CONFLICT(room_id,round_no,player_id) DO UPDATE SET attempts=attempts+1,last_attempt=excluded.last_attempt,pending=excluded.pending',[...$args,1,$now,$pending]);
    $db->exec('COMMIT');
    // Once the reservation is committed, concurrent players and state polling can proceed.
    try{$verdict=bluffSemanticVerdict($text,$question,$transport);}finally{$db->exec('BEGIN IMMEDIATE');}
    query("UPDATE bluff_ai_attempts SET pending='' WHERE room_id=? AND round_no=? AND player_id=? AND pending=?",[...$args,$pending]);
    $fresh=bluffRow($b['room_id']);
    if(!$fresh||$fresh['phase']!=='write'||(int)$fresh['round_no']!==(int)$b['round_no']||(int)$fresh['question_index']!==(int)$b['question_index']||(float)$fresh['deadline']<=microtime(true))fail('Этап игры изменился во время проверки. Обновите экран.',409);
    if(!query('SELECT id FROM players WHERE id=? AND room_id=?',[$player['id'],$b['room_id']])->fetchColumn())fail('Подключитесь к игре заново.',401);
    if(query('SELECT player_id FROM bluff_lies WHERE room_id=? AND round_no=? AND player_id=?',$args)->fetchColumn())fail('Ваш вариант уже принят.',409);
    if($verdict!=='uncertain')query('INSERT OR IGNORE INTO bluff_ai_cache VALUES (?,?,?,?)',[$b['room_id'],$b['round_no'],$normal,$verdict]);
    return $verdict;
}
function bluffRow(string $id): array {return query('SELECT * FROM bluff_rooms WHERE room_id=?',[$id])->fetch();}
function bluffCategories(array $b,array $quiz): array {$played=json_decode($b['played'],true);$cats=[];foreach($quiz['questions'] as $i=>$q)if(!in_array($i,$played,true))$cats['c:'.$q['category']]=$q['category'];return array_values($cats);}
function bluffQuestion(array $b,array $quiz,string $category): void {
    $played=json_decode($b['played'],true);$available=[];foreach($quiz['questions'] as $i=>$q)if($q['category']===$category&&!in_array($i,$played,true))$available[]=$i;
    if(!$available)fail('Категория уже сыграна. Выберите другую.',409);
    $index=$available[random_int(0,count($available)-1)];$played[]=$index;
    query("UPDATE bluff_rooms SET phase='write',question_index=?,deadline=?,played=?,choices='[]',scored=0 WHERE room_id=?",[$index,microtime(true)+$quiz['questions'][$index]['seconds'],json_encode($played),$b['room_id']]);
}
function bluffStartVote(array $b,array $quiz): void {
    $authorMode=($quiz['mode']??'')==='author';$q=$quiz['questions'][$b['question_index']];$choices=$authorMode?[]:[['id'=>bin2hex(random_bytes(8)),'text'=>$q['truth'],'truth'=>true,'authors'=>[]]];$groups=[];
    foreach(query('SELECT l.player_id,l.text,l.normal,c.verdict FROM bluff_lies l LEFT JOIN bluff_lie_checks c ON c.room_id=l.room_id AND c.round_no=l.round_no AND c.player_id=l.player_id WHERE l.room_id=? AND l.round_no=? ORDER BY l.rowid',[$b['room_id'],$b['round_no']])->fetchAll() as $l){
        if($authorMode){$choices[]=['id'=>bin2hex(random_bytes(8)),'text'=>$l['text'],'truth'=>false,'authors'=>[$l['player_id']],'needsReview'=>false];continue;}
        if(!isset($groups[$l['normal']]))$groups[$l['normal']]=['id'=>bin2hex(random_bytes(8)),'text'=>$l['text'],'truth'=>false,'authors'=>[],'needsReview'=>false];$groups[$l['normal']]['authors'][]=$l['player_id'];if($l['verdict']!=='different')$groups[$l['normal']]['needsReview']=true;
    }
    $choices=array_merge($choices,array_values($groups));shuffle($choices);
    $review=!$authorMode&&(!$groups||array_filter($groups,fn($choice)=>$choice['needsReview']));
    query('UPDATE bluff_rooms SET phase=?,choices=?,deadline=? WHERE room_id=?',[$review?'review':'vote',json_encode($choices,JSON_UNESCAPED_UNICODE),$review?0:microtime(true)+30,$b['room_id']]);
}
function bluffScore(array $b,bool $authorMode=false): void {
    if($b['scored'])return;$choices=[];foreach(json_decode($b['choices'],true) as $c)$choices[$c['id']]=$c;
    $awards=[];$votes=query('SELECT * FROM bluff_votes WHERE room_id=? AND round_no=?',[$b['room_id'],$b['round_no']])->fetchAll();$tallies=[];
    foreach($votes as $v){$c=$choices[$v['choice_id']];$tallies[$c['id']]=($tallies[$c['id']]??0)+1;
        if($authorMode){foreach($c['authors'] as $id)$awards[$id]=($awards[$id]??0)+1000;}
        elseif($c['truth'])$awards[$v['player_id']]=($awards[$v['player_id']]??0)+1000;
        else foreach($c['authors'] as $id)$awards[$id]=($awards[$id]??0)+500;
    }
    if($authorMode&&$tallies){$max=max($tallies);$winning=array_keys(array_filter($tallies,fn($n)=>$n===$max));foreach($winning as $choiceId)foreach($choices[$choiceId]['authors'] as $id)$awards[$id]=($awards[$id]??0)+2000;foreach($votes as $v)if(in_array($v['choice_id'],$winning,true))$awards[$v['player_id']]=($awards[$v['player_id']]??0)+1000;foreach(query('SELECT player_id,choice_id,author_id FROM bluff_author_guesses WHERE room_id=? AND round_no=?',[$b['room_id'],$b['round_no']])->fetchAll() as $guess){if(isset($choices[$guess['choice_id']])&&in_array($guess['author_id'],$choices[$guess['choice_id']]['authors'],true))$awards[$guess['player_id']]=($awards[$guess['player_id']]??0)+1000;}
    }
    foreach($awards as $pid=>$points)query('UPDATE players SET score=score+? WHERE id=?',[$points,$pid]);
    query("UPDATE bluff_rooms SET phase='results',scored=1 WHERE room_id=?",[$b['room_id']]);
}
function bluffAdvance(array $b,array $quiz): array {
    $id=$b['room_id'];$roster=json_decode($b['roster'],true);
    if($b['phase']==='choose'&&microtime(true)>=(float)$b['deadline']){$cats=bluffCategories($b,$quiz);if($cats)bluffQuestion($b,$quiz,$cats[random_int(0,count($cats)-1)]);$b=bluffRow($id);}
    if($b['phase']==='write'&&(microtime(true)>=(float)$b['deadline']||(int)query('SELECT count(*) FROM bluff_lies WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn()>=count($roster))){bluffStartVote($b,$quiz);$b=bluffRow($id);}
    if($b['phase']==='vote'&&(microtime(true)>=(float)$b['deadline']||(int)query('SELECT count(*) FROM bluff_votes WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn()>=count($roster))){if(($quiz['mode']??'')==='author'){query("UPDATE bluff_rooms SET phase='guess',deadline=? WHERE room_id=?",[microtime(true)+30,$id]);}else bluffScore($b);$b=bluffRow($id);}
    if($b['phase']==='guess'&&(microtime(true)>=(float)$b['deadline']||(int)query('SELECT count(*) FROM bluff_author_guesses WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn()>=count($roster))){bluffScore($b,true);$b=bluffRow($id);}
    return $b;
}
function bluffHandle(string $action,array $input,array $room,array $quiz,array $meta,?array $player,bool $projector): array {
    global $admin;$authorMode=($quiz['mode']??'')==='author';bluffSchema();$id=$room['id'];query('INSERT OR IGNORE INTO bluff_rooms(room_id) VALUES (?)',[$id]);$b=bluffAdvance(bluffRow($id),$quiz);
    $roster=json_decode($b['roster'],true);$isPlaying=$player&&in_array($player['id'],$roster,true);
    if($action==='control'){
        hostOnly();if(isset($input['phase'])&&$input['phase']!==$b['phase'])fail('Этап игры уже изменился. Обновите экран.',409);if(isset($input['round'])&&(int)$input['round']!==(int)$b['round_no'])fail('Раунд уже изменился. Обновите экран.',409);$command=$input['command']??'';
        if($command==='next'&&in_array($b['phase'],['lobby','results'],true)){
            if(count(json_decode($b['played'],true))>=count($quiz['questions']))query("UPDATE bluff_rooms SET phase='finished' WHERE room_id=?",[$id]);
            else {$ids=array_column(query('SELECT id FROM players WHERE room_id=? ORDER BY rowid',[$id])->fetchAll(),'id');if(count($ids)<2)fail('Для игры нужны хотя бы два участника.');$round=(int)$b['round_no']+1;
                query("UPDATE bluff_rooms SET phase='choose',round_no=?,chooser=?,roster=?,question_index=-1,deadline=?,choices='[]',scored=0 WHERE room_id=?",[$round,$ids[($round-1)%count($ids)],json_encode($ids),microtime(true)+60,$id]);}
        }elseif($command==='reveal'&&$b['phase']==='write')bluffStartVote($b,$quiz);
        elseif($command==='start_vote'&&$b['phase']==='review')query("UPDATE bluff_rooms SET phase='vote',deadline=? WHERE room_id=?",[microtime(true)+30,$id]);
        elseif($command==='reject_lie'&&$b['phase']==='review'){
            $choices=json_decode($b['choices'],true);$found=false;
            foreach($choices as $i=>$choice)if($choice['id']===($input['choice']??null)&&!$choice['truth']){unset($choices[$i]);$found=true;}
            if(!$found)fail('Можно убрать только выдумку на этапе проверки.',409);
            query('UPDATE bluff_rooms SET choices=? WHERE room_id=?',[json_encode(array_values($choices),JSON_UNESCAPED_UNICODE),$id]);
        }
        elseif($command==='reveal'&&$b['phase']==='vote'&&$authorMode)query("UPDATE bluff_rooms SET phase='guess',deadline=? WHERE room_id=?",[microtime(true)+30,$id]);
        elseif($command==='reveal'&&$b['phase']==='vote')bluffScore($b);
        elseif($command==='reveal'&&$b['phase']==='guess'&&$authorMode)bluffScore($b,true);
        elseif($command==='choose_random'&&$b['phase']==='choose'){$cats=bluffCategories($b,$quiz);bluffQuestion($b,$quiz,$cats[random_int(0,count($cats)-1)]);}
        elseif($command==='finish'){if($b['phase']==='vote')bluffScore($b,$authorMode);query("UPDATE bluff_rooms SET phase='finished' WHERE room_id=?",[$id]);}
        else fail('Это действие сейчас недоступно.',409);
        $b=bluffRow($id);query('UPDATE rooms SET status=? WHERE id=?',[$b['phase']==='finished'?'finished':'bluff',$id]);return ['ok'=>true];
    }
    if(in_array($action,['bluff_select','bluff_lie','bluff_vote','bluff_guess'],true)){
        if(!$isPlaying)fail('Вы сможете участвовать со следующего раунда.',403);
        if((int)($input['round']??0)!==(int)$b['round_no'])fail('Раунд уже изменился. Обновите экран.',409);
        if($action==='bluff_select'){
            if($b['phase']!=='choose'||$player['id']!==$b['chooser'])fail('Сейчас категорию выбирает другой игрок.',403);
            bluffQuestion($b,$quiz,cleanText($input['category']??'',60));return ['ok'=>true];
        }
        if((int)($input['index']??-1)!==(int)$b['question_index'])fail('Вопрос уже изменился.',409);
        $q=$quiz['questions'][$b['question_index']];
        if($action==='bluff_lie'){
            if($b['phase']!=='write')fail('Приём выдумок завершён.',409);
            if(query('SELECT player_id FROM bluff_lies WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn())fail('Ваш вариант уже принят.',409);
            $text=cleanText($input['text']??'',120);$normal=bluffNormal($text);if($normal==='')fail('Добавьте слова или цифры в ответ.');
            $verdict='different';if(!$authorMode){foreach(array_merge([$q['truth']],$q['aliases']??[]) as $truth)if(bluffMatchesTruth($text,$truth))return ['ok'=>true,'accepted'=>false,'matchedTruth'=>true,'message'=>'Этот вариант совпадает с правдой или очень похож на неё. Придумайте другой ложный ответ.'];$verdict=bluffCheckLie($b,$q,$player,$text);if($verdict==='same')return ['ok'=>true,'accepted'=>false,'matchedTruth'=>true,'message'=>'Этот вариант передаёт правильный ответ, даже если написан другими словами. Придумайте другой ложный ответ.'];}
            query('INSERT INTO bluff_lies VALUES (?,?,?,?,?)',[$id,$b['round_no'],$player['id'],$text,$normal]);
            query('INSERT INTO bluff_lie_checks VALUES (?,?,?,?)',[$id,$b['round_no'],$player['id'],$verdict]);return ['ok'=>true,'accepted'=>true];
        }
        if($action==='bluff_guess'){
            if(!$authorMode||$b['phase']!=='guess')fail('Сейчас нельзя угадывать автора.',409);
            $selected=query('SELECT choice_id FROM bluff_votes WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn();if(!$selected)fail('Сначала выберите лучший ответ.',409);
            if(query('SELECT player_id FROM bluff_author_guesses WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn())fail('Вы уже сделали предположение.',409);
            $author=(string)($input['author']??'');$choice=null;foreach(json_decode($b['choices'],true) as $candidate)if($candidate['id']===$selected)$choice=$candidate;
            if(!$choice||!in_array($author,array_column(query('SELECT id FROM players WHERE room_id=?',[$id])->fetchAll(),'id'),true))fail('Выберите участника из списка.',400);
            query('INSERT INTO bluff_author_guesses VALUES (?,?,?,?,?)',[$id,$b['round_no'],$player['id'],$selected,$author]);return ['ok'=>true];
        }
        if($b['phase']!=='vote')fail('Голосование завершено.',409);
        $selected=null;foreach(json_decode($b['choices'],true) as $c)if($c['id']===($input['choice']??null))$selected=$c;
        if(!$selected)fail('Выберите доступный вариант.');if(in_array($player['id'],$selected['authors'],true))fail('Нельзя голосовать за свою выдумку.');
        if(query('SELECT player_id FROM bluff_votes WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn())fail('Ваш голос уже принят.',409);
        query('INSERT INTO bluff_votes VALUES (?,?,?,?)',[$id,$b['round_no'],$player['id'],$selected['id']]);return ['ok'=>true];
    }
    if($action!=='state')fail('В этом режиме используйте выдумки и голосование.',400);
    $b=bluffAdvance($b,$quiz);$revealed=in_array($b['phase'],['results','finished'],true);$question=null;$mine=null;$vote=null;$choices=[];
    if((int)$b['question_index']>=0){$q=$quiz['questions'][$b['question_index']];$question=['text'=>$q['text'],'category'=>$q['category'],'image'=>$q['image'],'seconds'=>$q['seconds']];if($revealed&&!$authorMode){$question['truth']=$q['truth'];$question['reference']=$q['reference'];}}
    $guess=null;if($player){$mine=query('SELECT text FROM bluff_lies WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn();$vote=query('SELECT choice_id FROM bluff_votes WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn();$guess=query('SELECT author_id FROM bluff_author_guesses WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn();}
    $people=query('SELECT id,name,score FROM players WHERE room_id=? ORDER BY score DESC,name',[$id])->fetchAll();$names=array_column($people,'name','id');$rank=0;$last=null;foreach($people as $i=>&$p){$p['score']=(int)$p['score'];if($p['score']!==$last)$rank=$i+1;$p['rank']=$rank;$last=$p['score'];}unset($p);
    $voterNames=[];if($revealed)foreach(query('SELECT player_id,choice_id FROM bluff_votes WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchAll() as $v)$voterNames[$v['choice_id']][]=$names[$v['player_id']]??'Игрок';
    if(in_array($b['phase'],['vote','guess','results','finished'],true))foreach(json_decode($b['choices'],true) as $c){$safe=['id'=>$c['id'],'text'=>$c['text'],'own'=>$player?in_array($player['id'],$c['authors'],true):false];if($revealed){$safe['truth']=$c['truth'];if(!$projector||$authorMode)$safe['authors']=array_map(fn($pid)=>$names[$pid]??'Игрок',$c['authors']);$safe['voterCount']=count($voterNames[$c['id']]??[]);if(!$projector)$safe['voters']=$voterNames[$c['id']]??[];}$choices[]=$safe;}
    $reviewChoices=$admin&&!$player&&!$projector&&$b['phase']==='review'?array_values(array_filter(json_decode($b['choices'],true),fn($choice)=>$choice['truth']||($choice['needsReview']??true))):[];
    return ['semanticCheck'=>!$authorMode&&(bool)getenv('OPENAI_API_KEY'),'reviewChoices'=>$reviewChoices,'id'=>$id,'code'=>$room['code'],'title'=>$quiz['title'],'mode'=>$quiz['mode']??'bluff','status'=>$b['phase'],'round'=>(int)$b['round_no'],'index'=>(int)$b['question_index'],'total'=>count($quiz['questions']),'played'=>count(json_decode($b['played'],true)),'categories'=>bluffCategories($b,$quiz),'chooser'=>$b['chooser'],'chooserName'=>$names[$b['chooser']]??'Игрок','playing'=>$isPlaying,'playerId'=>$player['id']??null,'players'=>$people,'question'=>$question,'choices'=>$choices,'myLie'=>$mine===false?null:$mine,'myVote'=>$vote?:null,'myGuess'=>$guess?:null,'written'=>(int)query('SELECT count(*) FROM bluff_lies WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn(),'answered'=>(int)query('SELECT count(*) FROM bluff_votes WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn(),'guessed'=>(int)query('SELECT count(*) FROM bluff_author_guesses WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn(),'roundPlayers'=>count($roster),'remaining'=>in_array($b['phase'],['choose','write','vote','guess'],true)?max(0,(float)$b['deadline']-microtime(true)):0,'projectorToken'=>$admin&&!$player&&!$projector?$meta['projector_token']:null];
}
