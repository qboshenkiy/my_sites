<?php
declare(strict_types=1);
function telegramReplyKeyboard(): array {return ['keyboard'=>[
    [['text'=>'📖 Отметить чтение'],['text'=>'📊 Мой прогресс']],
    [['text'=>'📚 План недели'],['text'=>'🗓 Мои недели']],
    [['text'=>'🔁 Круги чтения'],['text'=>'🌐 Открыть сайт']],
    [['text'=>'❓ Помощь'],['text'=>'Отмена']]
],'resize_keyboard'=>true,'is_persistent'=>true,'input_field_placeholder'=>'Выберите действие или напишите «прочитал 5»'];}
function telegramBookLines(array $books): array {return array_map(fn($b)=>'• '.$b['title'].': главы '.$b['chapter_from'].'–'.$b['chapter_to'],$books);}
function telegramReaderHeader(array $reader,array $c): string {return $reader['name'].' · Круг '.$c['round'].' · '.($c['current']<1?'до старта':($c['current']>22?'срок завершён':'неделя '.$c['current'].'/22'));}
function telegramMenu(string $text,bool $callback,?array $reader,string $telegramId,callable $reply): bool {
    $actions=['📖 Отметить чтение'=>'read','📊 Мой прогресс'=>'progress','📚 План недели'=>'plan','🗓 Мои недели'=>'weeks','🔁 Круги чтения'=>'rounds','🌐 Открыть сайт'=>'site','❓ Помощь'=>'help','Отмена'=>'cancel','🏠 Меню'=>'home','/start'=>'home','/menu'=>'home','/help'=>'help','/cancel'=>'cancel'];
    $action=$callback&&str_starts_with($text,'menu:')?substr($text,5):($actions[preg_replace('~^(/(?:start|menu|help|cancel))@\w+$~i','$1',trim($text))]??null);
    if($callback&&preg_match('/^circle:(\d+)$/',$text,$m)){
        if(!$reader){$reply('Сначала привяжите Telegram по приглашению команды.');return true;}
        try{$archive=archivedReadingRound($reader['id'],(int)$m[1]);$s=$archive['stats'];$c=$archive['marathon'];$reply('📜 Круг '.$c['round'].' · история' ."\n".'Старт: '.$c['start'].'. Глав: '.$s['chapters'].'. Выполнено '.$s['goalWeeks'].'/22 недель.'."\n".implode("\n",array_map(fn($w)=>'Неделя '.$w['week'].': '.$w['chapters'].'/'.$w['goal'].' глав · '.$w['days'].' дн.',$s['reports'])),[[['text'=>'← К кругам','callback_data'=>'menu:rounds']]]);}catch(DomainException $e){$reply($e->getMessage());}return true;
    }
    if($callback&&($text==='circle:new'||preg_match('/^c_([yn])_([a-f0-9]{32})$/',$text,$m))){
        if(!$reader){$reply('Аккаунт недоступен. Получите новое приглашение.');return true;}$c=calendar($reader['id']);
        if($text==='circle:new'){
            $s=stats($reader['id']);if($s['goalWeeks']!==22){$reply('Для следующего круга завершите все 22 недели. Сейчас выполнено '.$s['goalWeeks'].'/22.');return true;}
            $token=bin2hex(random_bytes(16));sql("DELETE FROM requests WHERE user_id=? AND kind='round'",[$reader['id']]);
            sql('INSERT INTO requests(token_hash,kind,user_id,session_hash,expires_at) VALUES (?,?,?,?,?)',[hash('sha256',$token),'round',$reader['id'],$reader['session_epoch'].':'.$c['round'].':'.$c['today'],time()+900]);
            $reply('🔁 Начать круг '.($c['round']+1).' сегодня, '.$c['today'].'?'."\n".'Все результаты круга '.$c['round'].' сохранятся в истории. Новый круг: те же книги и главы, 22 недели с сегодняшнего дня. Главы из бота будут идти в новый круг.',[[['text'=>'✓ Начать новый круг','callback_data'=>'c_y_'.$token],['text'=>'Отмена','callback_data'=>'c_n_'.$token]]]);return true;
        }
        $r=sql("SELECT * FROM requests WHERE token_hash=? AND kind='round'",[hash('sha256',$m[2])])->fetch();
        if(!$r||$r['consumed']||$r['expires_at']<time()||$r['user_id']!==$reader['id']||$r['session_hash']!==$reader['session_epoch'].':'.$c['round'].':'.$c['today']){$reply('Подтверждение истекло или круг изменился. Откройте «Круги чтения» заново.');return true;}
        sql('UPDATE requests SET consumed=1 WHERE token_hash=?',[$r['token_hash']]);
        if($m[1]==='n')$reply('Новый круг не начат. Результаты не изменились.');
        else {try{$next=startReadingRound($reader['id'],$reader['id'],$c['round']);$reply('🎉 Круг '.$next['round'].' начат!'."\n".'Первая неделя: '.$next['calendar'][0]['start'].' — '.$next['calendar'][0]['end'].'. План: '.$next['calendar'][0]['goal'].' глав.'."\n".'Предыдущие результаты доступны в «Круги чтения».',[[['text'=>'📚 Мой новый план','callback_data'=>'menu:plan'],['text'=>'📖 Отметить чтение','callback_data'=>'menu:read']]]);}catch(DomainException $e){$reply($e->getMessage());}}return true;
    }
    if($action===null)return false;
    if($action==='site'){$base=rtrim(getenv('APP_URL')?:'','/');$reply($base?'Откройте сайт: планы, исправление глав и подробные отчёты.':'Администратор ещё не указал адрес сайта в настройках бота.',$base?[[['text'=>'🌐 Открыть сайт','url'=>$base]]]:null);return true;}
    if($action==='help'){$reply("❓ Как отмечать чтение\n1. Нажмите «📖 Отметить чтение».\n2. Введите только число новых глав или выберите быстрый вариант.\n3. Проверьте распределение и нажмите «Подтвердить». До этого главы не зачтены.\n\nСначала закрывается предыдущая неделя, затем текущая. Добавляйте только новые главы, не общий итог. «Отмена» отменяет незавершённый ввод. Исправить уже зачтённое можно на сайте.\n\nДлительность — между датами завершения соседних планов. Без предыдущего — от начала недели. Новый круг доступен после всех 22 недель; история сохраняется.");return true;}
    if(!$reader){$reply('Добро пожаловать! Сначала получите персональную ссылку у команды и привяжите Telegram. После этого кнопки откроют ваш план и прогресс.');return true;}
    $id=$reader['id'];$c=calendar($id);$s=stats($id);$header=telegramReaderHeader($reader,$c);
    if($action==='cancel'){sql('DELETE FROM telegram_menu_states WHERE user_id=?',[$id]);sql('DELETE FROM telegram_reading_requests WHERE user_id=?',[$id]);sql("DELETE FROM requests WHERE user_id=? AND kind='round'",[$id]);$reply('Отменено. Неподтверждённые главы не зачтены. Выберите действие в меню.');return true;}
    if($action==='read'){
        $eligible=array_filter($s['reports'],fn($w)=>$w['week']>=max(1,$c['current']-1)&&$w['week']<=min(22,$c['current'])&&$w['remaining']>0);$left=array_sum(array_column($eligible,'remaining'));
        if(!$left){$reply('✅ За текущую и предыдущую неделю всё прочитано.'.($s['goalWeeks']===22?' Можно начать следующий круг в «Круги чтения».':' Следующий план откроется по расписанию.'),[[['text'=>'📊 Мой прогресс','callback_data'=>'menu:progress'],['text'=>'🔁 Круги','callback_data'=>'menu:rounds']]]);return true;}
        sql('INSERT INTO telegram_menu_states VALUES (?,?,?,?,?) ON CONFLICT(user_id) DO UPDATE SET telegram_id=excluded.telegram_id,session_epoch=excluded.session_epoch,round_number=excluded.round_number,expires_at=excluded.expires_at',[$id,$telegramId,(int)$reader['session_epoch'],$c['round'],time()+900]);
        $buttons=[];foreach([1,5,10] as $n)if($n<=$left)$buttons[]=['text'=>'+'.$n.' глав','callback_data'=>'amount:'.$n];
        $reply('📖 '.$header."\n".'Сколько новых глав прочитали? Введите число от 1 до '.$left.' или выберите кнопку.'."\n".implode("\n",array_map(fn($w)=>'Неделя '.$w['week'].': осталось '.$w['remaining'].' глав.',$eligible))."\n".'Следующий шаг — проверка и подтверждение.',[$buttons,[['text'=>'Весь остаток: '.$left,'callback_data'=>'amount:'.$left],['text'=>'Отмена','callback_data'=>'menu:cancel']]]);return true;
    }
    if($action==='rounds'){
        $list=readingRounds($id);$lines=['🔁 '.$header,'Текущий круг: '.$s['chapters'].' глав · '.$s['goalWeeks'].'/22 недель.'];$buttons=[];
        foreach(array_slice($list,-10) as $r){$lines[]='Круг '.$r['number'].' · старт '.$r['start'].' · '.($r['active']?'активный':'завершён, '.$r['chapters'].' глав');if(!$r['active'])$buttons[]=[['text'=>'📜 История круга '.$r['number'],'callback_data'=>'circle:'.$r['number']]];}
        if($s['goalWeeks']===22)$buttons[]=[['text'=>'Начать круг '.($c['round']+1),'callback_data'=>'circle:new']];else $lines[]='Следующий круг откроется после выполнения 22/22 недель.';
        $reply(implode("\n",$lines),$buttons?:null);return true;
    }
    if($action==='weeks'){$names=['upcoming'=>'⏳','in_progress'=>'📖','overdue'=>'⚠️','completed'=>'✅','completed_late'=>'✅ С опозданием'];$reply('🗓 '.$header."\n".implode("\n",array_map(fn($w)=>$names[$w['status']].' Неделя '.$w['week'].': '.$w['chapters'].'/'.$w['goal'].' глав · до '.$w['end'],$s['reports'])),[[['text'=>'📖 Отметить чтение','callback_data'=>'menu:read'],['text'=>'📚 План недели','callback_data'=>'menu:plan']]]);return true;}
    $w=$s['pace'];
    if($action==='plan'){$w=$w??($c['current']<1?$s['reports'][0]:$s['reports'][21]);$reply('📚 '.$header."\n".'План недели '.$w['week'].': '.$w['start'].' — '.$w['end']."\n".implode("\n",telegramBookLines($w['books']))."\n".'Прочитано '.$w['chapters'].' из '.$w['goal'].' глав. Осталось '.$w['remaining'].'.'.($w['remaining']&&$w['daysLeft']?' Нужно '.$w['perDay'].' глав в день, осталось '.$w['daysLeft'].' дн.':'').($w['status']==='overdue'?"\n⚠️ Срок прошёл.":''),[[['text'=>'📖 Отметить чтение','callback_data'=>'menu:read']]]);return true;}
    $bar=str_repeat('■',min(10,(int)floor($s['progress']/10))).str_repeat('□',max(0,10-(int)floor($s['progress']/10)));
    $reply('📊 '.$header."\n".$bar.' '.$s['progress'].'%'."\n".'Всего: '.$s['chapters'].'/'.$s['goalTotal'].' глав. Выполнено '.$s['goalWeeks'].'/22 недель.'."\n".'Просрочено: '.$s['overdueWeeks'].'. Выполнено с опозданием: '.$s['lateWeeks'].'.'.($w?"\n".'Неделя '.$w['week'].': '.$w['chapters'].'/'.$w['goal'].' глав. '.($w['remaining']?'Осталось '.$w['remaining'].', темп '.$w['perDay'].' глав/день.':'✅ План выполнен за '.$w['days'].' дн.'):'')."\n".'Выберите действие кнопками ниже.');return true;
}
