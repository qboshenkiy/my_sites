<?php
require dirname(__DIR__).'/lib/telegram.php';
function check(bool $ok,string $why): void {if(!$ok)throw new RuntimeException($why);}
$weeks=[];for($i=0;$i<3;$i++){$start=(new DateTimeImmutable('2026-10-12'))->modify('+'.($i*7).' days');$weeks[]=['start'=>$start->format('Y-m-d'),'end'=>$start->modify('+6 days')->format('Y-m-d'),'goal'=>70,'chapters'=>0,'completedCycles'=>0];}
$p=telegramCatchupForecast($weeks,'2026-10-19',20);check($p['date']==='2026-10-25'&&$p['chapters']===140,'Forecast includes newly due reading');
check(telegramCatchupForecast($weeks,'2026-10-19',10)['date']==='2026-11-08','Slow pace catches up only after end');
$weeks[0]['completedCycles']=1;check(telegramCatchupCredit($weeks[0])===70,'Repeats do not create fresh debt');
db();sql("UPDATE settings SET value='2026-10-12' WHERE key='start'");putenv('MARATHON_TEST_TODAY=2026-10-26');
foreach([['admin','100','admin'],['reader','200','participant']] as [$id,$tg,$role])sql('INSERT INTO users(id,name,role,telegram_id,created_at) VALUES (?,?,?,?,?)',[$id,$id,$role,$tg,time()]);
$admin=user('admin');$reader=user('reader');$n=8000;
function bot(string $text,int $from=100,string $type='private',int $chat=100,bool $callback=false): array {
    global $n;$message=['chat'=>['id'=>$chat,'type'=>$type,'title'=>'Тестовая группа'],'from'=>['id'=>$from],'text'=>$text];
    return telegramUpdate($callback?['update_id'=>++$n,'callback_query'=>['id'=>(string)$n,'from'=>['id'=>$from],'message'=>$message,'data'=>$text]]:['update_id'=>++$n,'message'=>$message]);
}
check(bot('/reading_here',200,'supergroup',-900)===[],'Participant cannot bind group');check(setting('reading_group')==='','No unauthorized mutation');
check(count(bot('/reading_here',100,'supergroup',-900))===1,'Linked admin binds group');
check(str_contains(bot('Как догнать?',200,'private',200)[0]['args']['text'],'До ориентира'),'Personal menu');
check(str_contains(bot('📣 Отправить в группу',200,'private',200)[0]['args']['text'],'только администратор'),'Participant cannot send group report');
$reply=bot('📣 Отправить в группу');$last=$reply[count($reply)-1];$action=$last['args']['reply_markup']['inline_keyboard'][0][0]['callback_data'];
check(str_starts_with($action,'group:send:'),'Preview confirmation');$delivered=[];$send=function($args)use(&$delivered){$delivered[]=$args;};
telegramGroupDeliveries($send);check(!$delivered,'Preview alone does not send');
bot($action,100,'private',100,true);bot($action,100,'private',100,true);telegramGroupDeliveries($send);$count=count($delivered);check($count===1&&$delivered[0]['text']===telegramDailyText(calendar())&&$delivered[0]['chat_id']==='-900','Only confirmed target group');telegramGroupDeliveries($send);check(count($delivered)===$count,'No duplicate confirmed send');
$reply=bot('📣 Отправить в группу');$action=$reply[count($reply)-1]['args']['reply_markup']['inline_keyboard'][0][0]['callback_data'];bot($action,100,'private',100,true);bot('/reading_here',100,'supergroup',-901);telegramGroupDeliveries($send);check(count($delivered)===$count,'Changed group cancels queued old report');
$allocation=telegramReadingPlan('reader',15);check($allocation[0]['week']===1&&count($allocation)>=2,'Reading reaches debt older than one week');
check(telegramGroupReport()===telegramDailyText(calendar()),'Manual message equals the shared daily target, no personal results');
sql('INSERT INTO telegram_group_dispatches(id,actor_id,actor_epoch,chat_id,payload,confirmed,expires_at,format_version) VALUES (?,?,?,?,?,1,?,0)',['legacy','admin',$admin['session_epoch'],'-901','Old personal data',time()+600]);
sql('INSERT INTO telegram_group_parts(dispatch_id,part,text) VALUES (?,0,?)',['legacy','Old personal data']);telegramGroupDeliveries($send);check(count($delivered)===$count,'Old queued personal reports are retired after update');
echo "PASS: catch-up forecast, new weekly workload, repeat credit, private button, group authorization/preview/confirmation/deduplication, changed group and old debt allocation\n";
