<?php
require dirname(__DIR__).'/assets/bluff.php';
foreach([['Нoй','Ной'],["Н\u{200b}ой",'Ной'],['Но й','Ной'],['Это был Ной','Ной'],['Аврааам','Авраам'],['Иаков и Иосиф','Иосиф и Иаков']] as [$a,$b])if(!bluffMatchesTruth($a,$b))throw new RuntimeException('Missed equivalent answer');
foreach([['49','50'],['не Ной','Ной'],['Иосиф','Иосия'],['Рим','Риф'],['Моисей','Ной']] as [$a,$b])if(bluffMatchesTruth($a,$b))throw new RuntimeException('Different answers merged');
echo "PASS: homoglyphs, invisible characters, spacing, filler, typo and reordered-word guards; distinct numbers and names\n";
