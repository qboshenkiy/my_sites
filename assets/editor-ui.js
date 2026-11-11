let pulseEditorClosed = new Set();
let pulseEditorIssuesShown = false;
const pulseBlockDescriptions = {
 matching: 'Соединить персонажей, книги или события в пары',
 ordering: 'Расположить события от первого к последнему',
 missing_word: 'Выбрать слово, которое дополняет текст',
 scenario: 'Выбрать решение описанной ситуации',
 speaker: 'Узнать автора цитаты'
};
const pulseBlockIcons = {matching:'users',ordering:'logs',missing_word:'edit',scenario:'book',speaker:'user'};

function pulseEditorQuestionIssues(q,index){
 const issues=[];
 if(!q.text.trim())issues.push('Введите текст вопроса');
 if(q.options.some(option=>!option.trim()))issues.push(pulseStructuredQuestion(q)?'Заполните все элементы':'Заполните варианты ответа');
 if(q.block==='matching'&&q.prompts.some(prompt=>!prompt.trim()))issues.push('Заполните левую часть каждой пары');
 if(pulseStructuredQuestion(q)&&new Set(q.options.map(option=>option.trim())).size!==q.options.length)issues.push('Элементы должны отличаться');
 if(q.type==='quiz'&&!pulseStructuredQuestion(q)&&!correctIndexes(q).length)issues.push('Отметьте правильный ответ');
 if(!Number.isInteger(q.points)||q.points<1||q.points>10000)issues.push('Укажите баллы от 1 до 10000');
 if(draft.mode==='board'){
  if(!q.category.trim())issues.push('Укажите категорию');
  if(draft.questions.some((other,i)=>i!==index&&other.category.trim()===q.category.trim()&&other.points===q.points))issues.push('Измените баллы — такая ячейка уже есть');
 }
 return issues;
}

function pulseEditorRowActions(q,index,position){
 return `<div class="editor-row-actions">${pulseStructuredQuestion(q)?`<button type="button" class="icon-button editor-move-up" data-editor-option-move="${position}" data-index="${index}" data-offset="-1" ${position===0?'disabled':''} title="Строку выше" aria-label="Строку ${position+1} выше">${icon('back',14)}</button><button type="button" class="icon-button editor-move-down" data-editor-option-move="${position}" data-index="${index}" data-offset="1" ${position===q.options.length-1?'disabled':''} title="Строку ниже" aria-label="Строку ${position+1} ниже">${icon('back',14)}</button>`:''}<button type="button" class="icon-button danger" data-editor-option-remove="${position}" data-index="${index}" ${q.options.length<=2?'disabled':''} title="Убрать строку" aria-label="Удалить строку ${position+1}">${icon('close',14)}</button></div>`;
}

