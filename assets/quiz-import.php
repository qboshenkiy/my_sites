<?php
declare(strict_types=1);
if(realpath($_SERVER['SCRIPT_FILENAME']??'')===__FILE__){http_response_code(404);exit;}
function importQuizText(mixed $v,int $max,string $where,bool $required=true): string {
    if(!is_string($v))throw new DomainException($where.': ожидается текст.');$v=trim($v);
    if(($required&&$v==='')||mb_strlen($v)>$max)throw new DomainException($where.': '.($required?'заполните текст, ':'').'максимум '.$max.' символов.');return $v;
}
function importQuizNumber(mixed $v,int $min,int $max,string $where): int {
    if(is_bool($v)||(!is_int($v)&&!is_string($v))||filter_var($v,FILTER_VALIDATE_INT)===false||(int)$v<$min||(int)$v>$max)throw new DomainException($where.': целое число от '.$min.' до '.$max.'.');return (int)$v;
}
function normalizeQuizImport(string $json,array $settings=[]): array {
    if(strlen($json)>10000000)throw new DomainException('JSON: максимум 10 МБ.');
    $json=trim(preg_replace('/^\xEF\xBB\xBF/','',$json));
    if(preg_match('/^```(?:json)?\s*\n(.*)\n```$/is',$json,$fence))$json=$fence[1];
    try{$source=json_decode($json,true,64,JSON_THROW_ON_ERROR);}catch(JsonException $e){throw new DomainException('Неверный или неполный JSON. Проверьте кавычки, запятые и закрывающие скобки; текст мог оборваться.');}
    if(!is_array($source)||array_is_list($source))throw new DomainException('Нужен JSON-объект с title и categories или questions.');
    $title=importQuizText($source['title']??'',100,'Название');
    $hasCategories=array_key_exists('categories',$source);
    if($hasCategories&&array_key_exists('questions',$source))throw new DomainException('Укажите либо categories, либо questions, чтобы не потерять часть вопросов.');
    $mode=$settings['mode']??($source['mode']??($hasCategories?'board':'classic'));if($mode==='auto')$mode=$source['mode']??($hasCategories?'board':'classic');
    $scoring=in_array($mode,['board','bluff'],true)?'fixed':($source['scoring']??'speed');
    if(!in_array($mode,['board','classic','bluff'],true)||!in_array($scoring,['speed','fixed'],true))throw new DomainException('Неизвестный режим или способ начисления баллов.');
    $seconds=importQuizNumber($settings['seconds']??($source['seconds']??20),5,120,'Время по умолчанию');
    $step=importQuizNumber($settings['pointStep']??10,1,10000,'Шаг баллов');
    $metadata=[];foreach(['translation','testament','book'] as $key)if(isset($source[$key]))$metadata[]=importQuizText($source[$key],100,'Поле '.$key);
    $description=importQuizText($source['description']??implode(' · ',$metadata),300,'Описание',false);
    $groups=$hasCategories?$source['categories']:[['title'=>'Вопросы','questions'=>$source['questions']??null]];
    if(!is_array($groups)||!array_is_list($groups)||!$groups||count($groups)>50)throw new DomainException('Нужно от 1 до 50 категорий, каждая с questions.');
    $valid=[];$summary=[];$cells=[];$warnings=[];$generatedPoints=false;$hasImages=false;
    foreach($groups as $gi=>$group){
        $label='Категория '.($gi+1);if(!is_array($group))throw new DomainException($label.': нужен объект.');
        $category=importQuizText($group['title']??'',60,$label);
        $questions=$group['questions']??null;if(!is_array($questions)||!array_is_list($questions)||!$questions)throw new DomainException($label.': добавьте массив questions с вопросами.');
        $summary[]=['title'=>$category,'count'=>count($questions),'points'=>[]];
        foreach($questions as $qi=>$q){$where=$category.', вопрос '.($qi+1);if(!is_array($q))throw new DomainException($where.': нужен объект.');if(count($valid)>=50)throw new DomainException('Максимум 50 вопросов в одной викторине.');
            $text=importQuizText($q['question']??$q['text']??'',250,$where);
            if($mode==='bluff'&&array_key_exists('truth',$q)){
                $truth=importQuizText($q['truth'],120,$where.', правильный ответ');$aliases=$q['aliases']??[];
                if(!is_array($aliases)||!array_is_list($aliases)||count($aliases)>10)throw new DomainException($where.': aliases — массив до 10 написаний.');
                $aliases=array_map(fn($v)=>importQuizText($v,120,$where.', написание ответа'),$aliases);
                $cat=$hasCategories?$category:importQuizText($q['category']??'Вопросы',60,$where.', категория');
                $valid[]=['text'=>$text,'type'=>'quiz','seconds'=>importQuizNumber($q['seconds']??$seconds,5,120,$where.', время'),'options'=>[],'correct'=>null,'category'=>$cat,'points'=>1000,'truth'=>$truth,'aliases'=>$aliases,'image'=>null,'reference'=>importQuizText($q['reference']??'',200,$where.', reference',false)];
                $summary[$gi]['points'][]=1000;if(!empty($q['image']))$hasImages=true;continue;
            }
            $type=$q['type']??'quiz';if(!in_array($type,['quiz','poll'],true))throw new DomainException($where.': тип quiz или poll.');
            $options=$q['options']??null;if(!is_array($options)||!array_is_list($options)||count($options)<2||count($options)>4)throw new DomainException($where.': нужно 2–4 варианта ответа.');
            $texts=[];$ids=[];$marked=[];$hasFlags=false;
            foreach($options as $oi=>$option){
                $object=is_array($option);$texts[]=importQuizText($object?($option['text']??''):$option,120,$where.', вариант '.($oi+1));
                if($object&&isset($option['id'])){if(!is_string($option['id'])&&!is_int($option['id']))throw new DomainException($where.': id варианта должен быть строкой или числом.');$id=(string)$option['id'];if(isset($ids[$id]))throw new DomainException($where.': id вариантов должны быть уникальны.');$ids[$id]=$oi;}
                if($object&&array_key_exists('isCorrect',$option)){$hasFlags=true;if(!is_bool($option['isCorrect']))throw new DomainException($where.': isCorrect должен быть true или false.');if($option['isCorrect'])$marked[]=$oi;}
            }
            $correct=null;
            if($type==='quiz'){
                if(array_key_exists('correct',$q))$correct=importQuizNumber($q['correct'],0,count($options)-1,$where.', correct (нумерация с 0)');
                if(array_key_exists('correctAnswer',$q)){
                    $answer=$q['correctAnswer'];if(!is_string($answer)&&!is_int($answer))throw new DomainException($where.': correctAnswer должен указывать id или текст варианта.');
                    $key=(string)$answer;$found=$ids[$key]??null;
                    if($found===null&&!$ids&&is_string($answer)&&preg_match('/^[a-d]$/i',$answer))$found=ord(strtolower($answer))-97;
                    if($found===null){$matches=array_keys($texts,$key,true);if(count($matches)===1)$found=$matches[0];}
                    if($found===null||$found>=count($options))throw new DomainException($where.': correctAnswer не совпадает ни с одним вариантом.');
                    if($correct!==null&&$correct!==$found)throw new DomainException($where.': correct и correctAnswer противоречат друг другу.');$correct=$found;
                }
                if($hasFlags){if(count($marked)!==1)throw new DomainException($where.': нужен ровно один isCorrect: true.');if($correct!==null&&$correct!==$marked[0])throw new DomainException($where.': correctAnswer и isCorrect противоречат друг другу.');$correct=$marked[0];}
                if($correct===null)throw new DomainException($where.': укажите correctAnswer или isCorrect: true.');
            }
            $cat=$hasCategories?$category:importQuizText($q['category']??(in_array($mode,['board','bluff'],true)?'Вопросы':''),60,$where.', категория',in_array($mode,['board','bluff'],true));
            $points=isset($q['points'])?importQuizNumber($q['points'],1,10000,$where.', баллы'):($mode==='board'?($qi+1)*$step:1000);
            if(!isset($q['points'])&&$mode==='board')$generatedPoints=true;
            if($points>10000)throw new DomainException($where.': автоматические баллы превышают 10000, уменьшите шаг.');
            if($mode==='board'){$cell=$cat.'|'.$points;if(isset($cells[$cell]))throw new DomainException($where.': повторяется ячейка «'.$cat.' / '.$points.'». Укажите уникальные points.');$cells[$cell]=true;}
            $reference=importQuizText($q['reference']??'',200,$where.', reference',false);
            $time=importQuizNumber($q['seconds']??$seconds,5,120,$where.', время');
            if(!empty($q['image']))$hasImages=true;
            $valid[]=['text'=>$text,'type'=>$type,'seconds'=>$time,'options'=>$texts,'correct'=>$correct,'category'=>$cat,'points'=>$points,'image'=>null,'reference'=>$reference];
            if($mode==='bluff'){if($type!=='quiz')throw new DomainException($where.': Бредовухе нужен правильный ответ, тип poll не подходит.');$last=count($valid)-1;$valid[$last]['truth']=$texts[$correct];$valid[$last]['aliases']=[];$valid[$last]['options']=[];$valid[$last]['correct']=null;$valid[$last]['points']=1000;}
            $summary[$gi]['points'][]=$mode==='bluff'?1000:$points;
        }
    }
    if($mode==='bluff')$warnings[]='Бредовуха: игроки придумывают варианты сами. За правду — 1000, за обман — 500 баллов за голос. Категорию выбирают по очереди.';
    if(!$hasCategories){$byCategory=[];foreach($valid as $q){$cat=$q['category']?:'Вопросы';if(!isset($byCategory[$cat]))$byCategory[$cat]=['title'=>$cat,'count'=>0,'points'=>[]];$byCategory[$cat]['count']++;$byCategory[$cat]['points'][]=$q['points'];}$summary=array_values($byCategory);}
    if(isset($source['totalQuestions'])&&(string)$source['totalQuestions']!==(string)count($valid))$warnings[]='В totalQuestions указано '.(is_scalar($source['totalQuestions'])?(string)$source['totalQuestions']:'неверное значение').', в JSON найдено '.count($valid).' вопросов. Будут импортированы все найденные вопросы.';
    if($generatedPoints)$warnings[]='Для вопросов без points баллы назначены автоматически: '.$step.', '.($step*2).' и далее внутри каждой категории.';
    if($hasImages)$warnings[]='Изображения из JSON не загружаются. Добавьте их файлами в редакторе.';
    return ['quiz'=>['title'=>$title,'description'=>$description,'mode'=>$mode,'scoring'=>$scoring,'questions'=>$valid],'summary'=>['count'=>count($valid),'categories'=>$summary],'warnings'=>$warnings];
}
