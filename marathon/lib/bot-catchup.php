<?php
declare(strict_types=1);
function telegramCatchupCredit(array $week): int {return ($week['completedCycles']??0)>0?(int)$week['goal']:min((int)$week['goal'],(int)$week['chapters']);}
function telegramCatchupDue(array $week,string $date): int {
    if($date<$week['start'])return 0;
    $day=min(7,(int)(new DateTimeImmutable($week['start']))->diff(new DateTimeImmutable($date))->format('%a')+1);
    return (int)ceil($week['goal']*$day/7);
}
function telegramCatchupDeficit(array $weeks,array $credits,string $date): int {
    $left=0;foreach($weeks as $i=>$week)$left+=max(0,telegramCatchupDue($week,$date)-$credits[$i]);return $left;
}
// Simulate reading from today, oldest unfinished week first; future weeks open on their own dates.
function telegramCatchupForecast(array $weeks,string $today,int $pace): ?array {
    $credits=array_map('telegramCatchupCredit',$weeks);$date=new DateTimeImmutable($today);$read=0;
    for($day=1;$day<=365;$day++,$date=$date->modify('+1 day')){
        $stamp=$date->format('Y-m-d');$capacity=$pace;
        foreach($weeks as $i=>$week){if($stamp<$week['start'])continue;$add=min($capacity,max(0,$week['goal']-$credits[$i]));$credits[$i]+=$add;$capacity-=$add;$read+=$add;if(!$capacity)break;}
        if(telegramCatchupDeficit($weeks,$credits,$stamp)===0)return ['date'=>$stamp,'days'=>$day,'chapters'=>$read];
    }
    return null;
}
function telegramCatchupText(array $calendar,array $weeks): string {
    if($calendar['current']<1)return 'Марафон ещё не начался. Расчёт появится в день старта.';
    $credits=array_map('telegramCatchupCredit',$weeks);$behind=telegramCatchupDeficit($weeks,$credits,$calendar['today']);
    $lines=['🧭 Как догнать?','По вашим отмеченным главам на '.$calendar['today'].'.'];
    if(!$behind)return implode("\n",array_merge($lines,['Вы на графике к концу сегодняшнего дня. Долга по первому чтению нет.','Продолжайте по плану недели; повторные круги не создают нового долга.']));
    $lines[]='До ориентира на сегодня не хватает '.$behind.' глав.';$lines[]='';
    foreach([10,15,20] as $pace){$result=telegramCatchupForecast($weeks,$calendar['today'],$pace);$lines[]=$result?'• '.$pace.' глав в день → догоните '.$result['date'].' (за '.$result['days'].' дн., всего прочитать '.$result['chapters'].' глав).'.($result['date']>$calendar['end']?' Это позже конца марафона.':''):'• '.$pace.' глав в день → не догоните в ближайшие 365 дней.';}
    $lines[]='';$lines[]='Считаем с сегодняшнего дня, по графику на 7 дней, с учётом следующих недель. В последний день может потребоваться меньше глав.';
    $lines[]='Это прогноз при ежедневном чтении, а не обещание. Длина глав разная — выбирайте посильный темп. Если читали, но не отмечали, сначала внесите главы.';
    return implode("\n",$lines);
}
