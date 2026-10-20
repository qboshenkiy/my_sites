<?php
declare(strict_types=1);
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){http_response_code(404);exit;}
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
    $q=$quiz['questions'][$b['question_index']];$choices=[['id'=>bin2hex(random_bytes(8)),'text'=>$q['truth'],'truth'=>true,'authors'=>[]]];$groups=[];
    foreach(query('SELECT player_id,text,normal FROM bluff_lies WHERE room_id=? AND round_no=? ORDER BY rowid',[$b['room_id'],$b['round_no']])->fetchAll() as $l){
        if(!isset($groups[$l['normal']]))$groups[$l['normal']]=['id'=>bin2hex(random_bytes(8)),'text'=>$l['text'],'truth'=>false,'authors'=>[]];$groups[$l['normal']]['authors'][]=$l['player_id'];
    }
    $choices=array_merge($choices,array_values($groups));shuffle($choices);
    query("UPDATE bluff_rooms SET phase='review',choices=?,deadline=0 WHERE room_id=?",[json_encode($choices,JSON_UNESCAPED_UNICODE),$b['room_id']]);
}
function bluffScore(array $b): void {
    if($b['scored'])return;$choices=[];foreach(json_decode($b['choices'],true) as $c)$choices[$c['id']]=$c;
    $awards=[];foreach(query('SELECT * FROM bluff_votes WHERE room_id=? AND round_no=?',[$b['room_id'],$b['round_no']])->fetchAll() as $v){$c=$choices[$v['choice_id']];
        if($c['truth'])$awards[$v['player_id']]=($awards[$v['player_id']]??0)+1000;
        else foreach($c['authors'] as $id)$awards[$id]=($awards[$id]??0)+500;
    }
    foreach($awards as $pid=>$points)query('UPDATE players SET score=score+? WHERE id=?',[$points,$pid]);
    query("UPDATE bluff_rooms SET phase='results',scored=1 WHERE room_id=?",[$b['room_id']]);
}
function bluffAdvance(array $b,array $quiz): array {
    $id=$b['room_id'];$roster=json_decode($b['roster'],true);
    if($b['phase']==='choose'&&microtime(true)>=(float)$b['deadline']){$cats=bluffCategories($b,$quiz);if($cats)bluffQuestion($b,$quiz,$cats[random_int(0,count($cats)-1)]);$b=bluffRow($id);}
    if($b['phase']==='write'&&(microtime(true)>=(float)$b['deadline']||(int)query('SELECT count(*) FROM bluff_lies WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn()>=count($roster))){bluffStartVote($b,$quiz);$b=bluffRow($id);}
    if($b['phase']==='vote'&&(microtime(true)>=(float)$b['deadline']||(int)query('SELECT count(*) FROM bluff_votes WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn()>=count($roster))){bluffScore($b);$b=bluffRow($id);}
    return $b;
}
function bluffHandle(string $action,array $input,array $room,array $quiz,array $meta,?array $player,bool $projector): array {
    global $admin;bluffSchema();$id=$room['id'];query('INSERT OR IGNORE INTO bluff_rooms(room_id) VALUES (?)',[$id]);$b=bluffAdvance(bluffRow($id),$quiz);
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
        elseif($command==='reveal'&&$b['phase']==='vote')bluffScore($b);
        elseif($command==='choose_random'&&$b['phase']==='choose'){$cats=bluffCategories($b,$quiz);bluffQuestion($b,$quiz,$cats[random_int(0,count($cats)-1)]);}
        elseif($command==='finish'){if($b['phase']==='vote')bluffScore($b);query("UPDATE bluff_rooms SET phase='finished' WHERE room_id=?",[$id]);}
        else fail('Это действие сейчас недоступно.',409);
        $b=bluffRow($id);query('UPDATE rooms SET status=? WHERE id=?',[$b['phase']==='finished'?'finished':'bluff',$id]);return ['ok'=>true];
    }
    if(in_array($action,['bluff_select','bluff_lie','bluff_vote'],true)){
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
            foreach(array_merge([$q['truth']],$q['aliases']??[]) as $truth)if(bluffMatchesTruth($text,$truth))return ['ok'=>true,'accepted'=>false,'matchedTruth'=>true,'message'=>'Этот вариант совпадает с правдой или очень похож на неё. Придумайте другой ложный ответ.'];
            query('INSERT INTO bluff_lies VALUES (?,?,?,?,?)',[$id,$b['round_no'],$player['id'],$text,$normal]);return ['ok'=>true,'accepted'=>true];
        }
        if($b['phase']!=='vote')fail('Голосование завершено.',409);
        $selected=null;foreach(json_decode($b['choices'],true) as $c)if($c['id']===($input['choice']??null))$selected=$c;
        if(!$selected)fail('Выберите доступный вариант.');if(in_array($player['id'],$selected['authors'],true))fail('Нельзя голосовать за свою выдумку.');
        if(query('SELECT player_id FROM bluff_votes WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn())fail('Ваш голос уже принят.',409);
        query('INSERT INTO bluff_votes VALUES (?,?,?,?)',[$id,$b['round_no'],$player['id'],$selected['id']]);return ['ok'=>true];
    }
    if($action!=='state')fail('В этом режиме используйте выдумки и голосование.',400);
    $b=bluffAdvance($b,$quiz);$revealed=in_array($b['phase'],['results','finished'],true);$question=null;$mine=null;$vote=null;$choices=[];
    if((int)$b['question_index']>=0){$q=$quiz['questions'][$b['question_index']];$question=['text'=>$q['text'],'category'=>$q['category'],'image'=>$q['image'],'seconds'=>$q['seconds']];if($revealed){$question['truth']=$q['truth'];$question['reference']=$q['reference'];}}
    if($player){$mine=query('SELECT text FROM bluff_lies WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn();$vote=query('SELECT choice_id FROM bluff_votes WHERE room_id=? AND round_no=? AND player_id=?',[$id,$b['round_no'],$player['id']])->fetchColumn();}
    $people=query('SELECT id,name,score FROM players WHERE room_id=? ORDER BY score DESC,name',[$id])->fetchAll();$names=array_column($people,'name','id');$rank=0;$last=null;foreach($people as $i=>&$p){$p['score']=(int)$p['score'];if($p['score']!==$last)$rank=$i+1;$p['rank']=$rank;$last=$p['score'];}unset($p);
    $voterNames=[];if($revealed)foreach(query('SELECT player_id,choice_id FROM bluff_votes WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchAll() as $v)$voterNames[$v['choice_id']][]=$names[$v['player_id']]??'Игрок';
    if(in_array($b['phase'],['vote','results','finished'],true))foreach(json_decode($b['choices'],true) as $c){$safe=['id'=>$c['id'],'text'=>$c['text'],'own'=>$player?in_array($player['id'],$c['authors'],true):false];if($revealed){$safe['truth']=$c['truth'];if(!$projector)$safe['authors']=array_map(fn($pid)=>$names[$pid]??'Игрок',$c['authors']);$safe['voterCount']=count($voterNames[$c['id']]??[]);if(!$projector)$safe['voters']=$voterNames[$c['id']]??[];}$choices[]=$safe;}
    $reviewChoices=$admin&&!$player&&!$projector&&$b['phase']==='review'?json_decode($b['choices'],true):[];
    return ['reviewChoices'=>$reviewChoices,'id'=>$id,'code'=>$room['code'],'title'=>$quiz['title'],'mode'=>'bluff','status'=>$b['phase'],'round'=>(int)$b['round_no'],'index'=>(int)$b['question_index'],'total'=>count($quiz['questions']),'played'=>count(json_decode($b['played'],true)),'categories'=>bluffCategories($b,$quiz),'chooser'=>$b['chooser'],'chooserName'=>$names[$b['chooser']]??'Игрок','playing'=>$isPlaying,'playerId'=>$player['id']??null,'players'=>$people,'question'=>$question,'choices'=>$choices,'myLie'=>$mine===false?null:$mine,'myVote'=>$vote?:null,'written'=>(int)query('SELECT count(*) FROM bluff_lies WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn(),'answered'=>(int)query('SELECT count(*) FROM bluff_votes WHERE room_id=? AND round_no=?',[$id,$b['round_no']])->fetchColumn(),'roundPlayers'=>count($roster),'remaining'=>in_array($b['phase'],['choose','write','vote'],true)?max(0,(float)$b['deadline']-microtime(true)):0,'projectorToken'=>$admin&&!$player&&!$projector?$meta['projector_token']:null];
}
