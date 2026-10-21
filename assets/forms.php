<?php
declare(strict_types=1);
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){http_response_code(404);exit;}

function formsSchema(): void {
    global $db;
    $db->exec("CREATE TABLE IF NOT EXISTS pulse_forms(
        id TEXT PRIMARY KEY,token TEXT UNIQUE NOT NULL,owner_id TEXT NOT NULL,title TEXT NOT NULL,description TEXT NOT NULL,
        quiz TEXT NOT NULL,active INTEGER NOT NULL DEFAULT 1,published INTEGER NOT NULL DEFAULT 0,
        require_account INTEGER NOT NULL DEFAULT 0,created_at INTEGER NOT NULL,revision INTEGER NOT NULL DEFAULT 1,assessment_id TEXT);
        CREATE TABLE IF NOT EXISTS form_attempts(id TEXT PRIMARY KEY,form_id TEXT NOT NULL REFERENCES pulse_forms(id),
        user_id TEXT,name TEXT NOT NULL,guest_key TEXT NOT NULL,answers TEXT NOT NULL,points REAL NOT NULL,max_points REAL NOT NULL,
        submitted_at INTEGER NOT NULL,source TEXT NOT NULL,UNIQUE(form_id,guest_key));
        CREATE UNIQUE INDEX IF NOT EXISTS form_account_attempt ON form_attempts(form_id,user_id) WHERE user_id IS NOT NULL;
        CREATE INDEX IF NOT EXISTS form_attempt_list ON form_attempts(form_id,submitted_at);");
}
function formOwned(string $id): array {
    hostOnly();$form=query('SELECT * FROM pulse_forms WHERE id=?',[$id])->fetch();
    if(!$form||!communityOwn($form))fail('Тест не найден.',404);return $form;
}
function formGuestKey(): string {
    global $me;
    return $me?'u:'.$me['id']:'w:'.hash('sha256',session_id());
}
function formAttempt(array $form): array|false {
    return query('SELECT * FROM form_attempts WHERE form_id=? AND guest_key=?',[$form['id'],formGuestKey()])->fetch();
}
function formScore(array $form,array $answers,bool $allowMissing=false): array {
    $questions=json_decode($form['quiz'],true)['questions'];
    if(!$allowMissing&&count($answers)!==count($questions))fail('Ответьте на все вопросы.');
    $points=0;$max=0;$valid=[];
    foreach($questions as $i=>$q){
        $choice=$answers[$i]??null;$selected=$choice===null?[]:(is_array($choice)?$choice:[$choice]);
        if($choice!==null&&(!$selected||array_filter($selected,fn($n)=>!is_int($n)||!array_key_exists($n,$q['options']))))fail('Некорректный ответ на вопрос '.($i+1).'.');
        $selectedUnique=array_values(array_unique($selected));sort($selectedUnique);if(count($selected)!==count($selectedUnique))fail('Некорректный ответ на вопрос '.($i+1).'.');
        if(!$allowMissing&&$choice===null)fail('Ответьте на вопрос '.($i+1).'.');
        $valid[]=$choice===null?null:(count($selectedUnique)===1?$selectedUnique[0]:$selectedUnique);
        if($q['type']==='quiz'){$max+=(int)$q['points'];$expected=$q['correct']??null;$expected=is_array($expected)?array_map('intval',$expected):[$expected===null?-1:(int)$expected];sort($expected);if($choice!==null&&$selectedUnique===$expected)$points+=(int)$q['points'];}
    }
    return ['answers'=>$valid,'points'=>$points,'max_points'=>$max];
}
function formSyncAssessment(array $form): ?string {
    if(!$form['published'])return null;
    $old=$form['assessment_id']?query('SELECT * FROM assessments WHERE id=?',[$form['assessment_id']])->fetch():false;
    if($old&&!empty($old['source_edited']))return $old['id'];
    $rows=query('SELECT * FROM form_attempts WHERE form_id=? AND user_id IS NOT NULL',[$form['id']])->fetchAll();
    if(!$rows&&!$old)return null;
    $max=formScore($form,[],true)['max_points'];if($max<=0)return null;
    $id=$old['id']??bin2hex(random_bytes(8));
    if(!$old)query('INSERT INTO assessments(id,title,max_points,owner_id,held_on,created_at,source_form_id,score_basis) VALUES (?,?,?,?,?,?,?,?)',[$id,$form['title'],$max,$form['owner_id'],date('Y-m-d',(int)$form['created_at']),time(),$form['id'],'form']);
    else query('UPDATE assessments SET revision=revision+1 WHERE id=?',[$id]);
    query('DELETE FROM assessment_scores WHERE assessment_id=?',[$id]);
    foreach($rows as $row)query('INSERT INTO assessment_scores VALUES (?,?,?,?,?,?)',[$id,$row['user_id'],$row['points'],'Проверено автоматически',time(),$form['owner_id']]);
    query('UPDATE pulse_forms SET assessment_id=? WHERE id=?',[$id,$form['id']]);return $id;
}
function formStoreAttempt(array $form,?string $uid,string $key,string $name,array $answers,string $source,bool $allowMissing=false): array {
    $existing=query('SELECT * FROM form_attempts WHERE form_id=? AND (guest_key=? OR (? IS NOT NULL AND user_id=?))',[$form['id'],$key,$uid,$uid])->fetch();
    if($existing)return $existing;
    $score=formScore($form,$answers,$allowMissing);$id=bin2hex(random_bytes(8));
    query('INSERT INTO form_attempts VALUES (?,?,?,?,?,?,?,?,?,?)',[$id,$form['id'],$uid,mb_substr($name,0,80),$key,json_encode($score['answers']),$score['points'],$score['max_points'],time(),$source]);
    formSyncAssessment($form);return query('SELECT * FROM form_attempts WHERE id=?',[$id])->fetch();
}
function formPublic(array $form,array|false $attempt): array {
    if($attempt&&$form['published'])$attempt=formAdjustedAttempt($form,$attempt);
    $quiz=json_decode($form['quiz'],true);$questions=[];
    foreach($quiz['questions'] as $i=>$q){
        $safe=array_intersect_key($q,array_flip(['text','options','type','image','points','category','multiple']));
        if($attempt&&$form['published']){$safe['correct']=$q['correct'];$safe['reference']=$q['reference']??'';}
        $questions[]=$safe;
    }
    $data=['token'=>$form['token'],'title'=>$form['title'],'description'=>$form['description'],'active'=>(bool)$form['active'],
        'published'=>(bool)$form['published'],'require_account'=>(bool)$form['require_account'],'questions'=>$questions,'submitted'=>(bool)$attempt];
    if($attempt){$data['attempt']=['name'=>$attempt['name'],'submitted_at'=>$attempt['submitted_at']];
        if($form['published'])$data['attempt']+=['points'=>(float)$attempt['points'],'max_points'=>(float)$attempt['max_points'],
            'percent'=>$attempt['max_points']>0?round($attempt['points']/$attempt['max_points']*100,2):null,'answers'=>json_decode($attempt['answers'],true),'manually_adjusted'=>!empty($attempt['manually_adjusted'])];}
    return $data;
}
function formAdjustedAttempt(array $form,array $attempt): array {
    if(!empty($form['assessment_id'])&&!empty($attempt['user_id'])){
        $manual=query('SELECT a.max_points,s.points FROM assessments a JOIN assessment_scores s ON s.assessment_id=a.id WHERE a.id=? AND a.source_edited=1 AND s.user_id=?',[$form['assessment_id'],$attempt['user_id']])->fetch();
        if($manual){$attempt['points']=$manual['points'];$attempt['max_points']=$manual['max_points'];$attempt['manually_adjusted']=true;}
    }
    return $attempt;
}
function formsHandle(string $action,array $input): void {
    global $db,$me;
    if(!in_array($action,['forms','form_create','form_get','form_submit','form_configure','form_results','form_link_attempt','form_telegram_create','form_telegram_command'],true))return;
    formsSchema();
    if(in_array($action,['form_get','form_submit'],true)){
        $token=$input['token']??$_GET['token']??'';
        if(!is_string($token)||!preg_match('/^[a-f0-9]{32}$/',$token))fail('Тест не найден.',404);
        if($action==='form_submit')$db->exec('BEGIN IMMEDIATE');
        $form=query('SELECT * FROM pulse_forms WHERE token=?',[$token])->fetch();if(!$form)fail('Тест не найден.',404);
        $attempt=formAttempt($form);
        if($action==='form_submit'&&!$attempt){
            if(!$form['active'])fail('Приём ответов закрыт.',409);
            if($form['require_account']&&!$me)fail('Войдите в аккаунт перед прохождением.',401);
            if((int)query('SELECT count(*) FROM form_attempts WHERE form_id=?',[$form['id']])->fetchColumn()>=20000)fail('Достигнут лимит ответов теста.');
            $answers=$input['answers']??null;if(!is_array($answers)||!array_is_list($answers))fail('Некорректный список ответов.');
            $name=$me?$me['name']:cleanText($input['name']??'',80);
            $attempt=formStoreAttempt($form,$me['id']??null,formGuestKey(),$name,$answers,'web');
        }
        $result=formPublic($form,$attempt);if($action==='form_submit')$db->exec('COMMIT');out($result);
    }
    hostOnly();
    if($action==='forms'){
        $rows=query('SELECT f.*,(SELECT count(*) FROM form_attempts a WHERE a.form_id=f.id) AS responses FROM pulse_forms f WHERE owner_id=? ORDER BY created_at DESC',[$me['id']])->fetchAll();
        foreach($rows as &$r){$r['question_count']=count(json_decode($r['quiz'],true)['questions']);unset($r['quiz']);}unset($r);
        out(['forms'=>$rows,'bot'=>getenv('TELEGRAM_BOT_USERNAME')?:null]);
    }
    if($action==='form_create'){
        $q=communityQuiz((string)($input['quiz_id']??''));$quiz=json_decode($q['questions'],true);
        $quiz=is_array($quiz)&&isset($quiz['questions'])?$quiz:['questions'=>$quiz];
        if(($quiz['mode']??'classic')==='bluff')fail('Для самостоятельного теста нужны вопросы с вариантами ответов.');
        foreach($quiz['questions'] as &$question){$question['points']??=1000;$question['type']??='quiz';$question['image']??=null;$question['multiple']=!empty($question['multiple'])||(is_array($question['correct']??null)&&count($question['correct'])>1);}unset($question);
        $title=cleanText($input['title']??$q['title'],100);$description=$input['description']??$q['description'];
        if(!is_string($description)||mb_strlen($description)>1000)fail('Описание: до 1000 символов.');
        $id=bin2hex(random_bytes(8));$token=bin2hex(random_bytes(16));
        query('INSERT INTO pulse_forms(id,token,owner_id,title,description,quiz,require_account,created_at) VALUES (?,?,?,?,?,?,?,?)',[$id,$token,$me['id'],$title,trim($description),json_encode($quiz,JSON_UNESCAPED_UNICODE),!empty($input['require_account'])?1:0,time()]);
        communityAudit('create_form',$id,['quiz'=>$q['id']]);out(['id'=>$id,'token'=>$token]);
    }
    $id=(string)($input['form']??$_GET['form']??'');$form=formOwned($id);
    if($action==='form_results'){
        require_once __DIR__.'/forms-bot.php';formsBotSchema();
        $attempts=query('SELECT a.id,a.name,a.points,a.max_points,a.submitted_at,a.user_id,a.source,u.name AS account_name FROM form_attempts a LEFT JOIN pulse_accounts u ON u.id=a.user_id WHERE a.form_id=? ORDER BY a.submitted_at DESC',[$id])->fetchAll();
        foreach($attempts as &$a){$a=formAdjustedAttempt($form,$a);$a['percent']=$a['max_points']>0?round($a['points']/$a['max_points']*100,2):null;}unset($a);
        $deliveries=query('SELECT id,kind,chat_title,position,state,error,revision FROM form_tg_deliveries WHERE form_id=? AND kind=\'group\' ORDER BY created_at DESC',[$id])->fetchAll();
        $quiz=json_decode($form['quiz'],true);unset($form['quiz']);out(['form'=>$form,'question_count'=>count($quiz['questions']),'attempts'=>$attempts,'deliveries'=>$deliveries,'bot'=>getenv('TELEGRAM_BOT_USERNAME')?:null]);
    }
    if(in_array($action,['form_telegram_create','form_telegram_command'],true)){require_once __DIR__.'/forms-bot.php';formsBotSchema();formsBotHandle($action,$input,$form);return;}
    $db->exec('BEGIN IMMEDIATE');$form=formOwned($id);
    if($action==='form_link_attempt'){
        communityStaff();$uid=(string)($input['user_id']??'');$u=query('SELECT * FROM pulse_accounts WHERE id=? AND active=1',[$uid])->fetch();if(!$u)fail('Аккаунт не найден.');
        $a=query('SELECT * FROM form_attempts WHERE id=? AND form_id=?',[$input['attempt']??'',$id])->fetch();if(!$a)fail('Ответ не найден.',404);
        if(query('SELECT id FROM form_attempts WHERE form_id=? AND user_id=? AND id<>?',[$id,$uid,$a['id']])->fetchColumn())fail('У этого аккаунта уже есть результат.',409);
        query('UPDATE form_attempts SET user_id=? WHERE id=?',[$uid,$a['id']]);formSyncAssessment($form);communityAudit('link_form_attempt',$a['id'],['user_id'=>$uid]);
    }else{
        if((int)($input['revision']??-1)!==(int)$form['revision'])fail('Настройки уже изменились. Обновите тест.',409);
        foreach(['active','published'] as $field)if(!isset($input[$field])||!is_bool($input[$field]))fail('Некорректные настройки теста.');
        query('UPDATE pulse_forms SET active=?,published=?,revision=revision+1 WHERE id=?',[$input['active']?1:0,$input['published']?1:0,$id]);
        $form=formOwned($id);formSyncAssessment($form);communityAudit('configure_form',$id,['active'=>$form['active'],'published'=>$form['published']]);
    }
    $db->exec('COMMIT');out(['ok'=>true]);
}
