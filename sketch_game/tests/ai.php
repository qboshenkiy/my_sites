<?php
require dirname(__DIR__).'/lib/ai.php';
$calls=[];
$transport=function($body)use(&$calls){$calls[]=$body;return count($calls)===1?['guess'=>'Корабль','description'=>'Деревянный корабль на воде']:['stars'=>4,'feedback'=>'Добавьте животных, чтобы ковчег узнавался лучше.'];};
$result=judgeDrawing('data:image/png;base64,test','Ноев ковчег',$transport);
if($result['stars']!==4||count($calls)!==2||str_contains(json_encode($calls[0],JSON_UNESCAPED_UNICODE),'Ноев ковчег')||!str_contains(json_encode($calls[1],JSON_UNESCAPED_UNICODE),'Ноев ковчег'))throw new RuntimeException('Blind recognition failed');
try{judgeDrawing('test','Кот',fn($b)=>isset($b['text']['format']['schema']['properties']['stars'])?['stars'=>9,'feedback'=>'bad']:['guess'=>'Кот','description'=>'Кот']);throw new RuntimeException('Invalid stars accepted');}catch(DomainException $expected){}
echo "PASS: blind recognition, structured grading, invalid stars rejected, no external API calls\n";
