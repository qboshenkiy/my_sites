const pulseBlockNames={choice:'Варианты ответа',matching:'Соответствия',ordering:'Последовательность',missing_word:'Пропущенное слово',scenario:'Разбор ситуации',speaker:'Кто это сказал?'};
const pulseStructuredQuestion=q=>['matching','ordering'].includes(q.block);
let pulseLiveBlockChoices=[];
function pulseBlockPicker(q,i){
 return `<label>Блок вопроса<select name="block-${i}" data-question-block="${i}">${Object.entries(pulseBlockNames).map(([key,label])=>`<option value="${key}" ${key===(q.block||'choice')?'selected':''}>${label}</option>`).join('')}</select></label>`;
}
function pulseNewBlock(kind){
 const q=defaultQuestion();q.block=kind;
 if(kind==='matching'){q.seconds=60;q.text='Установите соответствия';q.options=['','',''];q.prompts=['','',''];q.correct=[0,1,2];}
 if(kind==='ordering'){q.seconds=60;q.text='Расположите события по порядку';q.options=['','',''];q.correct=[0,1,2];}
 if(kind==='missing_word')q.text='Дополните текст: «… ___ …»';
 if(kind==='scenario')q.text='Как следует поступить в этой ситуации?';
 if(kind==='speaker')q.text='Кто сказал эти слова: «…»?';
 return q;
}
function pulseBlockEditor(q,i){
 if(pulseStructuredQuestion(q)){
  const right=correctIndexes(q);
  return `<div class="block-editor"><p>${q.block==='matching'?'Введите правильные пары. Участник получит перемешанную правую колонку.':'Введите события в правильном порядке. При прохождении они будут перемешаны.'}</p>${q.options.map((_,j)=>`<div class="block-editor-row"><span>${j+1}</span>${q.block==='matching'?`<label>Левая часть<input name="prompt-${i}-${j}" required maxlength="120" value="${esc(q.prompts?.[j]||'')}" placeholder="Персонаж, книга или событие"></label>`:''}<label>${q.block==='matching'?'Правая часть':'Событие'}<input name="block-option-${i}-${j}" required maxlength="120" value="${esc(q.options[right[j]]??q.options[j])}" placeholder="${q.block==='matching'?'Соответствующая пара':'Что произошло'}"></label>${pulseEditorRowActions(q,i,j)}</div>`).join('')}</div>`;
 }
 return `<div class="answer-editor">${q.options.map((o,j)=>`<div class="answer-edit option-${j%shapes.length}"><span>${j+1}</span><input name="option-${i}-${j}" required maxlength="120" value="${esc(o)}" placeholder="Вариант ${j+1}" aria-label="Вариант ${j+1}">${q.type==='quiz'?`<label class="correct-choice" title="Отметить правильный ответ" aria-label="Правильный вариант ${j+1}"><input type="checkbox" name="correct-${i}" value="${j}" ${correctIndexes(q).includes(j)?'checked':''}><span>✓</span></label>`:''}${pulseEditorRowActions(q,i,j)}</div>`).join('')}</div>`;
}
function pulseCaptureBlock(q,i,fd){
 const block=q.block||'choice';
 // Capture the currently rendered fields before switching the block picker.
 if(fd.has(`block-option-${i}-0`))return {block:q.block,type:'quiz',options:q.options.map((_,j)=>fd.get(`block-option-${i}-${j}`)||''),prompts:q.block==='matching'?q.options.map((_,j)=>fd.get(`prompt-${i}-${j}`)||''):undefined,correct:q.options.map((_,j)=>j),multiple:false};
 return {block:fd.get(`type-${i}`)==='poll'?'choice':block,options:q.options.map((_,j)=>fd.get(`option-${i}-${j}`)||''),correct:fd.get(`type-${i}`)==='quiz'?fd.getAll(`correct-${i}`).map(Number):null};
}
function pulseAnswerComplete(q,answer){
 if(!pulseStructuredQuestion(q))return answer!==null&&(!Array.isArray(answer)||answer.length>0);
 return Array.isArray(answer)&&answer.length===q.options.length&&answer.every(n=>Number.isInteger(n)&&n>=0&&n<q.options.length)&&new Set(answer).size===q.options.length;
}
function pulseFormAnswer(form,q,i){
 if(pulseStructuredQuestion(q))return [...form.querySelectorAll(`[data-block-question="${i}"] select`)].map(s=>s.value===''?null:Number(s.value));
 const selected=[...form.querySelectorAll(`[name="self-q-${i}"]:checked`)].map(x=>Number(x.value));
 return formMulti(q)?selected:(selected[0]??null);
}
function pulseStructuredInputs(q,key,selected=[],disabled=false){
 return `<fieldset class="structured-question" data-block-question="${key}" ${disabled?'disabled':''}><legend>${esc(pulseBlockNames[q.block])}</legend><p>${q.block==='matching'?'Выберите пару для каждой строки. Каждый вариант используется один раз.':'Выберите события от первого к последнему. Каждый вариант используется один раз.'}</p>${q.options.map((_,i)=>`<label><span>${q.block==='matching'?esc(q.prompts[i]):'Шаг '+(i+1)}</span><select name="block-${key}-${i}" required aria-label="${esc(q.block==='matching'?q.prompts[i]:'Событие '+(i+1))}"><option value="">Выберите вариант</option>${q.options.map((text,j)=>`<option value="${j}" ${selected[i]===j?'selected':''} ${selected.includes(j)&&selected[i]!==j?'disabled':''}>${esc(text)}</option>`).join('')}</select></label>`).join('')}</fieldset>`;
}
function pulseBlockAnswerText(q,choices){
 return choices.map((index,i)=>(q.block==='matching'?q.prompts[i]+' — ':q.block==='ordering'?(i+1)+'. ':'')+(q.options[index]||'')).join('\n');
}
function pulseBlockReview(q,answer,index,heading=true,own=true){
 const selected=Array.isArray(answer)?answer:[],right=correctIndexes(q),exact=JSON.stringify(selected)===JSON.stringify(right);
 return `<section class="self-test-question block-review">${heading?`<span class="self-test-number">Вопрос ${index+1} · ${esc(pulseBlockNames[q.block])}</span><h2>${esc(q.text)}</h2>`:''}<p class="self-test-verdict ${own?(exact?'is-correct':'is-incorrect'):''}">${own?(exact?'✓ Верно':selected.length?'✕ Неверно':'✕ Нет ответа'):'Правильный ответ'}</p>${right.map((expected,i)=>`<div class="self-test-review ${!own||selected[i]===expected?'correct':'incorrect'}"><div><strong>${q.block==='matching'?esc(q.prompts[i]):'Шаг '+(i+1)}</strong>${own?`<p>Ваш ответ — ${esc(q.options[selected[i]]??'Нет ответа')}</p>`:''}${!own||selected[i]!==expected?`<p>Правильный ответ — ${esc(q.options[expected])}</p>`:''}</div></div>`).join('')}${heading&&q.reference?`<p class="self-test-reference"><strong>Местописание / пояснение</strong><br>${esc(q.reference)}</p>`:''}</section>`;
}
function pulseLiveBlock(q,s,isHost,revealed,answered){
 if(revealed)return pulseBlockReview(q,s.answer?.choices||[],s.index,false,!isHost);
 return pulseStructuredInputs(q,'live',answered?s.answer.choices:pulseLiveBlockChoices,isHost||answered)+(!isHost&&!answered?`<button class="primary" data-action="submit-block-answer" ${pulseAnswerComplete(q,pulseLiveBlockChoices)?'':'disabled'}>Подтвердить ответ →</button>`:'');
}
document.addEventListener('change',event=>{
 const fieldset=event.target.closest('[data-block-question]');
 if(fieldset){
  const choices=[...fieldset.querySelectorAll('select')].map(s=>s.value===''?null:Number(s.value));
  for(const select of fieldset.querySelectorAll('select'))for(const option of select.options)option.disabled=option.value!==''&&option.value!==select.value&&choices.includes(Number(option.value));
  if(fieldset.dataset.blockQuestion==='live'){
   pulseLiveBlockChoices=choices;
   const submit=document.querySelector('[data-action="submit-block-answer"]');if(submit)submit.disabled=!pulseAnswerComplete(state.question,choices);
  }else updatePublicProgress();
 }
 const picker=event.target.closest('[data-question-block]');
 if(!picker)return;
 const index=Number(picker.dataset.questionBlock),kind=picker.value;
 captureDraft();const previous=draft.questions[index],next=pulseNewBlock(kind);
 if(previous.text&&previous.text!==pulseNewBlock(previous.block||'choice').text)next.text=previous.text;
 if(previous.options.some(option=>option.trim())){
  next.options=previous.options.slice(0,pulseStructuredQuestion(next)?6:12);
  next.correct=pulseStructuredQuestion(next)?next.options.map((_,i)=>i):0;
  if(kind==='matching')next.prompts=next.options.map((_,i)=>previous.prompts?.[i]||'');
  next.seconds=previous.seconds;
 }
 draft.questions[index]={...next,category:previous.category,points:previous.points,image:previous.image,reference:previous.reference};
 drawEditor();
});
