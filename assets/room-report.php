<?php
declare(strict_types=1);

function roomReportSchema(): void {
    global $db;
    if(query("SELECT value FROM settings WHERE key='room_report_schema'")->fetchColumn())return;
    $db->exec('BEGIN IMMEDIATE');
    foreach(['assessments'=>['source_room_id'=>'TEXT','source_max_override'=>'REAL','score_basis'=>"TEXT NOT NULL DEFAULT 'manual'"], 'rooms'=>['link_revision'=>'INTEGER NOT NULL DEFAULT 0']] as $table=>$columns){
        $existing=array_column(query('PRAGMA table_info('.$table.')')->fetchAll(),'name');
        foreach($columns as $name=>$type)if(!in_array($name,$existing,true))$db->exec("ALTER TABLE $table ADD COLUMN $name $type");
    }
    $db->exec('CREATE UNIQUE INDEX IF NOT EXISTS assessment_source_room ON assessments(source_room_id) WHERE source_room_id IS NOT NULL');
    query("INSERT OR REPLACE INTO settings VALUES ('room_report_schema','1')");$db->exec('COMMIT');
}
function roomReportMaximum(array $room): array {
    $quiz=json_decode($room['quiz'],true);$mode=$quiz['mode']??'classic';
    $best=(float)(query('SELECT COALESCE(MAX(score),0) FROM players WHERE room_id=?',[$room['id']])->fetchColumn());
    if($mode==='bluff')return ['points'=>$best,'basis'=>'leader','label'=>'В Бредовухе 100% — лучший результат этой игры.'];
    $played=$mode==='board'?json_decode(query('SELECT played FROM room_meta WHERE room_id=?',[$room['id']])->fetchColumn()?:'[]',true):null;
    $max=0;
    foreach($quiz['questions']??[] as $index=>$q){
        $wasPlayed=$mode==='board'?in_array($index,$played??[],true):$index<=(int)$room['current_index'];
        if($wasPlayed&&($q['type']??'quiz')==='quiz')$max+=(int)($q['points']??1000);
    }
    return ['points'=>$max,'basis'=>'questions','label'=>'100% — сумма максимальных баллов за проведённые вопросы. Опросы без правильного ответа не учитываются.'];
}
// Caller owns the write transaction. Never changes game answers or player scores.
function syncRoomReport(array $room,bool $setOverride=false,?float $override=null): array {
    global $me;
    $old=query('SELECT * FROM assessments WHERE source_room_id=?',[$room['id']])->fetch();
    if($room['status']!=='finished')return ['assessment'=>null,'warning'=>'Ведомость появится после завершения игры.'];
    $maximum=roomReportMaximum($room);
    $manual=$setOverride?$override:($old['source_max_override']??null);
    $max=$manual??$maximum['points'];
    $players=query('SELECT id,user_id,score FROM players WHERE room_id=? AND user_id IS NOT NULL ORDER BY user_id',[$room['id']])->fetchAll();
    $best=(float)(query('SELECT COALESCE(MAX(score),0) FROM players WHERE room_id=?',[$room['id']])->fetchColumn());
    if($max<=0||$max<$best)return ['assessment'=>$old['id']??null,'warning'=>'Укажите максимум баллов не меньше лучшего результата игры.'];
    if(!$players&&!$old)return ['assessment'=>null,'warning'=>'Сопоставьте хотя бы одного игрока — ведомость создастся автоматически.'];
    $id=$old['id']??bin2hex(random_bytes(8));$quiz=json_decode($room['quiz'],true);
    $basis=$manual!==null?'custom':$maximum['basis'];
    $before=$old?query('SELECT user_id,points FROM assessment_scores WHERE assessment_id=? ORDER BY user_id',[$id])->fetchAll():[];
    $after=array_map(fn($p)=>['user_id'=>$p['user_id'],'points'=>(float)$p['score']],$players);
    if($old&&(float)$old['max_points']===(float)$max&&$old['score_basis']===$basis&&$before==$after)return ['assessment'=>$id,'warning'=>null];
    if(!$old)query('INSERT INTO assessments(id,title,max_points,owner_id,held_on,created_at,source_room_id,source_max_override,score_basis) VALUES (?,?,?,?,?,?,?,?,?)',[$id,mb_substr($quiz['title'],0,100),$max,$me['id'],date('Y-m-d',(int)$room['created_at']),time(),$room['id'],$manual,$basis]);
    else query('UPDATE assessments SET max_points=?,source_max_override=?,score_basis=?,revision=revision+1 WHERE id=?',[$max,$manual,$basis,$id]);
    query('DELETE FROM assessment_scores WHERE assessment_id=?',[$id]);
    foreach($players as $p)query('INSERT INTO assessment_scores VALUES (?,?,?,?,?,?)',[$id,$p['user_id'],(float)$p['score'],'',time(),$me['id']]);
    communityAudit('sync_room_report',$id,['room'=>$room['id'],'participants'=>count($players),'max_points'=>$max]);
    return ['assessment'=>$id,'warning'=>null];
}
function roomReportHandle(string $action,array $input): void {
    global $db;
    if($action!=='link_room_players')return;
    communityStaff();$db->exec('BEGIN IMMEDIATE');
    $room=query('SELECT * FROM rooms WHERE id=?',[$input['room']??''])->fetch();
    if(!$room||!communityOwn($room))fail('Игра не найдена.',404);
    if((int)($input['revision']??-1)!==(int)$room['link_revision'])fail('Связи уже изменены. Обновите страницу игры.',409);
    $links=$input['links']??null;if(!is_array($links)||count($links)>500)fail('Некорректный список игроков.');
    $players=query('SELECT id,user_id FROM players WHERE room_id=? ORDER BY id',[$room['id']])->fetchAll();
    if(count($players)!==count($links))fail('Состав игроков изменился. Откройте игру заново.',409);
    $seen=[];$users=[];$byId=array_column($players,null,'id');
    foreach($links as $link){
        if(!is_array($link))fail('Некорректная связь игрока.');
        $pid=$link['player_id']??'';$uid=$link['user_id']??null;
        if(!is_string($pid)||!isset($byId[$pid])||isset($seen[$pid]))fail('Некорректный игрок.');$seen[$pid]=true;
        if($uid!==null){
            if(!is_string($uid)||isset($users[$uid]))fail('Один аккаунт нельзя назначить двум игрокам.',409);
            $u=query('SELECT * FROM pulse_accounts WHERE id=?',[$uid])->fetch();
            if(!$u||(!$u['active']&&$byId[$pid]['user_id']!==$uid))fail('Выберите активного участника.');$users[$uid]=true;
        }
    }
    $override=$input['max_points']??null;
    if($override!==null&&(!is_numeric($override)||!is_finite((float)$override)||(float)$override<=0||(float)$override>100000000))fail('Укажите положительный максимум баллов.');
    $recommended=roomReportMaximum($room);$max=$override??$recommended['points'];
    $best=(float)(query('SELECT COALESCE(MAX(score),0) FROM players WHERE room_id=?',[$room['id']])->fetchColumn());
    if($room['status']==='finished'&&count($users)&&($max<=0||$max<$best))fail('Максимум должен быть положительным и не меньше '.$best.' баллов.');
    // Clear first, so swapping two accounts is atomic under the unique constraint.
    query('UPDATE players SET user_id=NULL WHERE room_id=?',[$room['id']]);
    foreach($links as $link)query('UPDATE players SET user_id=? WHERE id=?',[$link['user_id']??null,$link['player_id']]);
    query('UPDATE rooms SET link_revision=link_revision+1 WHERE id=?',[$room['id']]);
    communityAudit('link_room_players',$room['id'],['before'=>$players,'after'=>$links]);
    $report=syncRoomReport($room,true,$override!==null?(float)$override:null);
    $db->exec('COMMIT');out(['ok'=>true]+$report);
}
