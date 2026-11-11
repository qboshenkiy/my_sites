<?php
declare(strict_types=1);
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){http_response_code(404);exit;}

function pulseStructuredQuestion(array $question): bool {
    return in_array($question['block']??'choice',['matching','ordering'],true);
}
function pulseQuestionChoices(array $question,array $choices): array {
    $choices=array_map('intval',$choices);
    if(!pulseStructuredQuestion($question))sort($choices);
    return $choices;
}
function pulseQuestionCorrect(array $question,array $choices): bool {
    $correct=$question['correct']??null;
    $expected=is_array($correct)?$correct:[$correct===null?-1:$correct];
    return ($question['type']??'quiz')==='quiz'&&pulseQuestionChoices($question,$choices)===pulseQuestionChoices($question,$expected);
}
function pulseNormalizeBlock(array $question): array {
    $block=$question['block']??'choice';
    if(!in_array($block,['choice','matching','ordering','missing_word','scenario','speaker'],true))throw new DomainException('Неизвестный блок вопроса.');
    $question['block']=$block;
    if($block!=='matching')unset($question['prompts']);
    if($block==='choice')return $question;
    if($question['type']!=='quiz')throw new DomainException('Для этого блока нужен вопрос с правильным ответом.');
    if(!pulseStructuredQuestion($question))return $question;
    $count=count($question['options']);
    if($count<2||$count>6)throw new DomainException('В соответствиях и последовательности нужно 2–6 элементов.');
    if(count(array_unique($question['options']))!==$count)throw new DomainException('Элементы блока должны отличаться.');
    $correct=$question['correct'];$all=range(0,$count-1);$sorted=$correct;
    if(!is_array($correct))throw new DomainException('Укажите правильное соответствие или порядок всех элементов.');
    sort($sorted);
    if($sorted!==$all)throw new DomainException('Каждый элемент должен использоваться ровно один раз.');
    if($block==='matching'){
        $prompts=$question['prompts']??null;
        if(!is_array($prompts)||!array_is_list($prompts)||count($prompts)!==$count)throw new DomainException('Укажите левую часть каждой пары.');
        foreach($prompts as &$prompt){
            if(!is_string($prompt)||trim($prompt)===''||mb_strlen($prompt)>120)throw new DomainException('Левая часть пары должна содержать 1–120 символов.');
            $prompt=trim($prompt);
        }
        unset($prompt);$question['prompts']=$prompts;
    }
    // Keep author-entered pairs and order out of the public option order.
    $order=$all;shuffle($order);
    if($order===$correct)$order=[...array_slice($order,1),$order[0]];
    $question['options']=array_map(fn($index)=>$question['options'][$index],$order);
    $question['correct']=array_map(fn($index)=>array_search($index,$order,true),$correct);
    $question['multiple']=false;
    return $question;
}
function pulseQuestionAnswerText(array $question,array $choices): string {
    $parts=[];
    foreach($choices as $position=>$index){
        $text=$question['options'][$index]??'';
        if(($question['block']??'')==='matching')$text=($question['prompts'][$position]??($position+1)).' — '.$text;
        elseif(($question['block']??'')==='ordering')$text=($position+1).'. '.$text;
        $parts[]=$text;
    }
    return implode(pulseStructuredQuestion($question)?"\n":', ',$parts);
}
function pulseQuestionInstruction(array $question): string {
    if(($question['block']??'')==='matching'){
        $lines=[];foreach($question['prompts'] as $i=>$text)$lines[]=($i+1).'. '.$text;
        return "\n\n".implode("\n",$lines)."\n\nВыбирайте правые части по порядку строк. Повторное нажатие отменяет этот и последующие шаги. После всех пар подтвердите ответ.";
    }
    if(($question['block']??'')==='ordering')return "\n\nНажимайте события в нужном порядке, затем подтвердите ответ. Повторное нажатие отменяет этот и последующие шаги.";
    return '';
}
function pulseQuestionSelect(array $question,array $selected,int $option): array {
    $position=array_search($option,$selected,true);
    if(pulseStructuredQuestion($question))return $position===false?[...$selected,$option]:array_slice($selected,0,$position);
    if($position===false)$selected[]=$option;
    else $selected=array_values(array_diff($selected,[$option]));
    sort($selected);return $selected;
}