function pulseEditorQuestion(q,i){
 const block=q.block||'choice';
 const itemWord=block==='matching'?'пара':block==='ordering'?'событие':'вариант';
 return `<details class="question-editor panel editor-question-card" data-index="${i}" id="editor-question-${i}" ${pulseEditorClosed.has(i)?'':'open'}>
  <summary class="editor-question-summary">
   <span class="editor-question-number">${String(i+1).padStart(2,'0')}</span>
   <span class="editor-question-caption"><strong data-editor-caption>${esc(q.text||'Новый вопрос')}</strong><small>${esc(pulseBlockNames[block])} <span data-editor-card-status></span></small></span>
   <span class="editor-question-actions">
    <button type="button" class="icon-button editor-move-up" data-editor-action="move" data-index="${i}" data-offset="-1" ${i===0?'disabled':''} aria-label="Переместить вопрос ${i+1} выше" title="Выше">${icon('back',16)}</button>
    <button type="button" class="icon-button editor-move-down" data-editor-action="move" data-index="${i}" data-offset="1" ${i===draft.questions.length-1?'disabled':''} aria-label="Переместить вопрос ${i+1} ниже" title="Ниже">${icon('back',16)}</button>
    <button type="button" class="icon-button" data-editor-action="duplicate" data-index="${i}" ${draft.questions.length>=50?'disabled':''} aria-label="Копировать вопрос ${i+1}" title="Копировать">${icon('copy',16)}</button>
    <button type="button" class="icon-button danger" data-action="remove-question" data-index="${i}" ${draft.questions.length===1?'disabled':''} aria-label="Удалить вопрос ${i+1}" title="Удалить">${icon('close',16)}</button>
   </span><span class="editor-question-chevron">${icon('chevron-down',16)}</span>
  </summary>
  <div class="editor-question-body">
   <p class="editor-question-issues" data-editor-issues role="status" hidden></p>
   ${pulseBlockPicker(q,i)}
   <label class="editor-question-text">Текст вопроса <span data-editor-character-count>${q.text.length} / 250</span><textarea name="text-${i}" required maxlength="250" rows="3" placeholder="Сформулируйте вопрос или вставьте цитату">${esc(q.text)}</textarea></label>
   ${pulseBlockEditor(q,i)}
   <div class="question-editor-bottom"><small>${pulseStructuredQuestion(q)?'2–6 элементов. Варианты перемешиваются при прохождении.':q.type==='quiz'?'Отметьте ✓ у всех правильных вариантов.':'Опрос без правильного ответа и баллов.'}</small><span><button type="button" class="text-button" data-action="remove-option" data-index="${i}" ${q.options.length<=2?'disabled':''}>− ${block==='matching'?'Последняя пара':block==='ordering'?'Последнее событие':'Последний вариант'}</button><button type="button" class="text-button" data-action="add-option" data-index="${i}" ${q.options.length>=(pulseStructuredQuestion(q)?6:12)?'disabled':''}>＋ ${itemWord[0].toUpperCase()+itemWord.slice(1)}</button></span></div>
   <div class="editor-question-extras">
    <label>Местописание или пояснение <small>Участник увидит после завершения самостоятельного теста</small><textarea name="reference-${i}" rows="2" maxlength="200" placeholder="Например, Левит 23:5">${esc(q.reference)}</textarea></label>
    <details class="editor-media" ${q.image?'open':''}><summary>${icon('image',16)} Изображение ${q.image?'добавлено':'к вопросу'}</summary><div class="image-editor">${q.image?`<img src="api.php?action=image&id=${q.image}" alt="Иллюстрация к вопросу"><button type="button" class="text-button danger" data-action="remove-image" data-index="${i}">Убрать изображение</button>`:''}<label class="outline">Выбрать файл<input type="file" data-image-index="${i}" accept="image/png,image/jpeg,image/webp,image/gif"></label><small>PNG, JPEG, WebP, GIF · до 2 МБ</small></div></details>
   </div>
   <details class="editor-question-settings" ${draft.mode==='board'?'open':''}><summary>${icon('settings',16)} Параметры вопроса <span data-editor-parameter-summary>${q.points||1000} баллов · ${q.seconds} сек</span></summary><div class="question-config">
    <label ${(q.block||'choice')!=='choice'?'hidden':''}>Оценивание<select name="type-${i}"><option value="quiz" ${q.type==='quiz'?'selected':''}>С правильным ответом</option><option value="poll" ${q.type==='poll'?'selected':''}>Опрос без баллов</option></select></label>
    <label>Категория<input name="category-${i}" maxlength="60" value="${esc(q.category)}" ${draft.mode==='board'?'required':''} placeholder="Например, История"></label>
    <label>Баллы<input name="points-${i}" type="number" min="1" max="10000" required value="${q.points||1000}"></label>
    <label>Время в живой игре<select name="seconds-${i}" aria-label="Время ответа">${[...new Set([5,10,15,20,30,45,60,90,120,q.seconds])].sort((a,b)=>a-b).map(seconds=>`<option value="${seconds}" ${q.seconds===seconds?'selected':''}>${seconds} сек</option>`).join('')}</select></label>
   </div></details>
  </div>
 </details>`;
}

