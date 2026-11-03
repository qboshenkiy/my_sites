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
function telegramCatchupPaces(array $calendar,array $weeks): array {
    $current=array_values(array_filter($weeks,fn($w)=>$w['start']<=$calendar['today']&&$w['end']>=$calendar['today']));
    $base=max(1,min(200,(int)ceil(($current[0]['goal']??35)/7)));
    return array_values(array_unique([$base,min(200,$base+2),min(200,$base+5)]));
}
function telegramCatchupText(array $calendar,array $weeks,?int $pace=null): string {
    if($calendar['current']<1)return 'Марафон ещё не начался. Расчёт появится в день старта.';
    $today=$calendar['today'];$credits=array_map('telegramCatchupCredit',$weeks);$behind=telegramCatchupDeficit($weeks,$credits,$today);
    $lines=['🧭 Как догнать?','Расчёт на '.(new DateTimeImmutable($today))->format('d.m.Y').'.'];
    if(!$behind)return implode("\n",array_merge($lines,['Вы на графике к концу сегодняшнего дня. Долга по первому чтению нет.','Продолжайте по плану недели; повторные круги не создают нового долга.']));
    $lines[]='До ориентира на сегодня: '.$behind.' глав.';
    if($pace===null){
        $lines[]='';$lines[]='Выберите посильный темп — покажу, что читать сегодня и к какой дате догоните.';
        foreach(telegramCatchupPaces($calendar,$weeks) as $suggested){$r=telegramCatchupForecast($weeks,$today,$suggested);$lines[]='• '.$suggested.' глав/день → '.($r?(new DateTimeImmutable($r['date']))->format('d.m.Y').($r['date']>$calendar['end']?' · после конца марафона':''):'не догоните за год');}
        $lines[]='';$lines[]='Для своего темпа напишите, например: темп 6';
    }else{
        if($pace<1||$pace>200)return 'Укажите темп от 1 до 200 глав в день: например, темп 6';
        $r=telegramCatchupForecast($weeks,$today,$pace);$lines[]='Ваш темп: '.$pace.' глав в день.';$lines[]='';
        $lines[]='📖 Сегодня прочитайте:';
        foreach(telegramCatchupTodayReading($weeks,$today,$pace) as $range)$lines[]='• '.$range;
        $lines[]='';
        if($r){$lines[]='🗓 Догоните '.(new DateTimeImmutable($r['date']))->format('d.m.Y').' — за '.$r['days'].' дн.';$lines[]='За это время: '.$r['chapters'].' глав, включая новый план.';if($r['date']>$calendar['end'])$lines[]='Этот темп приведёт к завершению после конца марафона. Для более ранней даты выберите темп выше.';}
        else $lines[]='Таким темпом не получится догнать план за ближайший год. Выберите темп выше.';
    }
    $lines[]='';$lines[]='Считаем с сегодняшнего дня, по графику на 7 дней и с учётом новых недель. Последний день может быть короче. Длина глав разная; темп выбираете вы.';
    $lines[]='Если уже читали эти главы — сначала отметьте их, затем пересчитайте.';
    return implode("\n",$lines);
}

// Physical book/chapter ranges for today's selected pace; no progress is written.
function telegramCatchupTodayReading(array $weeks,string $today,int $pace): array {
    $lines=[];$left=max(0,$pace);
    foreach($weeks as $week){
        if(!$left)break;if($week['start']>$today)continue;
        $credit=telegramCatchupCredit($week);$take=min($left,max(0,$week['goal']-$credit));
        if(!$take)continue;$left-=$take;
        if(empty($week['books'])){$lines[]='Неделя '.($week['week']??'?').': ещё '.$take.' глав';continue;}
        $offset=0;$begin=$credit;$end=$credit+$take;
        foreach($week['books'] as $book){
            $length=$book['chapter_to']-$book['chapter_from']+1;
            $from=max($begin,$offset);$to=min($end,$offset+$length);
            if($from<$to){$a=$book['chapter_from']+$from-$offset;$b=$book['chapter_from']+$to-$offset-1;$lines[]=$book['title'].': '.($a===$b?'глава '.$a:'главы '.$a.'–'.$b);}
            $offset+=$length;
        }
    }
    return $lines;
}
