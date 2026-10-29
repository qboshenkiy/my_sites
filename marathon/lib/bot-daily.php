<?php
declare(strict_types=1);

// Cumulative target: each day ends at a whole chapter, the last day at the last book.
function telegramDailyTarget(array $books,int $goal,int $day,int $days): string {
    $total=$books?array_sum(array_map(fn($b)=>(int)$b['chapter_to']-(int)$b['chapter_from']+1,$books)):$goal;
    $target=(int)ceil($total*min($day,$days)/$days);
    if(!$books)return $target.' из '.$total.' глав';
    $left=$target;
    foreach($books as $book){
        $count=(int)$book['chapter_to']-(int)$book['chapter_from']+1;
        if($left<=$count)return $book['title'].' '.((int)$book['chapter_from']+$left-1).' глава';
        $left-=$count;
    }
    throw new LogicException('Reading target exceeds plan.');
}
function telegramDailyText(array $calendar): ?string {
    $week=$calendar['current'];
    if($week<1||$week>$calendar['weeks'])return null;
    $plan=$calendar['calendar'][$week-1];
    $day=(int)(new DateTimeImmutable($plan['start']))->diff(new DateTimeImmutable($calendar['today']))->format('%a')+1;
    $lines=['📚 Ориентир чтения · неделя '.$week.' · день '.$day.'/7',
        'К концу сегодняшнего дня ('.$calendar['today'].') нужно дочитать включительно:',
        '', 'За 7 дней:',telegramDailyTarget($plan['books'],$plan['goal'],$day,7),
        '', 'За 6 дней:',telegramDailyTarget($plan['books'],$plan['goal'],$day,6)];
    if($day===7)$lines[]='План на 6 дней уже завершён. Сегодня — запасной день.';
    $lines[]='';$lines[]='Это ориентир по плану недели; ваши отметки чтения не меняются.';
    return implode("\n",$lines);
}
function telegramDailyReminders(?DateTimeImmutable $now=null,?callable $deliver=null): void {
    $now=($now??new DateTimeImmutable())->setTimezone(new DateTimeZone(date_default_timezone_get()));
    if($now->format('H:i')<'08:00')return;
    $deliver??=fn($args)=>telegramCall('sendMessage',$args);
    sql('CREATE TABLE IF NOT EXISTS telegram_daily_deliveries(user_id TEXT NOT NULL,day TEXT NOT NULL,telegram_id TEXT NOT NULL,sent_at INTEGER,next_attempt INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(user_id,day))');
    $day=$now->format('Y-m-d');$time=$now->getTimestamp();$attempts=0;
    foreach(sql("SELECT id,telegram_id FROM users WHERE active=1 AND deleted_at IS NULL AND telegram_id IS NOT NULL ORDER BY id")->fetchAll() as $user){
        $sent=sql('SELECT * FROM telegram_daily_deliveries WHERE user_id=? AND day=?',[$user['id'],$day])->fetch();
        if($sent&&($sent['sent_at']!==null||(int)$sent['next_attempt']>$time))continue;
        $c=calendar($user['id']);
        if($c['today']!==$day)continue;
        $text=telegramDailyText($c);if($text===null)continue;
        // The polling worker holds bot.lock: no second sender runs concurrently.
        sql('INSERT INTO telegram_daily_deliveries(user_id,day,telegram_id,next_attempt) VALUES (?,?,?,?) ON CONFLICT(user_id,day) DO UPDATE SET telegram_id=excluded.telegram_id,next_attempt=excluded.next_attempt',[$user['id'],$day,$user['telegram_id'],$time+300]);
        try {
            $deliver(['chat_id'=>$user['telegram_id'],'text'=>$text,'reply_markup'=>['inline_keyboard'=>[[['text'=>'📚 План недели','callback_data'=>'menu:plan'],['text'=>'📖 Отметить чтение','callback_data'=>'menu:read']]]]]);
            sql('UPDATE telegram_daily_deliveries SET sent_at=? WHERE user_id=? AND day=?',[$time,$user['id'],$day]);
        }catch(Throwable $e){error_log('Daily reading reminder delivery failed; retry in 5 minutes.');break;}
        if(++$attempts>=5)break; // Keep incoming bot commands responsive during delivery failures.
    }
}