function pulseEditorContent(){
 return `<div class="editor-heading editor-page-heading"><div><button class="text-button" data-action="dashboard">${icon('back',16)} Мои опросники</button><h1>${draft.id?'Редактирование теста':'Новый тест'}<span>.</span></h1><p>Сформулируйте вопросы, укажите ответы и проверьте, как их увидят участники.</p></div><button type="button" class="outline" data-editor-action="preview">${icon('play',16)} Предпросмотр</button></div>
 <form id="editor-form" class="editor-workspace">
  <div class="editor-main">
   <section class="editor-details panel"><label>Название теста<input name="title" maxlength="100" required value="${esc(draft.title)}" placeholder="Например, Левит и Числа — итоги чтения"></label><label>Описание <small>Необязательно</small><input name="description" maxlength="300" value="${esc(draft.description)}" placeholder="Что нужно знать участнику перед началом"></label></section>
   <details class="panel mode-panel editor-global-settings" ${draft.mode==='board'?'open':''}><summary>${icon('settings',16)} Настройки игры <span>${draft.mode==='board'?'Категории и баллы':'Последовательная викторина'}</span>${icon('chevron-down',16)}</summary><div>
    <label>Формат игры<select name="mode"><option value="classic" ${draft.mode!=='board'?'selected':''}>Последовательная викторина</option><option value="board" ${draft.mode==='board'?'selected':''}>Категории и баллы · игровое поле</option><option value="bluff">Бредовуха · выдумки и правда</option><option value="author">Тайный автор · анонимные ответы</option></select></label>
    <label>Начисление баллов<select name="scoring"><option value="speed" ${draft.scoring!=='fixed'?'selected':''}>За правильность и скорость</option><option value="fixed" ${draft.scoring==='fixed'?'selected':''}>Полные баллы за правильный ответ</option></select></label>
    <p>Скорость и время учитываются в живой игре. В тесте по ссылке участник отвечает в своём темпе.</p>${draft.mode==='board'?'<button type="button" class="outline" data-action="add-category">＋ Категория с вопросами 10–50</button>':''}
   </div></details>
   <div class="editor-questions-heading"><h2>Вопросы <span data-editor-count>${draft.questions.length}</span></h2><button type="button" class="text-button" data-editor-action="collapse">Свернуть все</button><button type="button" class="text-button" data-editor-action="expand">Развернуть все</button></div>
   <div id="questions">${draft.questions.map(pulseEditorQuestion).join('')}</div>
   <section class="editor-add-section" id="editor-add-block"><h2>Добавить блок</h2><p>Выберите, что должен сделать участник.</p><div class="block-add-buttons editor-block-picker">${Object.entries(pulseBlockDescriptions).map(([kind,description])=>`<button type="button" class="outline" data-action="add-block" data-block="${kind}" ${draft.questions.length>=50?'disabled':''}>${icon(pulseBlockIcons[kind],20)}<span><strong>${esc(pulseBlockNames[kind])}</strong><small>${esc(description)}</small></span>${icon('plus',16)}</button>`).join('')}</div></section>
  </div>
  <aside class="editor-outline panel" aria-label="Структура теста"><details class="editor-outline-details" ${window.matchMedia('(max-width:760px)').matches?'':'open'}><summary class="editor-outline-heading"><h2>Структура теста</h2><span data-editor-outline-count>${draft.questions.length}</span>${icon('chevron-down',16)}</summary><p data-editor-overview></p><nav data-editor-outline aria-label="Переход к вопросу"></nav><button type="button" class="outline" data-editor-action="add-menu">${icon('plus',16)} Добавить блок</button><p class="editor-outline-hint">Локальный черновик сохраняется автоматически. Кнопка «Сохранить» записывает тест на сервер.</p></details></aside>
  <div class="editor-footer editor-save-bar"><div><strong data-editor-ready></strong>${editorDraftStatus()}</div><div><button type="button" class="outline" data-action="add-question" ${draft.questions.length>=50?'disabled':''}>${icon('plus',16)} Вопрос</button><button type="submit" class="primary">${icon('check',16)} Сохранить тест</button></div></div>
 </form>`;
}

function pulseRefreshEditorOverview(){
 const navigation=document.querySelector('[data-editor-outline]');
 if(!navigation)return;
 const issues=draft.questions.map(pulseEditorQuestionIssues);
 const ready=issues.filter(list=>!list.length).length;
 const points=draft.questions.reduce((total,q)=>total+(q.type==='quiz'?(q.points||0):0),0);
 navigation.innerHTML=draft.questions.map((q,i)=>`<button type="button" data-editor-go="${i}" aria-label="Вопрос ${i+1}. ${esc(q.text||'Новый вопрос')}"><span>${i+1}</span><span><strong>${esc(q.text||'Новый вопрос')}</strong><small>${esc(pulseBlockNames[q.block||'choice'])}</small></span><span class="editor-outline-status ${issues[i].length?'':'is-ready'}" title="${issues[i].length?'Нужно заполнить':'Готов'}">${icon(issues[i].length?'edit':'check',14)}</span></button>`).join('');
 document.querySelector('[data-editor-ready]').textContent=`Готово ${ready} из ${draft.questions.length}`;
 document.querySelector('[data-editor-overview]').textContent=`${draft.questions.length} вопросов · ${points.toLocaleString('ru-RU')} баллов`;
 for(const [i,q] of draft.questions.entries()){
  const card=document.querySelector(`.editor-question-card[data-index="${i}"]`);
  card.querySelector('[data-editor-caption]').textContent=q.text||'Новый вопрос';
  card.querySelector('[data-editor-character-count]').textContent=q.text.length+' / 250';
  card.querySelector('[data-editor-parameter-summary]').textContent=q.type==='poll'?'Опрос без баллов':q.points+' баллов · '+q.seconds+' сек';
  const status=card.querySelector('[data-editor-card-status]');
  status.textContent=issues[i].length?'· Нужно заполнить':'· Готов';
  status.classList.toggle('is-ready',!issues[i].length);
  const message=card.querySelector('[data-editor-issues]');
  message.hidden=!pulseEditorIssuesShown||!issues[i].length;
  message.textContent=issues[i].join('. ');
 }
}

