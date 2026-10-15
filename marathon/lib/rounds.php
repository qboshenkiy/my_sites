<?php
declare(strict_types=1);
// A repeat belongs to one calendar week; other weeks and their dates never move.
function weeklyCycle(string $id,int $week): int {
    $v=sql('SELECT cycle FROM weekly_cycle_state WHERE user_id=? AND week=?',[$id,$week])->fetchColumn();
    return $v!==false?(int)$v:(int)sql('SELECT COALESCE(MAX(cycle),0)+1 FROM weekly_repeats WHERE user_id=? AND week=?',[$id,$week])->fetchColumn();
}
function nextWeeklyCycle(string $id,int $week): int {return max(weeklyCycle($id,$week),(int)sql('SELECT COALESCE(MAX(cycle),0) FROM weekly_repeats WHERE user_id=? AND week=?',[$id,$week])->fetchColumn())+1;}
function setWeeklyCycle(string $id,int $week,int $cycle): void {sql('INSERT INTO weekly_cycle_state VALUES (?,?,?) ON CONFLICT(user_id,week) DO UPDATE SET cycle=excluded.cycle',[$id,$week,$cycle]);}
function clearCycleData(string $id,int $week,string $actor): void {
    sql('DELETE FROM reading_entries WHERE user_id=? AND week=?',[$id,$week]);sql('DELETE FROM week_completions WHERE user_id=? AND week=?',[$id,$week]);
    sql('UPDATE reports SET chapters_manual=0,chapters_override=NULL,days_manual=NULL,editor_id=?,updated_at=? WHERE user_id=? AND week=?',[$actor,time(),$id,$week]);
    sql('DELETE FROM reports WHERE user_id=? AND week=? AND pages=0 AND minutes=0 AND books=0',[$id,$week]);
}
function restoreCycleData(array $snapshot): void {
    // These rows originate only from server-created snapshots, never request JSON.
    foreach(['reports'=>array_filter([$snapshot['report']??null]),'reading_entries'=>$snapshot['entries']??[],'week_completions'=>array_filter([$snapshot['completion']??null])] as $table=>$rows){
        $allowed=array_column(sql('PRAGMA table_info('.$table.')')->fetchAll(),'name');
        foreach($rows as $row){if($table==='reports'){$legacy=sql('SELECT pages,minutes,books FROM reports WHERE user_id=? AND week=?',[$row['user_id'],$row['week']])->fetch();if($legacy)$row=array_replace($row,$legacy);}$row=array_intersect_key($row,array_flip($allowed));$cols=array_keys($row);sql('INSERT OR REPLACE INTO '.$table.' ('.implode(',',$cols).') VALUES ('.implode(',',array_fill(0,count($cols),'?')).')',array_values($row));}
    }
}
function changeWeeklyCycle(string $id,string $actor,int $week,int $cycle,int $expected,bool $restore=false): array {
    $u=user($id);$a=user($actor);if(!$u||!$a||!$u['active'])throw new DomainException('Аккаунт недоступен.');
    if($actor!==$id&&$a['role']!=='admin')throw new DomainException('Удалять чужие круги может только администратор.');
    if($week>calendar($id)['current'])throw new DomainException('Эта неделя ещё не началась.');
    $current=weeklyCycle($id,$week);if($current!==$expected)throw new DomainException('Текущий круг изменился. Обновите страницу.');
    setWeeklyCycle($id,$week,$current);
    $row=sql('SELECT * FROM weekly_repeats WHERE user_id=? AND week=? AND cycle=?',[$id,$week,$cycle])->fetch();
    if($restore){
        if(!$row||$row['deleted_at']===null)throw new DomainException('Удалённый круг не найден.');
        setWeeklyCycle($id,$week,$current);sql('UPDATE weekly_repeats SET deleted_at=NULL WHERE user_id=? AND week=? AND cycle=?',[$id,$week,$cycle]);
    }elseif($cycle===$current){
        $w=weekResults($id)[$week-1];$saved=$w;unset($saved['repeats'],$saved['deletedRepeats']);
        $snapshot=['result'=>$saved,'report'=>sql('SELECT * FROM reports WHERE user_id=? AND week=?',[$id,$week])->fetch()?:null,'entries'=>sql('SELECT * FROM reading_entries WHERE user_id=? AND week=?',[$id,$week])->fetchAll(),'completion'=>sql('SELECT * FROM week_completions WHERE user_id=? AND week=?',[$id,$week])->fetch()?:null];
        sql('INSERT INTO weekly_repeats(user_id,week,cycle,snapshot,created_at,deleted_at) VALUES (?,?,?,?,?,?)',[$id,$week,$cycle,json_encode($snapshot,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),time(),time()]);
        clearCycleData($id,$week,$actor);
        $previous=sql('SELECT * FROM weekly_repeats WHERE user_id=? AND week=? AND deleted_at IS NULL ORDER BY cycle DESC LIMIT 1',[$id,$week])->fetch();
        if($previous){restoreCycleData(json_decode($previous['snapshot'],true,512,JSON_THROW_ON_ERROR));sql('DELETE FROM weekly_repeats WHERE user_id=? AND week=? AND cycle=?',[$id,$week,$previous['cycle']]);setWeeklyCycle($id,$week,(int)$previous['cycle']);}
        else setWeeklyCycle($id,$week,nextWeeklyCycle($id,$week));
    }else{
        if(!$row||$row['deleted_at']!==null)throw new DomainException('Круг уже удалён или не найден.');
        setWeeklyCycle($id,$week,$current);sql('UPDATE weekly_repeats SET deleted_at=? WHERE user_id=? AND week=? AND cycle=?',[time(),$id,$week,$cycle]);
    }
    sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$id]);sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$id]);
    audit($actor,$restore?'restore_weekly_cycle':'delete_weekly_cycle',$id,'Неделя '.$week.', круг '.$cycle.($restore?' восстановлен в истории':' удалён в архив'));
    return weekResults($id)[$week-1];
}
function weeklyRepeats(string $id,int $week,bool $deleted=false): array {
    return array_map(fn($r)=>json_decode($r['snapshot'],true,512,JSON_THROW_ON_ERROR)['result'],sql('SELECT snapshot FROM weekly_repeats WHERE user_id=? AND week=? AND deleted_at IS '.($deleted?'NOT NULL':'NULL').' ORDER BY cycle',[$id,$week])->fetchAll());
}
function startWeeklyRepeat(string $id,string $actor,int $week,int $expected): array {
    $u=user($id);if(!$u||!$u['active'])throw new DomainException('Аккаунт недоступен.');
    $c=calendar($id);if($week!==$c['current'])throw new DomainException('Повторное чтение можно начать только для текущей недели.');
    $w=weekResults($id)[$week-1];
    if($w['cycle']!==$expected)throw new DomainException('Круг недели уже изменился. Обновите план.');
    if(!$w['completed'])throw new DomainException('Сначала полностью завершите текущий круг недели.');
    $next=nextWeeklyCycle($id,$week);$archived=$w;unset($archived['repeats'],$archived['deletedRepeats']);
    $snapshot=['result'=>$archived,'report'=>sql('SELECT * FROM reports WHERE user_id=? AND week=?',[$id,$week])->fetch()?:null,'entries'=>sql('SELECT * FROM reading_entries WHERE user_id=? AND week=?',[$id,$week])->fetchAll(),'completion'=>sql('SELECT * FROM week_completions WHERE user_id=? AND week=?',[$id,$week])->fetch()?:null];
    sql('INSERT INTO weekly_repeats(user_id,week,cycle,snapshot,created_at) VALUES (?,?,?,?,?)',[$id,$week,$expected,json_encode($snapshot,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),time()]);
    sql('DELETE FROM reading_entries WHERE user_id=? AND week=?',[$id,$week]);
    sql('DELETE FROM week_completions WHERE user_id=? AND week=?',[$id,$week]);
    sql("UPDATE reports SET chapters_manual=0,chapters_override=NULL,days_manual=NULL,editor_id=?,updated_at=? WHERE user_id=? AND week=?",[$actor,time(),$id,$week]);
    sql('DELETE FROM reports WHERE user_id=? AND week=? AND pages=0 AND minutes=0 AND books=0',[$id,$week]);
    sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$id]);sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$id]);
    setWeeklyCycle($id,$week,$next);
    audit($actor,'weekly_repeat',$id,'Неделя '.$week.': начат круг '.$next.', предыдущий результат сохранён.');
    return weekResults($id)[$week-1];
}
function visibleCalendar(array $c,bool $admin): array {
    if(!$admin)$c['calendar']=array_values(array_filter($c['calendar'],fn($w)=>$w['number']<=$c['current']));return $c;
}
function activeRound(string $id): ?array {return sql('SELECT * FROM reading_rounds WHERE user_id=? ORDER BY number DESC LIMIT 1',[$id])->fetch()?:null;}
function readingRounds(string $id): array {
    $rows=sql('SELECT number,start,snapshot,created_at FROM reading_rounds WHERE user_id=? ORDER BY number',[$id])->fetchAll();
    if(!$rows)return [['number'=>1,'start'=>setting('start'),'active'=>true,'chapters'=>null]];
    return array_map(function($r){$snapshot=$r['snapshot']?json_decode($r['snapshot'],true):null;return ['number'=>(int)$r['number'],'start'=>$r['start'],'active'=>$snapshot===null,'chapters'=>$snapshot['stats']['chapters']??null];},$rows);
}
function startReadingRound(string $id,string $actor,int $expectedRound): array {
    $u=user($id);if(!$u||!$u['active'])throw new DomainException('Аккаунт недоступен.');
    $c=calendar($id);if($c['round']!==$expectedRound)throw new DomainException('Круг уже изменился. Откройте меню кругов заново.');
    $stats=stats($id);if($stats['goalWeeks']!==22)throw new DomainException('Новый круг доступен после выполнения всех 22 недель. Сейчас выполнено '.$stats['goalWeeks'].' из 22.');
    $archive=['stats'=>$stats,'marathon'=>$c,'raw'=>['reports'=>sql('SELECT * FROM reports WHERE user_id=?',[$id])->fetchAll(),'entries'=>sql('SELECT * FROM reading_entries WHERE user_id=?',[$id])->fetchAll(),'completions'=>sql('SELECT * FROM week_completions WHERE user_id=?',[$id])->fetchAll()]];
    $plans=json_encode($c['calendar'],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);$snapshot=json_encode($archive,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR);
    sql('INSERT INTO reading_rounds(user_id,number,start,plans,snapshot,created_at) VALUES (?,?,?,?,?,?) ON CONFLICT(user_id,number) DO UPDATE SET snapshot=excluded.snapshot',[$id,$expectedRound,$c['start'],$plans,$snapshot,time()]);
    $next=$expectedRound+1;sql('INSERT INTO reading_rounds(user_id,number,start,plans,created_at) VALUES (?,?,?,?,?)',[$id,$next,$c['today'],$plans,time()]);
    sql('DELETE FROM reading_entries WHERE user_id=?',[$id]);sql('DELETE FROM week_completions WHERE user_id=?',[$id]);sql('DELETE FROM reports WHERE user_id=?',[$id]);
    sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$id]);sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$id]);
    audit($actor,'start_round',$id,'Начат круг '.$next.'. Предыдущий круг сохранён в истории.');return calendar($id);
}
function archivedReadingRound(string $id,int $number): array {
    $snapshot=sql('SELECT snapshot FROM reading_rounds WHERE user_id=? AND number=?',[$id,$number])->fetchColumn();
    if(!$snapshot)throw new DomainException('Завершённый круг не найден.');return json_decode($snapshot,true,512,JSON_THROW_ON_ERROR);
}
