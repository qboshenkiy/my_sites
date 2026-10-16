<?php
declare(strict_types=1);

function telegramAuditPage(int $cursor,string $direction,?string $target,int $week,callable $reply): void {
    $data=auditEvents($cursor,$direction,$target,$week,5);
    $name=$target?sql('SELECT name FROM users WHERE id=?',[$target])->fetchColumn():null;
    $lines=['🧾 Журнал изменений',($target?'Участник: '.($name?:'Архивный аккаунт'):'Все участники').' · '.($week?'неделя '.$week:'все недели'),'Время: '.$data['timezone']];$buttons=[];
    foreach($data['events'] as $e){
        $m=$e['metadata'];$lines[]="\n#".$e['id'].' · '.date('d.m.Y H:i:s',(int)$e['created_at']).' · '.(($m['source']??'')==='telegram'?'Telegram':(($m['source']??'')==='site'?'Сайт':(($m['source']??'')==='system'?'Система':'Старый журнал')));
        $lines[]=mb_substr($e['actor']?:'Система',0,60).($e['target']?' → '.mb_substr($e['target'],0,60):'');
        $lines[]=mb_substr($e['details'],0,180);
        if(isset($m['week']))$lines[]='Неделя '.$m['week'].(isset($m['cycle'])?' · круг '.$m['cycle']:'');
        foreach(array_slice(auditChangeLines($m),0,3) as $line)$lines[]=mb_substr($line,0,120);
        $buttons[]=[['text'=>'Подробнее #'.$e['id'],'callback_data'=>'lg:e:'.$e['id'].':'.($target??'-').':'.$week]];
    }
    if(!$data['events'])$lines[]='Записей по этому фильтру пока нет.';
    $nav=[];foreach(['newer'=>['n','← Новее'],'older'=>['b','Ранее →']] as $key=>[$dir,$label])if($data[$key]!==null)$nav[]=['text'=>$label,'callback_data'=>'lg:'.$dir.':'.$data[$key].':'.($target??'-').':'.$week];if($nav)$buttons[]=$nav;
    $buttons[]=[['text'=>'↻ Последние','callback_data'=>'lg:b:0:'.($target??'-').':'.$week],['text'=>'Все участники','callback_data'=>'lg:b:0:-:'.$week]];
    $weeks=[];if($week>1)$weeks[]=['text'=>'← Неделя '.($week-1),'callback_data'=>'lg:b:0:'.($target??'-').':'.($week-1)];if($week>0&&$week<22)$weeks[]=['text'=>'Неделя '.($week+1).' →','callback_data'=>'lg:b:0:'.($target??'-').':'.($week+1)];if($weeks)$buttons[]=$weeks;
    $buttons[]=[['text'=>$week?'Все недели':'Текущая неделя','callback_data'=>'lg:b:0:'.($target??'-').':'.($week?0:max(1,min(22,calendar()['current'])))] ,['text'=>'👥 Выбрать участника','callback_data'=>'ad:l:0:'.max(1,min(22,$week?:calendar()['current']))]];
    $reply(implode("\n",$lines),$buttons);
}
function telegramAuditMenu(string $text,bool $callback,?array $actor,callable $reply): bool {
    $command=in_array(preg_replace('~^(/logs)@\w+$~i','$1',trim($text)),['🧾 Журнал','/logs'],true);
    if(!$command&&!($callback&&str_starts_with($text,'lg:')))return false;
    if(!$actor||$actor['role']!=='admin'){$reply('Журнал доступен только привязанному администратору.');return true;}
    sql('DELETE FROM telegram_admin_states WHERE user_id=?',[$actor['id']]);sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$actor['id']]);sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$actor['id']]);
    if($command){telegramAuditPage(0,'b',null,0,$reply);return true;}
    if(!preg_match('/^lg:([bne]):(\d{1,18}):([a-zA-Z0-9_-]{1,40}):(\d{1,2})$/',$text,$match)||(int)$match[4]>22){$reply('Кнопка устарела. Откройте «🧾 Журнал» заново.');return true;}
    $id=(int)$match[2];$target=$match[3]==='-'?null:$match[3];$week=(int)$match[4];
    if($match[1]!=='e'){telegramAuditPage($id,$match[1],$target,$week,$reply);return true;}
    $e=sql('SELECT a.*,COALESCE(a.actor_name,u.name) AS actor,COALESCE(a.target_name,t.name) AS target FROM audit a LEFT JOIN users u ON u.id=a.actor_id LEFT JOIN users t ON t.id=a.target_id WHERE a.id=?',[$id])->fetch();
    if(!$e){$reply('Запись не найдена.');return true;}
    $m=json_decode($e['metadata'],true,512,JSON_THROW_ON_ERROR);
    $lines=['🧾 Запись #'.$id,date('d.m.Y H:i:s T',(int)$e['created_at']),'Кто: '.($e['actor']?:'Система'),'Участник: '.($e['target']?:'Общие настройки'),'Действие: '.$e['details'],'Источник: '.($m['source']??'старый журнал')];
    if(isset($m['week']))$lines[]='Неделя '.$m['week'].(isset($m['cycle'])?' · круг '.$m['cycle']:'');
    $changes=auditChangeLines($m);$lines[]=$changes?"\nБыло → стало:\n".implode("\n",$changes):(isset($m['before'],$m['after'])?'Отслеживаемые поля не изменились.':'Подробные изменения полей для этой записи не сохранены.');
    if(isset($m['affected_cycle']))$lines[]='Удалённый / восстановленный круг: '.$m['affected_cycle'];
    if(!empty($m['password_changed']))$lines[]='Пароль изменён (значение не сохраняется).';
    if(isset($m['request_id']))$lines[]='Операция: '.$m['request_id'];
    $reply(implode("\n",$lines),[[['text'=>'← К журналу','callback_data'=>'lg:b:0:'.($target??'-').':'.$week]]]);return true;
}
