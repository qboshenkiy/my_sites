<?php
declare(strict_types=1);

function standingsSchema(): void {
    global $db;
    $db->exec('CREATE TABLE IF NOT EXISTS published_assessments(
        assessment_id TEXT PRIMARY KEY,title TEXT NOT NULL,max_points REAL NOT NULL,held_on TEXT NOT NULL,
        source_revision INTEGER NOT NULL,published_at INTEGER NOT NULL,published_by TEXT NOT NULL,version INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS published_scores(
        assessment_id TEXT NOT NULL,user_id TEXT NOT NULL,name_at_publish TEXT NOT NULL,points REAL NOT NULL,
        PRIMARY KEY(assessment_id,user_id));
        CREATE INDEX IF NOT EXISTS published_scores_user ON published_scores(user_id);');
}
// The caller owns the transaction; updates happen only on an explicit publication action.
function standingsPublish(array $assessment): void {
    global $me;
    $rows=query('SELECT s.user_id,s.points,u.name FROM assessment_scores s JOIN pulse_accounts u ON u.id=s.user_id WHERE s.assessment_id=?',[$assessment['id']])->fetchAll();
    if(!$rows)fail('Сначала внесите хотя бы один результат.',400);
    query('INSERT INTO published_assessments(assessment_id,title,max_points,held_on,source_revision,published_at,published_by) VALUES (?,?,?,?,?,?,?)
        ON CONFLICT(assessment_id) DO UPDATE SET title=excluded.title,max_points=excluded.max_points,held_on=excluded.held_on,
        source_revision=excluded.source_revision,published_at=excluded.published_at,published_by=excluded.published_by,version=published_assessments.version+1',
        [$assessment['id'],$assessment['title'],$assessment['max_points'],$assessment['held_on'],$assessment['revision'],time(),$me['id']]);
    query('DELETE FROM published_scores WHERE assessment_id=?',[$assessment['id']]);
    foreach($rows as $row)query('INSERT INTO published_scores VALUES (?,?,?,?)',[$assessment['id'],$row['user_id'],$row['name'],(float)$row['points']]);
    communityAudit('publish_results',$assessment['id'],['participants'=>count($rows),'source_revision'=>$assessment['revision']]);
}
function standingsRemove(string $id): void {
    query('DELETE FROM published_scores WHERE assessment_id=?',[$id]);
    query('DELETE FROM published_assessments WHERE assessment_id=?',[$id]);
    communityAudit('unpublish_results',$id);
}
function standingsData(): array {
    $tests=query('SELECT assessment_id AS id,title,max_points,held_on,published_at FROM published_assessments ORDER BY held_on,assessment_id')->fetchAll();
    $maximum=array_sum(array_map(fn($test)=>(float)$test['max_points'],$tests));
    if(!$tests)return ['tests'=>[],'participants'=>[],'max_points'=>0,'published_count'=>0];
    $users=query("SELECT id,name,active FROM pulse_accounts WHERE (active=1 AND role='participant') OR id IN (SELECT user_id FROM published_scores) ORDER BY id")->fetchAll();
    $scores=[];
    foreach(query('SELECT s.* FROM published_scores s JOIN published_assessments a ON a.assessment_id=s.assessment_id')->fetchAll() as $score)$scores[$score['user_id']][$score['assessment_id']]=(float)$score['points'];
    $rows=[];
    foreach($users as $user){
        $values=$scores[$user['id']]??[];$total=array_sum($values);$percent=$maximum>0?round($total/$maximum*100,2):0;
        $rows[]=['id'=>$user['id'],'name'=>$user['name'],'active'=>(bool)$user['active'],'points'=>$total,'percent'=>$percent,'completed'=>count($values),'scores'=>$values];
    }
    usort($rows,fn($a,$b)=>($b['percent']<=>$a['percent'])?:strcmp($a['id'],$b['id']));
    $previous=null;$rank=0;
    foreach($rows as $index=>&$row){if($previous===null||$row['percent']!==$previous)$rank=$index+1;$row['rank']=$rank;$previous=$row['percent'];}unset($row);
    return ['tests'=>$tests,'participants'=>$rows,'max_points'=>$maximum,'published_count'=>count($tests)];
}
function standingsHandle(string $action,array $input): void {
    global $db,$me;
    if($action==='standings'){
        if(!$me)fail('Войдите в аккаунт, чтобы открыть общий рейтинг.',401);
        $db->beginTransaction();$data=standingsData();$db->commit();out($data);
    }
    if(!in_array($action,['publish_results','unpublish_results'],true))return;
    communityStaff();$id=$input['id']??'';
    if(!is_string($id)||!preg_match('/^[a-f0-9]{16}$/D',$id))fail('Некорректная ведомость.');
    $db->exec('BEGIN IMMEDIATE');
    $a=query('SELECT * FROM assessments WHERE id=?',[$id])->fetch();if(!$a)fail('Ведомость не найдена.',404);
    if((int)($input['revision']??0)!==(int)$a['revision'])fail('Ведомость изменилась. Обновите страницу перед публикацией.',409);
    $publication=query('SELECT version FROM published_assessments WHERE assessment_id=?',[$id])->fetch();
    if((int)($input['publication_version']??0)!==(int)($publication['version']??0))fail('Публикация уже изменилась. Обновите страницу.',409);
    if($action==='publish_results')standingsPublish($a);else standingsRemove($id);
    $db->exec('COMMIT');out(['ok'=>true]);
}
