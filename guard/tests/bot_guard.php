<?php
require dirname(__DIR__,2).'/marathon/lib/bot-guard.php';
function check($value,$message){if(!$value)throw new RuntimeException($message);}
$u=['message'=>['from'=>['id'=>123,'first_name'=>'Иван','username'=>'ivan'],'chat'=>['id'=>123,'type'=>'private'],'text'=>'/start i_'.str_repeat('a',48)]];
check(guardIncoming($u),'First incoming allowed');
check(count(guardCli('people',[])['people'])===1,'User registered');
$h=guardCli('history',['person'=>'123']);check(!str_contains(json_encode($h),str_repeat('a',48)),'Login token hidden');
guardCli('block',['person'=>'123']);check(!guardIncoming($u),'Blocked user ignored');
guardCli('unblock',['person'=>'123']);check(guardIncoming($u),'Unblocked user allowed');
check(!str_contains(guardText('r_y_'.str_repeat('b',32)),str_repeat('b',32)),'Callback token hidden');
guardOutgoing('sendMessage',['chat_id'=>123,'text'=>'Hello https://site.test/?token=private']);
check(!str_contains(json_encode(guardCli('history',['person'=>'123'])),'private'),'URL hidden');
$failed=false;try{guardCli('send',['person'=>'999','text'=>'hello']);}catch(Throwable $e){$failed=true;}check($failed,'Cannot message unknown user');
$u['update_id']=100;
guardIncoming($u);$count=count(guardCli('history',['person'=>'123'])['events']);guardIncoming($u);check(count(guardCli('history',['person'=>'123'])['events'])===$count,'Retried update not counted as spam twice');
$baseline=guardCli('activity',['after'=>null]);check($baseline['events']===[],'Activity baseline skips historical messages');
guardFailure($u,'response',new RuntimeException('https://api.telegram.org/botPRIVATE/sendMessage HTTP 500'));
$feed=guardCli('activity',['after'=>$baseline['cursor']]);check(count($feed['events'])===1,'Error is visible in incremental activity');check($feed['events'][0]['direction']==='error','Error type');check(!str_contains(json_encode($feed),'PRIVATE'),'Raw error and token not exposed');check(str_contains($feed['events'][0]['text'],'HTTP 500'),'Safe HTTP code retained');
echo "PASS: PHP audit, redaction, block/unblock and unknown-recipient protection\n";
