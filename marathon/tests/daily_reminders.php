<?php
// Run with an empty MARATHON_DATA_DIR; the transport is fake, never contacts Telegram.
require dirname(__DIR__).'/lib/telegram.php';
function check(bool $value,string $why): void {if(!$value)throw new RuntimeException($why);}
$books=[['title'=>'Левит','chapter_from'=>1,'chapter_to'=>27],['title'=>'Числа','chapter_from'=>1,'chapter_to'=>33]];
check(telegramDailyTarget($books,63,1,7)==='Левит 9 глава','7-day target uses actual chapter ranges');
check(telegramDailyTarget($books,63,1,6)==='Левит 10 глава','6-day target');
check(telegramDailyTarget($books,60,4,7)==='Числа 8 глава','Book boundary');
check(telegramDailyTarget($books,60,6,6)==='Числа 33 глава','6-day finish');
check(telegramDailyTarget($books,60,7,7)==='Числа 33 глава','7-day finish');
check(telegramDailyTarget([['title'=>'Книга','chapter_from'=>11,'chapter_to'=>17]],7,1,7)==='Книга 11 глава','Partial range');
check(telegramDailyTarget([],63,1,7)==='9 из 63 глав','Numeric fallback');
db();sql("UPDATE settings SET value='2026-10-12' WHERE key='start'");sql('UPDATE week_plans SET chapters=60 WHERE week=1');
foreach($books as $i=>$b)sql('INSERT INTO week_plan_books VALUES (?,?,?,?,?,?)',[(string)$i,1,$i,$b['title'],$b['chapter_from'],$b['chapter_to']]);
foreach([['a','101',1,null],['b','102',0,null],['c',null,1,null],['d','104',1,1]] as [$id,$tg,$active,$deleted])sql('INSERT INTO users(id,name,role,telegram_id,active,deleted_at,created_at) VALUES (?,?,?,?,?,?,?)',[$id,'Тест','participant',$tg,$active,$deleted,time()]);
putenv('MARATHON_TEST_TODAY=2026-10-12');$sent=[];$send=function($args)use(&$sent){$sent[]=$args;};
telegramDailyReminders(new DateTimeImmutable('2026-10-12 07:59:59'),$send);check(count($sent)===0,'Not before 08:00');
telegramDailyReminders(new DateTimeImmutable('2026-10-12 08:00:00'),$send);check(count($sent)===1&&$sent[0]['chat_id']==='101','Only linked active accounts');check(str_contains($sent[0]['text'],'Левит 9 глава')&&str_contains($sent[0]['text'],'Левит 10 глава'),'Both plans in message');
telegramDailyReminders(new DateTimeImmutable('2026-10-12 12:00:00'),$send);check(count($sent)===1,'Persisted deduplication');
putenv('MARATHON_TEST_TODAY=2026-10-13');$fail=function(){throw new RuntimeException('Fake network failure');};
telegramDailyReminders(new DateTimeImmutable('2026-10-13 08:00:00'),$fail);
telegramDailyReminders(new DateTimeImmutable('2026-10-13 08:04:00'),$send);check(count($sent)===1,'Retry backoff');
telegramDailyReminders(new DateTimeImmutable('2026-10-13 08:05:00'),$send);check(count($sent)===2,'Retry succeeds');
putenv('MARATHON_TEST_TODAY=2026-10-18');telegramDailyReminders(new DateTimeImmutable('2026-10-18 09:00:00'),$send);check(count($sent)===3&&str_contains($sent[2]['text'],'запасной день'),'Day seven and no stale-day catchup');
putenv('MARATHON_TEST_TODAY=2026-10-19');telegramDailyReminders(new DateTimeImmutable('2026-10-19 09:00:00'),$send);check(count($sent)===4&&str_contains($sent[3]['text'],'неделя 2 · день 1/7'),'Next week resets day');
$plans=calendar()['calendar'];$plans[0]['goal']=7;$plans[0]['books']=[['title'=>'Личная книга','chapter_from'=>11,'chapter_to'=>17]];
sql('INSERT INTO reading_rounds(user_id,number,start,plans,opened,created_at) VALUES (?,?,?,?,?,?)',['a',2,'2026-10-20',json_encode($plans),'[]',time()]);
putenv('MARATHON_TEST_TODAY=2026-10-20');telegramDailyReminders(new DateTimeImmutable('2026-10-20 08:00:00'),$send);check(count($sent)===5&&str_contains($sent[4]['text'],'Личная книга 11 глава'),'Personal round start and frozen books');
putenv('MARATHON_TEST_TODAY=2026-10-11');telegramDailyReminders(new DateTimeImmutable('2026-10-11 09:00:00'),$send);check(count($sent)===5,'Before marathon');
putenv('MARATHON_TEST_TODAY=2027-04-01');telegramDailyReminders(new DateTimeImmutable('2027-04-01 09:00:00'),$send);check(count($sent)===5,'After marathon');
echo "PASS: daily targets, book boundaries, partial ranges, scheduling, eligibility, deduplication, retries, spare day and calendar limits\n";
