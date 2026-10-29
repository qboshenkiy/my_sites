<?php
declare(strict_types=1);
function telegramReplyKeyboard(bool $admin=false): array {$rows=[
    [['text'=>'📖 Отметить чтение'],['text'=>'📊 Мой прогресс']],
    [['text'=>'📚 План недели'],['text'=>'🗓 Мои недели']],
    [['text'=>'🔁 Круги чтения'],['text'=>'📱 Марафон']],
    [['text'=>'🧭 Как догнать?']],
    [['text'=>'❓ Помощь'],['text'=>'Отмена']]
];if($admin){array_unshift($rows,[['text'=>'👥 Участники'],['text'=>'📋 Общий отчёт']]);$rows[]=[['text'=>'🧾 Журнал'],['text'=>'📣 Отправить в группу']];}return ['keyboard'=>$rows,'resize_keyboard'=>true,'is_persistent'=>true,'input_field_placeholder'=>'Выберите действие или напишите «прочитал 5»'];}
function telegramBookLines(array $books): array {return array_map(fn($b)=>'• '.$b['title'].': главы '.$b['chapter_from'].'–'.$b['chapter_to'],$books);}
function telegramReaderHeader(array $reader,array $c): string {return $reader['name'].' · '.($c['current']<1?'до старта':($c['current']>22?'марафон завершён':'неделя '.$c['current'].'/22'));}
function telegramMenu(string $text,bool $callback,?array $reader,string $telegramId,callable $reply): bool {
    $actions=['🧭 Как догнать?'=>'catchup','Как догнать?'=>'catchup','📖 Отметить чтение'=>'read','📊 Мой прогресс'=>'progress','📚 План недели'=>'plan','🗓 Мои недели'=>'weeks','🔁 Круги чтения'=>'rounds','🌐 Открыть сайт'=>'site','📱 Марафон'=>'site','/app'=>'site','❓ Помощь'=>'help','Отмена'=>'cancel','🏠 Меню'=>'home','/start'=>'home','/menu'=>'home','/help'=>'help','/cancel'=>'cancel'];
    $action=$callback&&str_starts_with($text,'menu:')?substr($text,5):($actions[preg_replace('~^(/(?:start|menu|help|cancel|app))@\w+$~i','$1',trim($text))]??null);
    if($action==='site'){$base=rtrim(getenv('APP_URL')?:'','/');$reply($base?'Планы, исправление глав и подробная история доступны на сайте.':'Администратор ещё не указал адрес сайта.',telegramAppButtons());return true;}
    if($action==='help'){$reply("❓ Как отмечать чтение\n1. Нажмите «📖 Отметить чтение».\n2. Введите число новых глав или выберите кнопку.\n3. Проверьте распределение и подтвердите.\n\nСначала закрываются самые ранние непрочитанные недели, затем текущая. Исправить главы можно на сайте.\n\n🔁 Круг — повтор того же недельного плана. Завершите план и начните следующий круг: книги и сроки недели остаются прежними, результаты каждого прохода сохраняются. Прогресс показывает текущий круг текущей недели.");return true;}
    $repeatCallback=$callback&&($text==='repeat:new'||preg_match('/^w_([yn])_([a-f0-9]{32})$/',$text,$match));
    if($callback&&(str_starts_with($text,'circle:')||str_starts_with($text,'c_'))){$reply('Круги теперь относятся к отдельной неделе. Откройте «🔁 Круги чтения».');return true;}
    if($action===null&&!$repeatCallback)return false;
    if(!$reader){$reply('Сначала получите персональное приглашение и привяжите Telegram. После этого кнопки откроют ваш план и прогресс.');return true;}
    $id=$reader['id'];$c=calendar($id);$s=stats($id);$w=$s['pace'];$header=telegramReaderHeader($reader,$c);
    if($action==='catchup'){$reply(telegramCatchupText($c,$s['reports']),[[['text'=>'📖 Отметить чтение','callback_data'=>'menu:read'],['text'=>'📚 План недели','callback_data'=>'menu:plan']]]);return true;}
    if($repeatCallback){
        if(!$w){$reply('Новый круг доступен только в текущей неделе марафона.');return true;}
        $binding=$reader['session_epoch'].':'.$w['week'].':'.$w['cycle'].':'.$c['today'];
        if($text==='repeat:new'){
            if(!$w['completed']){$reply('Сначала завершите текущий круг: осталось '.$w['remaining'].' глав.');return true;}
            $token=bin2hex(random_bytes(16));sql("DELETE FROM requests WHERE user_id=? AND kind='weekly_repeat'",[$id]);
            sql('INSERT INTO requests(token_hash,kind,user_id,session_hash,expires_at) VALUES (?,?,?,?,?)',[hash('sha256',$token),'weekly_repeat',$id,$binding,time()+900]);
            $reply('Начать круг '.$w['nextCycle'].' недели '.$w['week'].'?'."\n".'Тот же план: '.$w['goal'].' глав, срок до '.$w['end'].'. Предыдущие '.$w['chapters'].' глав сохранятся в истории. Прогресс нового круга начнётся с нуля.',[[['text'=>'✓ Начать повтор','callback_data'=>'w_y_'.$token],['text'=>'Отмена','callback_data'=>'w_n_'.$token]]]);return true;
        }
        $r=sql("SELECT * FROM requests WHERE token_hash=? AND kind='weekly_repeat'",[hash('sha256',$match[2])])->fetch();
        if(!$r||$r['consumed']||$r['expires_at']<time()||$r['user_id']!==$id||$r['session_hash']!==$binding){$reply('Подтверждение истекло или круг изменился. Откройте круги заново.');return true;}
        sql('UPDATE requests SET consumed=1 WHERE token_hash=?',[$r['token_hash']]);
        if($match[1]==='n')$reply('Отменено. Прочитанные главы сохранены.');
        else {try{$next=startWeeklyRepeat($id,$id,$w['week'],$w['cycle']);$reply('🔁 Неделя '.$next['week'].' · круг '.$next['cycle'].' начат. План: '.$next['goal'].' глав. Срок прежний: '.$next['end'].'.',[[['text'=>'📖 Отметить чтение','callback_data'=>'menu:read'],['text'=>'📚 План','callback_data'=>'menu:plan']]]);}catch(DomainException $e){$reply($e->getMessage());}}return true;
    }
    if($action==='cancel'){sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$id]);sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$id]);sql("DELETE FROM requests WHERE user_id=? AND kind IN ('round','weekly_repeat')",[$id]);$reply('Отменено. Неподтверждённые главы не зачтены.');return true;}
    if($action==='read'){
        $eligible=array_filter($s['reports'],fn($v)=>$v['week']<=min(22,$c['current'])&&$v['remaining']>0&&($v['week']===$c['current']||$v['completedCycles']===0));$left=array_sum(array_column($eligible,'remaining'));
        if(!$left){$reply($w?'✅ Недельный план прочитан. Можно повторить его через «🔁 Круги чтения».':'Сейчас нет открытого плана для отметки.',[[['text'=>'🔁 Круги чтения','callback_data'=>'menu:rounds']]]);return true;}
        sql('INSERT INTO telegram_menu_states VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET telegram_id=excluded.telegram_id,session_epoch=excluded.session_epoch,round_number=excluded.round_number,expires_at=excluded.expires_at',[$id,$telegramId,(int)$reader['session_epoch'],$c['round'],time()+900]);
        $buttons=[];foreach([1,5,10] as $n)if($n<=$left)$buttons[]=['text'=>'+'.$n.' глав','callback_data'=>'amount:'.$n];
        $reply('📖 '.$header."\n".'Сколько новых глав прочитали? Введите число от 1 до '.$left.'.'."\n".implode("\n",array_map(fn($v)=>'Неделя '.$v['week'].' · круг '.$v['cycle'].': осталось '.$v['remaining'].' глав.',$eligible))."\nДалее — проверка и подтверждение.",[$buttons,[['text'=>'Весь остаток: '.$left,'callback_data'=>'amount:'.$left],['text'=>'Отмена','callback_data'=>'menu:cancel']]]);return true;
    }
    if($action==='rounds'){
        if(!$w){$reply('Повторы доступны во время текущей недели марафона.');return true;}
        $lines=['🔁 '.$header,'План: '.$w['goal'].' глав. Текущий круг: '.$w['cycle'].'.','Завершено кругов: '.$w['completedCycles'].'. Всего за неделю: '.$w['totalChapters'].' глав.'];
        foreach($w['repeats'] as $r)$lines[]='✓ Круг '.$r['cycle'].': '.$r['chapters'].' глав за '.$r['days'].' дн. · '.$r['completedOn'];
        $lines[]='Сейчас: '.$w['chapters'].'/'.$w['goal'].' глав. Срок: '.$w['end'].'.';
        $reply(implode("\n",$lines),$w['completed']?[[['text'=>'Начать круг '.$w['nextCycle'],'callback_data'=>'repeat:new']]]:[[['text'=>'📖 Продолжить чтение','callback_data'=>'menu:read']]]);return true;
    }
    if($action==='weeks'){$names=['upcoming'=>'⏳','in_progress'=>'📖','overdue'=>'⚠️','completed'=>'✅','completed_late'=>'✅ С опозданием'];$weeks=array_filter($s['reports'],fn($v)=>$reader['role']==='admin'||$v['week']<=$c['current']);$reply('🗓 '.$header."\n".($weeks?implode("\n",array_map(fn($v)=>$names[$v['status']].' Неделя '.$v['week'].': '.$v['chapters'].'/'.$v['goal'].' глав · круг '.$v['cycle'].' · завершено кругов '.$v['completedCycles'],$weeks)):'Недели откроются после старта марафона.'),[[['text'=>'📚 План недели','callback_data'=>'menu:plan']]]);return true;}
    if($action==='plan'){
        if(!$w){$reply($c['current']<1?'Марафон ещё не начался. План откроется в день старта.':'Марафон завершён. Прошедшие планы доступны в «Мои недели».');return true;}
        $reply('📚 '.$header.' · круг '.$w['cycle']."\n".$w['start'].' — '.$w['end']."\n".implode("\n",telegramBookLines($w['books']))."\n".'Прочитано '.$w['chapters'].'/'.$w['goal'].' глав. Осталось '.$w['remaining'].'.'.($w['remaining']&&$w['daysLeft']?' Нужно '.$w['perDay'].' глав/день, осталось '.$w['daysLeft'].' дн.':''),[[['text'=>'📖 Отметить чтение','callback_data'=>'menu:read']]]);return true;
    }
    $bar=str_repeat('■',min(10,(int)floor($s['progress']/10))).str_repeat('□',max(0,10-(int)floor($s['progress']/10)));
    $reply('📊 '.$header."\n".($w?'Текущая неделя · круг '.$w['cycle']."\n".$bar.' '.$s['progress'].'%'."\n".$w['chapters'].'/'.$w['goal'].' глав. '.($w['remaining']?'Осталось '.$w['remaining'].', темп '.$w['perDay'].' глав/день.':'✅ Круг завершён за '.$w['days'].' дн.')."\n".'Завершено кругов недели: '.$w['completedCycles'].'. Всего за неделю: '.$w['totalChapters'].' глав.':'Сейчас нет текущей недели.')."\n".'Всего за марафон: '.$s['totalChapters'].' глав. Недель выполнено: '.$s['goalWeeks'].'/22. Просрочено: '.$s['overdueWeeks'].'.');return true;
}
