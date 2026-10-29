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
    return "За 7 дней:\n".telegramDailyTarget($plan['books'],$plan['goal'],$day,7)
        ."\n\nЗа 6 дней:\n".telegramDailyTarget($plan['books'],$plan['goal'],$day,6);
}
function telegramDailyReminders(?DateTimeImmutable $now=null,?callable $deliver=null): void {
    $now=($now??new DateTimeImmutable())->setTimezone(new DateTimeZone(date_default_timezone_get()));
    if($now->format('H:i')<'08:00')return;
    $group=setting('reading_group');if($group==='')return;
    $thread=setting('reading_group_thread');
    $calendar=calendar();$day=$now->format('Y-m-d');
    if($calendar['today']!==$day)return;
    $text=telegramDailyText($calendar);if($text===null)return;
    $time=$now->getTimestamp();
    sql('CREATE TABLE IF NOT EXISTS telegram_daily_group_deliveries(chat_id TEXT NOT NULL,thread_id TEXT NOT NULL,day TEXT NOT NULL,sent_at INTEGER,next_attempt INTEGER NOT NULL DEFAULT 0,PRIMARY KEY(chat_id,thread_id,day))');
    $sent=sql('SELECT * FROM telegram_daily_group_deliveries WHERE chat_id=? AND thread_id=? AND day=?',[$group,$thread,$day])->fetch();
    if($sent&&($sent['sent_at']!==null||(int)$sent['next_attempt']>$time))return;
    // The polling worker holds bot.lock: no second sender runs concurrently.
    sql('INSERT INTO telegram_daily_group_deliveries(chat_id,thread_id,day,next_attempt) VALUES (?,?,?,?) ON CONFLICT(chat_id,thread_id,day) DO UPDATE SET next_attempt=excluded.next_attempt',[$group,$thread,$day,$time+300]);
    $args=['chat_id'=>$group,'text'=>$text];if($thread!=='')$args['message_thread_id']=(int)$thread;
    $deliver??=fn($args)=>telegramCall('sendMessage',$args);
    try {
        $deliver($args);
        sql('UPDATE telegram_daily_group_deliveries SET sent_at=? WHERE chat_id=? AND thread_id=? AND day=?',[$time,$group,$thread,$day]);
    }catch(Throwable $e){error_log('Daily group reading target delivery failed; retry in 5 minutes.');}
}
