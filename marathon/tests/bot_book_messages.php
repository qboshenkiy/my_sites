<?php
require dirname(__DIR__).'/lib/telegram.php';
function check($ok,$message){if(!$ok)throw new RuntimeException($message);}
$w=['week'=>3,'cycle'=>1,'goal'=>63,'chapters'=>59,'added'=>2,'days'=>3,'completed'=>false,'books'=>[['title'=>'Левит','chapter_from'=>1,'chapter_to'=>27],['title'=>'Числа','chapter_from'=>1,'chapter_to'=>36]]];
$preview=telegramReadingWeekMessage($w,true);
check(str_contains($preview,'Левит')&&str_contains($preview,'по главу 27 из 27'),'Completed first book shown separately');
check(str_contains($preview,'Числа')&&str_contains($preview,'по главу 34 из 36'),'61 total displayed as Numbers chapter 34');
check(str_contains($preview,'Далее: Числа · глава 35'),'Correct next physical chapter');
check(!str_contains($preview,'63')&&!str_contains($preview,'61 из'),'No cumulative counter in book confirmation');
$w['chapters']=61;$confirmed=telegramReadingWeekMessage($w);
check(str_contains($confirmed,'Остановились: Числа · глава 34'),'Saved result shows book position');
$w['chapters']=27;$w['added']=1;$boundary=telegramReadingWeekMessage($w,true);
check(str_contains($boundary,'по главу 1 из 36'),'Second book restarts at chapter one');
$w['chapters']=63;$w['completed']=true;check(str_contains(telegramReadingWeekMessage($w),'Все книги этого плана прочитаны'),'Completed plan');
$w['books']=[];$w['completed']=false;check(str_contains(telegramReadingWeekMessage($w),'63 из 63 глав'),'Numeric fallback only without book plan');
echo "PASS: exact screenshot scenario, per-book confirmation, next chapter, saved message, boundary and no-book fallback\n";