function pulseEditorGo(index,solo=false){
 const card=document.querySelector(`.editor-question-card[data-index="${index}"]`);
 if(!card)return;
 if(solo){
  pulseEditorClosed=new Set(draft.questions.map((_,i)=>i).filter(i=>i!==index));
  for(const other of document.querySelectorAll('.editor-question-card'))other.open=other===card;
 }
 card.open=true;pulseEditorClosed.delete(index);
 card.scrollIntoView({behavior:'smooth',block:'start'});
}

function pulseEditorPreview(){
 captureDraft();saveEditorDraft();
 const quiz=structuredClone(draft);
 for(const q of quiz.questions){
  if(!pulseStructuredQuestion(q))continue;
  q.options=[...q.options.slice(1),q.options[0]];
  q.correct=correctIndexes(q).map(index=>(index+q.options.length-1)%q.options.length);
 }
 const dialog=document.createElement('dialog');dialog.className='editor-preview-dialog';
 dialog.innerHTML=`<div class="editor-preview-heading"><div><h2>Предпросмотр</h2><p>Пример самостоятельного теста</p></div><button type="button" class="outline" data-editor-preview-close>Закрыть</button></div><div class="editor-preview-tabs"><button type="button" class="outline" data-editor-preview="questions" aria-pressed="true">Вопросы</button><button type="button" class="outline" data-editor-preview="review" aria-pressed="false">Итоговый разбор</button></div><div class="self-test-page"><main data-editor-preview-body></main></div>`;
 function render(view){
  dialog.querySelector('[data-editor-preview-body]').innerHTML=`<section class="self-test-cover"><div class="eyebrow">${view==='review'?'ПРИМЕР РАЗБОРА С ПРАВИЛЬНЫМИ ОТВЕТАМИ':'КАК УВИДИТ УЧАСТНИК'}</div><h1>${esc(quiz.title||'Название теста')}</h1><p>${esc(quiz.description)}</p></section>`+quiz.questions.map((q,i)=>{
   if(view==='review'){
    const issues=pulseEditorQuestionIssues(q,i);
    if(issues.length)return `<section class="self-test-question"><h2>${esc(q.text||'Вопрос '+(i+1))}</h2><p>${esc(issues.join('. '))}</p></section>`;
    return formReviewQuestion(q,q.correct,i);
   }
   return `<section class="self-test-question"><span class="self-test-number">Вопрос ${i+1} · ${esc(pulseBlockNames[q.block||'choice'])}</span><h2>${esc(q.text||'Текст вопроса')}</h2>${q.image?`<img class="self-test-image" src="api.php?action=image&id=${q.image}" alt="Иллюстрация к вопросу">`:''}${pulseStructuredQuestion(q)?pulseStructuredInputs(q,'preview-'+i):`<div class="self-test-options">${q.options.map((text,j)=>`<label><input type="${multiCorrect(q)?'checkbox':'radio'}" name="preview-${i}" value="${j}"><span>${esc(text||'Вариант '+(j+1))}</span></label>`).join('')}</div>`}</section>`;
  }).join('');
  for(const tab of dialog.querySelectorAll('[data-editor-preview]'))tab.setAttribute('aria-pressed',String(tab.dataset.editorPreview===view));
 }
 dialog.addEventListener('click',event=>{
  if(event.target.closest('[data-editor-preview-close]'))dialog.close();
  const tab=event.target.closest('[data-editor-preview]');if(tab)render(tab.dataset.editorPreview);
 });
 dialog.onclose=()=>dialog.remove();document.body.append(dialog);render('questions');dialog.showModal();
}

