<?php
declare(strict_types=1);

// Persist only selected business fields: never credentials, cookies or Telegram tokens.
function auditWeekSnapshot(string $id,int $week): array {
    $w=weekResults($id)[$week-1];
    return array_intersect_key($w,array_flip(['week','cycle','chapters','goal','days','daysManual','completed','completedOn','status','title','note','books','totalChapters','completedCycles']));
}
function auditUserSnapshot(array $u): array {
    return array_merge(array_intersect_key($u,array_flip(['name','role','active','login','deleted_at'])),['telegramLinked'=>!empty($u['telegram_id'])]);
}
function audit(string $actor,string $event,?string $target,string $details,array $context=[]): void {
    $transport=$GLOBALS['audit_transport']??['source'=>'system','request_id'=>bin2hex(random_bytes(8))];
    $a=sql('SELECT name,role FROM users WHERE id=?',[$actor])->fetch();
    $t=$target?sql('SELECT name FROM users WHERE id=?',[$target])->fetch():false;
    $meta=array_merge($transport,['actor_role'=>$a['role']??null],$context);
    sql('INSERT INTO audit(actor_id,event,target_id,details,created_at,metadata,actor_name,target_name) VALUES (?,?,?,?,?,?,?,?)',[$actor,$event,$target,$details,time(),json_encode($meta,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),$a['name']??null,$t['name']??null]);
}
function auditWeekChange(string $actor,string $event,string $id,int $week,string $details,array $before,array $extra=[]): void {
    $after=auditWeekSnapshot($id,$week);
    audit($actor,$event,$id,$details,array_merge($extra,['week'=>$week,'round'=>calendar($id)['round'],'cycle'=>$after['cycle'],'before'=>$before,'after'=>$after]));
}
function auditEvents(int $cursor=0,string $direction='b',?string $target=null,int $week=0,int $limit=20): array {
    $limit=max(1,min(50,$limit));$cursor=max(0,$cursor);
    $where=[];$args=[];
    if($target!==null){$where[]='a.target_id=?';$args[]=$target;}
    if($week){$where[]="json_extract(a.metadata,'$.week')=CAST(? AS INTEGER)";$args[]=$week;}
    $base=$where;$baseArgs=$args;
    if($cursor){$where[]='a.id'.($direction==='n'?'>':'<').'?';$args[]=$cursor;}
    $rows=sql('SELECT a.*,COALESCE(a.actor_name,u.name) AS actor,COALESCE(a.target_name,t.name) AS target FROM audit a LEFT JOIN users u ON u.id=a.actor_id LEFT JOIN users t ON t.id=a.target_id'.($where?' WHERE '.implode(' AND ',$where):'').' ORDER BY a.id '.($cursor&&$direction==='n'?'ASC':'DESC').' LIMIT '.$limit,$args)->fetchAll();
    if($cursor&&$direction==='n')$rows=array_reverse($rows);
    foreach($rows as &$row){$row['metadata']=json_decode($row['metadata'],true,512,JSON_THROW_ON_ERROR);$row['changes']=auditChangeLines($row['metadata']);}unset($row);
    $first=$rows?(int)$rows[0]['id']:0;$last=$rows?(int)end($rows)['id']:0;
    $exists=function(string $op,int $id)use($base,$baseArgs):bool {return $id>0&&(bool)sql('SELECT 1 FROM audit a WHERE '.implode(' AND ',array_merge($base,['a.id'.$op.'?'])).' LIMIT 1',array_merge($baseArgs,[$id]))->fetchColumn();};
    return ['events'=>$rows,'newer'=>$exists('>',$first)?$first:null,'older'=>$exists('<',$last)?$last:null,'timezone'=>date_default_timezone_get()];
}
function auditChangeLines(array $meta): array {
    $labels=['chapters'=>'Главы','goal'=>'План глав','days'=>'Дни','daysManual'=>'Дни вручную','completed'=>'План выполнен','completedOn'=>'Дата завершения','status'=>'Статус','title'=>'Книга / название','note'=>'Комментарий','cycle'=>'Круг','totalChapters'=>'Всего глав с повторами','completedCycles'=>'Завершено кругов','books'=>'Книги плана','name'=>'Имя','role'=>'Роль','active'=>'Активен','login'=>'Логин','deleted_at'=>'Удалён','telegramLinked'=>'Telegram привязан','reopened'=>'Неделя открыта для исправлений','round'=>'Проход марафона'];
    $format=static function($v,string $key):string {
        if($v===null)return $key==='daysManual'?'автоматически':'не задано';
        if(is_bool($v)||in_array($key,['active','telegramLinked'],true))return $v?'да':'нет';
        if(is_array($v))return planBookText($v);
        if($key==='status')return ['upcoming'=>'не началась','in_progress'=>'в процессе','overdue'=>'просрочено','completed'=>'выполнено','completed_late'=>'выполнено с опозданием'][$v]??(string)$v;
        if($key==='role')return ['admin'=>'администратор','moderator'=>'модератор','participant'=>'участник'][$v]??(string)$v;
        if($key==='deleted_at')return date('d.m.Y H:i:s',(int)$v);
        return (string)$v;
    };
    $lines=[];$before=$meta['before']??[];$after=$meta['after']??[];
    foreach($labels as $key=>$label)if((array_key_exists($key,$before)||array_key_exists($key,$after))&&($before[$key]??null)!==($after[$key]??null))$lines[]=$label.': '.$format($before[$key]??null,$key).' → '.$format($after[$key]??null,$key);
    return $lines;
}
