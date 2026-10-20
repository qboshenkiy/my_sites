<?php
declare(strict_types=1);
// Run only against an explicitly supplied disposable data directory.
if(PHP_SAPI!=='cli'||!getenv('MARATHON_DATA_DIR'))exit(2);
require dirname(__DIR__).'/lib/core.php';
function check(bool $ok,string $message): void {if(!$ok)throw new RuntimeException($message);}
function today(string $date): void {putenv('MARATHON_TEST_TODAY='.$date);}
function result(string $id): array {return weekResults($id)[1];}
today('2026-10-19');db();
foreach(['admin'=>'admin','reader'=>'participant','mod'=>'moderator','daily'=>'participant'] as $id=>$role)sql('INSERT INTO users(id,name,role,created_at) VALUES (?,?,?,?)',[$id,$id,$role,time()]);
sql('UPDATE week_plans SET chapters=40 WHERE week=2');
completeWeek('daily','admin',1,null);
// Even a previous plan completed late/early cannot shift this week's start.
sql("INSERT INTO week_completions(user_id,week,completed_on) VALUES ('reader',1,'2026-10-15')");
$first=saveWeeklyResult('reader','reader',2,10,null,'','');
check($first['days']===1&&$first['recordedOn']==='2026-10-19','First-day partial reading must be one day.');
today('2026-10-20');$next=result('reader');
check($next['days']===1&&$next['elapsedDays']===2&&$next['durationFrom']==='2026-10-19','Viewing yesterday on day 2 must still show 1 saved day.');
check($next['actualPerDay']===10.0&&$next['daysAtToday']===2,'Actual pace and today preview must be independent.');
$comment=saveWeeklyResult('reader','reader',2,10,null,'Title','Comment only');
check($comment['days']===1,'Editing only a comment must not change reading date.');
$second=saveWeeklyResult('reader','reader',2,20,null,'','');
check($second['days']===2&&$second['recordedOn']==='2026-10-20','A changed total on day 2 freezes two days.');
today('2026-10-22');check(result('reader')['days']===2,'An incomplete plan must also keep its saved duration.');
$done=completeWeek('reader','reader',2,null);
check($done['days']===4&&$done['completedOn']==='2026-10-22','Whole-plan completion uses the actual completion day.');
today('2026-10-25');check(result('reader')['days']===4,'Completed days stay frozen.');
$manual=saveWeeklyResult('reader','admin',2,40,6,'','');
check($manual['days']===6,'Admin can explicitly correct duration.');
$preserved=saveWeeklyResult('reader','reader',2,39,6,'','');
check($preserved['days']===6,'Participant chapter correction must preserve the administrator override.');
foreach(['reader','mod'] as $actor){
    try{saveWeeklyResult('reader',$actor,2,39,3,'','');throw new RuntimeException('Manual change unexpectedly accepted.');}
    catch(DomainException $e){check(str_contains($e->getMessage(),'администратор'),'Only admin may manually change days.');}
}
// Daily and Telegram records use their recorded date, not the time of reading the report.
today('2026-10-20');addReading('daily','daily',5,'2026-10-19','','','site','entry_1');
check(result('daily')['days']===1&&result('daily')['recordedOn']==='2026-10-19','Backdated daily reading uses its date.');
addReading('daily','daily',5,'2026-10-20','','','site','entry_2');
today('2026-10-22');check(result('daily')['days']===2,'Daily marks do not drift on later visits.');
$telegram=addTelegramReading('daily',2,7001);
check(result('daily')['days']===4,'Telegram reading on day 4 records day 4.');
today('2026-10-24');check(result('daily')['days']===4,'Telegram partial reading must stay frozen too.');
// Repeat resets old dates, but still belongs to this calendar week's plan.
today('2026-10-25');completeWeek('daily','daily',2,null);startWeeklyRepeat('daily','daily',2,1);
$blank=result('daily');check($blank['days']===0&&$blank['recordedOn']===null,'New weekly pass must have no old reading date.');
$repeat=saveWeeklyResult('daily','daily',2,5,null,'','');check($repeat['days']===7,'Repeat still counts from the current week start.');
check($repeat['repeats'][0]['days']===7,'Prior completed pass stays archived.');
// Legacy rows with no dedicated date use the last recorded timestamp, not today.
sql("INSERT INTO reports(user_id,week,chapters_manual,editor_id,updated_at) VALUES ('mod',2,10,'admin',?)",[(new DateTimeImmutable('2026-10-19 12:00:00'))->getTimestamp()]);
check(result('mod')['days']===1,'Legacy partial result should freeze to its saved timestamp.');
echo "PASS: saved-day durations for partial/completed/daily/Telegram reading, legacy rows, repeat reset and admin-only changes\n";