document.addEventListener('click',event=>{
 const button=event.target.closest('[data-editor-action],[data-editor-go],[data-editor-option-remove],[data-editor-option-move]');
 if(!button||button.disabled)return;
 event.preventDefault();
 if(button.hasAttribute('data-editor-go'))return pulseEditorGo(Number(button.dataset.editorGo),true);
 const action=button.dataset.editorAction;
 if(action==='preview')return pulseEditorPreview();
 if(action==='add-menu')return document.querySelector('#editor-add-block').scrollIntoView({behavior:'smooth',block:'center'});
 if(action==='collapse'||action==='expand'){
  pulseEditorClosed=action==='collapse'?new Set(draft.questions.map((_,i)=>i)):new Set();
  for(const card of document.querySelectorAll('.editor-question-card'))card.open=action==='expand';
  return;
 }
 captureDraft();const index=Number(button.dataset.index),question=draft.questions[index];
 if(button.hasAttribute('data-editor-option-remove')){
  if(question.options.length<=2)return;
  const option=Number(button.dataset.editorOptionRemove);
  question.options.splice(option,1);if(question.block==='matching')question.prompts.splice(option,1);
  question.correct=pulseStructuredQuestion(question)?question.options.map((_,i)=>i):correctIndexes(question).filter(n=>n!==option).map(n=>n>option?n-1:n);
 }else if(button.hasAttribute('data-editor-option-move')){
  const position=Number(button.dataset.editorOptionMove),target=position+Number(button.dataset.offset);
  [question.options[position],question.options[target]]=[question.options[target],question.options[position]];
  if(question.block==='matching')[question.prompts[position],question.prompts[target]]=[question.prompts[target],question.prompts[position]];
 }else if(action==='duplicate'){
  if(draft.questions.length>=50)return toast('Максимум 50 вопросов.');
  const copy=structuredClone(question);
  if(draft.mode==='board'){
   const used=new Set(draft.questions.filter(q=>q.category===copy.category).map(q=>q.points));
   while(used.has(copy.points))copy.points=copy.points===10000?1:copy.points+1;
  }
  draft.questions.splice(index+1,0,copy);
  pulseEditorClosed=new Set([...pulseEditorClosed].map(n=>n>index?n+1:n));
 }else if(action==='move'){
  const target=index+Number(button.dataset.offset);
  if(target<0||target>=draft.questions.length)return;
  [draft.questions[index],draft.questions[target]]=[draft.questions[target],draft.questions[index]];
  pulseEditorClosed=new Set([...pulseEditorClosed].map(n=>n===index?target:n===target?index:n));
  drawEditor();return pulseEditorGo(target);
 }
 drawEditor();pulseEditorGo(action==='duplicate'?index+1:index,action==='duplicate');
});

document.addEventListener('click',event=>{
 const button=event.target.closest('.editor-question-summary button');
 if(button)event.preventDefault();
 if(button?.dataset.action==='remove-question'){
  const removed=Number(button.dataset.index);
  pulseEditorClosed=new Set([...pulseEditorClosed].filter(n=>n!==removed).map(n=>n>removed?n-1:n));
 }
},true);
document.addEventListener('toggle',event=>{
 const card=event.target;
 if(!card.isConnected||!card.matches('.editor-question-card'))return;
 const index=Number(card.dataset.index);
 if(card.open)pulseEditorClosed.delete(index);else pulseEditorClosed.add(index);
},true);
document.addEventListener('input',event=>{
 if(event.target.closest('#editor-form'))pulseRefreshEditorOverview();
});
document.addEventListener('change',event=>{
 if(event.target.closest('#editor-form'))pulseRefreshEditorOverview();
});
document.addEventListener('invalid',event=>{
 if(!event.target.closest('#editor-form'))return;
 for(let parent=event.target.parentElement;parent;parent=parent.parentElement)if(parent.tagName==='DETAILS')parent.open=true;
},true);
document.addEventListener('submit',event=>{
 if(event.target.id!=='editor-form'||event.target.dataset.bluff==='1')return;
 captureDraft();
 const first=draft.questions.findIndex((q,i)=>pulseEditorQuestionIssues(q,i).length);
 if(first<0)return;
 event.preventDefault();event.stopImmediatePropagation();
 pulseEditorIssuesShown=true;saveEditorDraft();pulseRefreshEditorOverview();pulseEditorGo(first);
 toast('Проверьте выделенный вопрос — под ним указано, что нужно заполнить.');
},true);

window.matchMedia('(max-width:760px)').addEventListener('change',event=>{
 const outline=document.querySelector('.editor-outline-details');
 if(outline)outline.open=!event.matches;
});
