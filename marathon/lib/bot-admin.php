<?php
declare(strict_types=1);
// Called within the same transaction and private-chat checks as all bot updates.
function telegramAdminState(array $actor,string $telegramId,array $payload): void {
    sql('INSERT INTO telegram_admin_states VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET telegram_id=excluded.telegram_id,session_epoch=excluded.session_epoch,payload=excluded.payload,expires_at=excluded.expires_at',[$actor['id'],$telegramId,(int)$actor['session_epoch'],json_encode($payload,JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR),time()+900]);
}
function telegramAdminWeek(string $id,int $week): array {
    $u=user($id);if(!$u)throw new DomainException('Участник удалён или не найден.');
    if($week<1||$week>22)throw new DomainException('Неделя должна быть от 1 до 22.');
    return weekResults($id)[$week-1];
}
function telegramAdminFingerprint(string $id,int $week): string {
    $u=user($id);return hash('sha256',json_encode(['epoch'=>$u['session_epoch']??null,'active'=>$u['active']??null,'round'=>calendar($id)['round'],'today'=>calendar($id)['today'],'result'=>telegramAdminWeek($id,$week)],JSON_UNESCAPED_UNICODE|JSON_THROW_ON_ERROR));
}
function telegramAdminList(int $page,int $week,bool $report,callable $reply): void {
    $people=staff();usort($people,fn($a,$b)=>strcmp($a['name'],$b['name']));$pages=max(1,(int)ceil(count($people)/8));$page=max(0,min($page,$pages-1));
    $lines=[($report?'📋 Общий отчёт':'👥 Участники').' · неделя '.$week,'Страница '.($page+1).' из '.$pages.' · Всего: '.count($people)];
    if($report){$complete=count(array_filter($people,fn($u)=>$u['weekly'][$week-1]['completedCycles']>0));$chapters=array_sum(array_map(fn($u)=>$u['weekly'][$week-1]['totalChapters'],$people));$lines[]='Выполнили хотя бы один круг: '.$complete.'/'.count($people).'. Всего с повторами: '.$chapters.' глав. За весь марафон: '.array_sum(array_column($people,'chapters')).' глав.';}
    $buttons=[];foreach(array_slice($people,$page*8,8) as $u){$w=$u['weekly'][$week-1];$status=$w['completed']?'✅':($w['completedCycles']>0?'🔁':($w['status']==='overdue'?'⚠️':'📖'));
        $lines[]=$status.' '.$u['name'].(!$u['active']?' [отключён]':'').' — '.$w['chapters'].'/'.$w['goal'].' глав · '.$w['days'].' дн. · круг '.$w['cycle'].' · завершено '.$w['completedCycles'].($report?' · за марафон '.$u['chapters'].' глав, недель выполнено '.$u['completed']:'');
        $buttons[]=[['text'=>mb_substr($u['name'],0,45),'callback_data'=>'ad:u:'.$u['id'].':'.$week]];
    }
    $kind=$report?'r':'l';$nav=[];if($page>0)$nav[]=['text'=>'← Назад','callback_data'=>'ad:'.$kind.':'.($page-1).':'.$week];if($page<$pages-1)$nav[]=['text'=>'Далее →','callback_data'=>'ad:'.$kind.':'.($page+1).':'.$week];if($nav)$buttons[]=$nav;
    $weeks=[];if($week>1)$weeks[]=['text'=>'← Неделя '.($week-1),'callback_data'=>'ad:'.$kind.':0:'.($week-1)];if($week<22)$weeks[]=['text'=>'Неделя '.($week+1).' →','callback_data'=>'ad:'.$kind.':0:'.($week+1)];if($weeks)$buttons[]=$weeks;
    $buttons[]=[['text'=>$report?'👥 Участники':'📋 Общий отчёт','callback_data'=>'ad:'.($report?'l':'r').':0:'.$week]];
    $reply(implode("\n",$lines),$buttons);
}
function telegramAdminCard(string $id,int $week,callable $reply): void {
    $u=user($id);$w=telegramAdminWeek($id,$week);$status=$w['completed']?'Выполнен':($w['status']==='overdue'?'Просрочен':($w['status']==='upcoming'?'Неделя ещё не началась':'В процессе'));
    $lines=['👤 '.$u['name'].(!$u['active']?' · аккаунт отключён':''),'Неделя '.$week.' · '.$w['start'].' — '.$w['end'],'Круг '.$w['cycle'].' · '.$status,$w['chapters'].'/'.$w['goal'].' глав · '.$w['days'].' дн.','Всего за неделю: '.$w['totalChapters'].' глав. Завершено кругов: '.$w['completedCycles'].'.',planBookText($w['books'])];
    $buttons=[];if($u['active']&&$w['editable'])$buttons[]=[['text'=>'✏️ Изменить главы и дни','callback_data'=>'ad:e:'.$id.':'.$week]];
    if($u['active']&&$w['canComplete']&&!$w['completed'])$buttons[]=[['text'=>'✅ Отметить план прочитанным','callback_data'=>'ad:c:'.$id.':'.$week]];
    if(!$w['editable']&&$w['canComplete'])$lines[]='Неделя закрыта для исправлений. Администратор может открыть её на сайте. Поздняя отметка выполнения доступна отдельно.';
    $nav=[];if($week>1)$nav[]=['text'=>'← Неделя '.($week-1),'callback_data'=>'ad:u:'.$id.':'.($week-1)];if($week<22)$nav[]=['text'=>'Неделя '.($week+1).' →','callback_data'=>'ad:u:'.$id.':'.($week+1)];if($nav)$buttons[]=$nav;
    $buttons[]=[['text'=>'🧾 История участника','callback_data'=>'lg:b:0:'.$id.':0']];
    $buttons[]=[['text'=>'👥 К списку','callback_data'=>'ad:l:0:'.$week],['text'=>'📋 Отчёт','callback_data'=>'ad:r:0:'.$week]];$reply(implode("\n",array_filter($lines,fn($s)=>$s!=='')),$buttons);
}
function telegramAdminPreview(array $actor,string $telegramId,array $p,int $chapters,?int $days,callable $reply): void {
    $u=user($p['target']);$w=telegramAdminWeek($p['target'],$p['week']);
    if(!$u['active'])throw new DomainException('Аккаунт участника отключён.');
    if($p['fingerprint']!==telegramAdminFingerprint($p['target'],$p['week']))throw new DomainException('Результат или план изменился. Выберите участника заново.');
    if($chapters<0||$chapters>$w['goal'])throw new DomainException('Укажите от 0 до '.$w['goal'].' глав.');
    if($days!==null&&($days<($chapters?1:0)||$days>3660))throw new DomainException('Дни: от '.($chapters?1:0).' до 3660.');
    if($p['mode']==='edit')assertWeekEditable($p['week'],$p['target']);elseif(!$w['canComplete'])throw new DomainException('Неделя ещё не началась.');
    $token=bin2hex(random_bytes(16));$p=array_merge($p,['stage'=>'confirm','chapters'=>$chapters,'days'=>$days,'token_hash'=>hash('sha256',$token)]);telegramAdminState($actor,$telegramId,$p);
    $reply('Сохранить результат?'."\n".$u['name'].' · неделя '.$p['week'].' · круг '.$w['cycle']."\n".'Было: '.$w['chapters'].'/'.$w['goal'].' глав, '.$w['days'].' дн.'."\n".'Станет: '.$chapters.'/'.$w['goal'].' глав, '.($days===null?'дни автоматически':$days.' дн.').'.'."\n".'Это общий итог текущего круга, а не прибавление. Ежедневные записи сохранятся. Пока ничего не изменено.',[[['text'=>'✓ Сохранить','callback_data'=>'ad:y:'.$token],['text'=>'Отмена','callback_data'=>'ad:n:'.$token]]]);
}
function telegramAdminMenu(string $text,bool $callback,?array $actor,string $telegramId,callable $reply): bool {
    $command=in_array($text,['👥 Участники','📋 Общий отчёт','/admin'],true);$adminCallback=$callback&&str_starts_with($text,'ad:');
    $row=$actor?sql('SELECT * FROM telegram_admin_states WHERE user_id=?',[$actor['id']])->fetch():false;
    if(!$command&&!$adminCallback&&!$row)return false;
    if(!$actor||$actor['role']!=='admin'){
        if($row)sql('DELETE FROM telegram_admin_states WHERE user_id=?',[$actor['id']]);
        if($command||$adminCallback){$reply('Этот раздел доступен только привязанному администратору.');return true;}return false;
    }
    if($command||$adminCallback){sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$actor['id']]);sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$actor['id']]);}
    $valid=$row&&$row['telegram_id']===$telegramId&&(int)$row['session_epoch']===(int)$actor['session_epoch']&&$row['expires_at']>=time();
    $state=$valid?json_decode($row['payload'],true,512,JSON_THROW_ON_ERROR):null;
    try {
        if($command){sql('DELETE FROM telegram_admin_states WHERE user_id=?',[$actor['id']]);sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$actor['id']]);telegramAdminList(0,max(1,min(22,calendar()['current'])),$text==='📋 Общий отчёт',$reply);return true;}
        if($adminCallback&&preg_match('/^ad:([yn]):([a-f0-9]{32})$/',$text,$m)){
            if(!$state||$state['stage']!=='confirm'||!hash_equals($state['token_hash'],hash('sha256',$m[2]))){$reply('Подтверждение истекло или уже использовано. Откройте участника заново.');return true;}
            sql('DELETE FROM telegram_admin_states WHERE user_id=?',[$actor['id']]);
            if($m[1]==='n'){$reply('Отменено. Результаты участника не изменились.');return true;}
            $u=user($state['target']);if(!$u||!$u['active']||telegramAdminFingerprint($state['target'],$state['week'])!==$state['fingerprint'])throw new DomainException('Аккаунт, круг, план или результат изменился. Ничего не сохранено. Выберите участника заново.');
            $w=telegramAdminWeek($state['target'],$state['week']);
            if($state['mode']==='complete')$saved=completeWeek($u['id'],$actor['id'],$state['week'],null);
            else $saved=saveWeeklyResult($u['id'],$actor['id'],$state['week'],$state['chapters'],$state['days'],$w['title'],$w['note']);
            $reply('✅ Сохранено: '.$u['name'].' · неделя '.$state['week'].' · круг '.$saved['cycle']."\n".$saved['chapters'].'/'.$saved['goal'].' глав · '.$saved['days'].' дн.',[[['text'=>'👤 Участник','callback_data'=>'ad:u:'.$u['id'].':'.$state['week']],['text'=>'📋 Общий отчёт','callback_data'=>'ad:r:0:'.$state['week']]]]);return true;
        }
        if($adminCallback){
            sql('DELETE FROM telegram_admin_states WHERE user_id=?',[$actor['id']]);
            if(preg_match('/^ad:([lr]):(\d{1,6}):(\d{1,2})$/',$text,$m)&&((int)$m[3]>=1&&(int)$m[3]<=22)){telegramAdminList((int)$m[2],(int)$m[3],$m[1]==='r',$reply);return true;}
            if(preg_match('/^ad:([uec]):([a-zA-Z0-9_-]{1,40}):(\d{1,2})$/',$text,$m)){
                $id=$m[2];$week=(int)$m[3];$w=telegramAdminWeek($id,$week);if($m[1]==='u'){telegramAdminCard($id,$week,$reply);return true;}
                $u=user($id);if(!$u['active'])throw new DomainException('Аккаунт отключён.');
                $p=['stage'=>'input','mode'=>$m[1]==='e'?'edit':'complete','target'=>$id,'week'=>$week,'fingerprint'=>telegramAdminFingerprint($id,$week)];
                if($m[1]==='c'){telegramAdminPreview($actor,$telegramId,$p,$w['goal'],null,$reply);return true;}
                assertWeekEditable($week,$id);telegramAdminState($actor,$telegramId,$p);sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$actor['id']]);
                $reply('✏️ '.$u['name'].' · неделя '.$week.' · круг '.$w['cycle']."\n".'Сейчас: '.$w['chapters'].'/'.$w['goal'].' глав, '.$w['days'].' дн.'."\n".'Введите общий итог глав от 0 до '.$w['goal'].'. Например «5». Для ручных дней — «5 2» (5 глав за 2 дня). Одно число включает автоматический расчёт дней. Следом появится подтверждение.',[[['text'=>'Отмена','callback_data'=>'ad:u:'.$id.':'.$week]]]);return true;
            }
            $reply('Кнопка недоступна. Откройте «👥 Участники» заново.');return true;
        }
        if(in_array($text,['Отмена','/cancel','/start','/menu','🏠 Меню'],true)||str_starts_with($text,'📖')||str_starts_with($text,'📊')||str_starts_with($text,'📚')||str_starts_with($text,'🗓')||str_starts_with($text,'🔁')||str_starts_with($text,'🌐')||str_starts_with($text,'📱')||$text==='/app'||str_starts_with($text,'❓')||$callback){sql('DELETE FROM telegram_admin_states WHERE user_id=?',[$actor['id']]);return false;}
        if(!$state){sql('DELETE FROM telegram_admin_states WHERE user_id=?',[$actor['id']]);$reply('Ввод администратора истёк. Выберите участника заново.');return true;}
        if($state['stage']!=='input'){$reply('Проверьте результат и нажмите «Сохранить» или «Отмена».');return true;}
        if(!preg_match('/^(\d{1,6})(?:\s+(\d{1,4}))?$/',trim($text),$m)){$reply('Введите общий итог: «5» или «5 2» (главы и дни). Для выхода нажмите «Отмена».');return true;}
        telegramAdminPreview($actor,$telegramId,$state,(int)$m[1],isset($m[2])?(int)$m[2]:null,$reply);return true;
    }catch(DomainException $e){$reply($e->getMessage());return true;}
}
