<?php
declare(strict_types=1);
// A repeat belongs to one calendar week; other weeks and their dates never move.
function weeklyRepeats(string $id,int $week): array {
    return array_map(fn($r)=>json_decode($r['snapshot'],true,512,JSON_THROW_ON_ERROR)['result'],sql('SELECT snapshot FROM weekly_repeats WHERE user_id=? AND week=? ORDER BY cycle',[$id,$week])->fetchAll());
}
function startWeeklyRepeat(string $id,string $actor,int $week,int $expected): array {
    $u=user($id);if(!$u||!$u['active'])throw new DomainException('Аккаунт недоступен.');
    $c=calendar($id);if($week!==$c['current'])throw new DomainException('Повторное чтение можно начать только для текущей недели.');
    $w=weekResults($id)[$week-1];
    if($w['cycle']!==$expected)throw new DomainException('Круг недели уже изменился. Обновите план.');
    if(!$w['completed'])throw new DomainException('Сначала полностью завершите текущий круг недели.');
    $archived=$w;unset($archived['repeats']);
    $snapshot=['result'=>$archived,'report'=>sql('SELECT * FROM reports WHERE user_id=? AND week=?',[$id,$week])->fetch()?:null,'entries'=>sql('SELECT * FROM reading_entries WHERE user_id=? AND week=?',[$id,$week])->fetchAll(),'completion'=>sql('SELECT * FROM week_completions WHERE user_id=? AND week=?',[$id,$week])->fetch()?:null];
    sql('INSERT INTO weekly_repeats(user_id,week,cycle,snapshot,created_at) VALUES (?,?,?,?,?)',[$id,$week,$expected,json_encode($snapshot,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),time()]);
    sql('DELETE FROM reading_entries WHERE user_id=? AND week=?',[$id,$week]);
    sql('DELETE FROM week_completions WHERE user_id=? AND week=?',[$id,$week]);
    sql("UPDATE reports SET chapters_manual=0,chapters_override=NULL,days_manual=NULL,editor_id=?,updated_at=? WHERE user_id=? AND week=?",[$actor,time(),$id,$week]);
    sql('DELETE FROM reports WHERE user_id=? AND week=? AND pages=0 AND minutes=0 AND books=0',[$id,$week]);
    sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$id]);sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$id]);
    audit($actor,'weekly_repeat',$id,'Неделя '.$week.': начат круг '.($expected+1).', предыдущий результат сохранён.');
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
