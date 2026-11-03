<?php
require dirname(__DIR__).'/lib/bot-catchup.php';
function check($ok,$why){if(!$ok)throw new RuntimeException($why);}
$books=[['title'=>'Левит','chapter_from'=>1,'chapter_to'=>27],['title'=>'Числа','chapter_from'=>1,'chapter_to'=>36]];
$weeks=[['week'=>1,'start'=>'2026-10-12','end'=>'2026-10-18','goal'=>63,'chapters'=>20,'books'=>$books]];
check(telegramCatchupTodayReading($weeks,'2026-10-19',10)===['Левит: главы 21–27','Числа: главы 1–3'],'Cross-book ranges use physical chapters');
$weeks[0]['chapters']=62;
check(telegramCatchupTodayReading($weeks,'2026-10-19',10)===['Числа: глава 36'],'Final partial day');
$weeks[0]['completedCycles']=1;
check(telegramCatchupTodayReading($weeks,'2026-10-19',10)===[],'Repeated passes never create catchup debt');
$weeks[0]['completedCycles']=0;$weeks[0]['start']='2026-10-26';
check(telegramCatchupTodayReading($weeks,'2026-10-19',10)===[],'Future weeks do not open early');
$weeks[0]['start']='2026-10-12';$weeks[0]['chapters']=0;$weeks[0]['books']=[['title'=>'Фрагмент','chapter_from'=>10,'chapter_to'=>72]];
check(telegramCatchupTodayReading($weeks,'2026-10-19',5)===['Фрагмент: главы 10–14'],'Non-one starting chapter');
echo "PASS: catchup physical ranges, book transition, final partial day, repeats and future weeks\n";
$weeks=[['week'=>1,'start'=>'2026-10-12','end'=>'2026-10-18','goal'=>63,'chapters'=>20,'books'=>$books]];
$calendar=['current'=>2,'today'=>'2026-10-19','end'=>'2027-03-14'];
$text=telegramCatchupText($calendar,$weeks,10);
check(str_contains($text,'Левит: главы 21–27')&&str_contains($text,'Числа: главы 1–3'),'Chosen pace shows physical reading ranges');
check(str_contains($text,'23.10.2026')&&str_contains($text,'43 глав'),'Forecast includes a shorter final day');
check(str_contains(telegramCatchupText($calendar,$weeks),'темп 6'),'Own pace is discoverable');
check(str_contains(telegramCatchupText($calendar,$weeks,0),'от 1 до 200'),'Invalid pace rejected');
echo "PASS: chosen pace, readable catchup date, precise daily assignment and custom pace validation\n";
