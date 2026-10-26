const communityStaff = () => ['admin','moderator'].includes(boot?.user?.role);
let assessmentData = [], directoryUsers = [], assessmentDraft = null;

const originalShell = shell;
shell = function(content, selected='quizzes') {
  originalShell(content,selected);
  const sidebar=document.querySelector('.sidebar');
  const nav=(action,title,active=false)=>`<button class="nav ${active?'active':''}" data-action="${action}">${title}</button>`;
  sidebar.querySelector('.nav-label').insertAdjacentHTML('afterend',nav('catalog','◎ Общий каталог',page==='catalog'));
  sidebar.querySelector('.sidebar-tip').insertAdjacentHTML('beforebegin',nav('results','✓ Мои результаты',page==='results')+(communityStaff()?nav('assessments','▤ Ведомости тестов',['assessments','assessment-editor'].includes(page))+nav('participants','♙ Участники',page==='participants'):''));
  const account=sidebar.querySelector('.account');
  account.innerHTML=boot.user?`<span class="avatar">${esc(boot.user.name.slice(0,1))}</span><div>${esc(boot.user.name)}<small>${esc({admin:'Администратор',moderator:'Модератор',participant:'Участник'}[boot.user.role])}</small></div><button class="icon-button" title="Выйти" data-action="logout">↪</button>`:'<button class="primary" data-action="account">Войти в аккаунт</button>';
  if(!boot.user) sidebar.querySelectorAll('[data-action="dashboard"],[data-action="sessions"],[data-action="results"]').forEach(b=>b.hidden=true);
  const heading=document.querySelector('.topbar>span');
  heading.textContent=({catalog:'Общий каталог',results:'Мои результаты',assessments:'Ведомости тестов','assessment-editor':'Ведомость теста',participants:'Участники'})[page]||heading.textContent;
  sidebar.querySelector('.workspace small').textContent='Создавайте и играйте вместе';
};
const originalDashboard=dashboard;
const originalJoinPage=joinPage;
joinPage=function(){
  originalJoinPage();
  if(boot.user){const name=document.querySelector('#join-form [name=name]');name.maxLength=80;name.value=boot.user.name;name.readOnly=true;document.querySelector('.join-note').textContent='Игра сохранится в вашем профиле.';}
};
dashboard=async function(tab='quizzes') {
  if(!boot.user)return communityAuth();
  return originalDashboard(tab);
};
const originalCard=card;
card=function(q,i) {
  let html=originalCard(q,i);
  html=html.replace('<div class="card-meta">',`<div class="visibility-badge">${q.visibility==='public'?'◎ Опубликован в каталоге':'♧ Личный · виден только вам'}</div><div class="card-meta">`);
  return html.replace('</div></div></article>',`<button class="icon-button" data-action="visibility" data-id="${esc(q.id)}" title="${q.visibility==='public'?'Сделать личным':'Опубликовать'}">${q.visibility==='public'?'♧':'◎'}</button></div></div></article>`);
};
async function catalogPage(){
  stopPoll();page='catalog';const data=await api('catalog');
  shell(`<div class="page-heading"><div class="eyebrow">ИГРАТЬ И СОЗДАВАТЬ ВМЕСТЕ</div><h1>Общий каталог<span>.</span></h1><p>Опросы, которыми поделились авторы. Ваши личные опросы остаются только у вас.</p><button class="primary" data-action="${boot.user?'new':'account'}">＋ Создать свой опрос</button> <button class="outline" data-action="join-page">Войти по коду</button></div><div class="quiz-grid">${data.quizzes.map((q,i)=>`<article class="quiz-card"><div class="card-cover ${['purple','green','orange','blue'][i%4]}"><span class="cover-label">${esc({classic:'ВИКТОРИНА',board:'КАТЕГОРИИ И БАЛЛЫ',bluff:'БРЕДОВУХА'}[q.mode]||'ОПРОС')}</span><div class="cover-shapes"><span>✦</span></div><span class="question-tag">Вопросов: ${q.count}</span></div><div class="card-body"><h3>${esc(q.title)}</h3><p>${esc(q.description)}</p><small>Автор: ${esc(q.author||'Команда Пульса')}</small><div class="card-actions"><button class="primary" data-action="public-launch" data-id="${q.id}">▷ Играть</button><button class="outline" data-action="clone-quiz" data-id="${q.id}">Скопировать себе</button></div></div></article>`).join('')||'<div class="panel"><h2>Здесь появятся опубликованные опросы</h2><p>Создайте опрос и нажмите ◎ на его карточке, чтобы поделиться им.</p></div>'}</div>`,'catalog');
}
function communityAuth(register=false){
  stopPoll();page='account';
  app.innerHTML=`<div class="public-page"><header>${brand()}<button class="outline" data-action="catalog">Каталог ↗</button></header><main class="join-main"><div class="auth-symbol">ϟ</div><h1>${register?'Ваш Пульс':'С возвращением'}<span>.</span></h1><p>Создавайте свои опросы, играйте и следите за результатами.</p>${boot.marathon?'<button class="primary marathon-login" data-action="marathon-login">Войти через марафон чтения →</button><p>Тот же аккаунт, что и в марафоне. Новый пароль не нужен.</p><hr>':''}<form id="account-form" class="join-form" data-register="${register?'1':'0'}">${register?'<label>Ваше имя<input name="name" maxlength="80" required autocomplete="name"></label>':''}<label>Логин<input name="login" required minlength="3" maxlength="40" autocomplete="username" pattern="[a-zA-Z0-9_.\-]{3,40}"></label><label>Пароль<input type="password" name="password" required minlength="8" maxlength="200" autocomplete="${register?'new-password':'current-password'}"></label><button class="primary" type="submit">${register?'Создать аккаунт':'Войти'}</button></form><button class="text-button" data-action="${register?'account':'register-page'}">${register?'У меня уже есть аккаунт':'Создать отдельный аккаунт Пульса'}</button><p><button class="text-button" data-action="legacy-login">Вход по прежнему паролю администратора</button></p></main></div>`;
}
async function resultsPage(staff=false){
  if(!boot.user)return communityAuth();stopPoll();page=staff?'assessments':'results';
  assessmentData=(await api('assessments'));
  const data=assessmentData.assessments;
  shell(`<div class="page-heading"><div class="eyebrow">ОТ 0 ДО 100%</div><h1>${staff?'Ведомости тестов':'Мои результаты'}<span>.</span></h1><p>${staff?'Внесите баллы каждого участника — процент рассчитается автоматически.':'Ваши результаты тестов и прошедших игр.'}</p>${staff?'<button class="primary" data-action="new-assessment">＋ Внести прошедший тест</button>':''}</div><div class="assessment-list">${data.map(a=>`<section class="panel"><div class="section-heading"><div><h2>${esc(a.title)}</h2>${a.source_room_id?'<span class="report-pill is-done">Из прошедшей игры</span>':''}<p>${esc(a.held_on)} · максимум ${a.max_points} баллов</p></div>${staff?`<div>${a.source_room_id?(a.can_link?`<button class="outline" data-action="link-participants" data-id="${a.source_room_id}">Игроки и ведомость</button>`:''):`<button class="outline" data-action="edit-assessment" data-id="${a.id}">Изменить</button>`} <button class="outline" data-action="export-assessment" data-id="${a.id}">↓ CSV</button> <button class="text-button danger" data-action="delete-assessment" data-id="${a.id}">Удалить</button></div>`:''}</div>${a.scores.length?`<div class="table-scroll"><table class="community-table"><thead><tr><th>Участник</th><th>Баллы</th><th>Результат</th><th>Примечание</th></tr></thead><tbody>${a.scores.map(s=>`<tr><td>${esc(s.name)}</td><td>${s.points} / ${a.max_points}</td><td><strong class="percent-result">${s.percent.toLocaleString('ru-RU')}%</strong><progress max="100" value="${s.percent}" aria-label="Результат ${s.percent}%"></progress></td><td>${esc(s.note)}</td></tr>`).join('')}</tbody></table></div>`:'<p>Результаты ещё не внесены.</p>'}</section>`).join('')||'<div class="panel">Пока нет результатов тестов.</div>'}</div>${!staff?`<h2>Мои игры</h2><div class="sessions">${assessmentData.games.map(g=>`<div class="session-row"><div><strong>${esc(g.title)}</strong><small>${new Date(g.created_at*1000).toLocaleDateString('ru-RU')}</small></div><span>${g.score} баллов</span><span class="badge">${g.status==='finished'?'Завершена':'Идёт игра'}</span></div>`).join('')||'<p>Играйте после входа в аккаунт — результаты сохранятся здесь.</p>'}</div>`:''}`,staff?'assessments':'results');
}
async function participantsPage(){
  stopPoll();page='participants';directoryUsers=(await api('directory')).users;
  shell(`<div class="page-heading"><div class="eyebrow">ОБЩИЕ АККАУНТЫ</div><h1>Участники<span>.</span></h1><p>Подключённые аккаунты марафона и отдельные аккаунты Пульса.</p>${boot.marathon?'<button class="primary" data-action="sync-marathon">↻ Обновить список из марафона</button>':'<div class="panel">Для подключения общего списка откройте GitDeck → Пульс → «Подключить марафон». Сначала обновите оба сайта.</div>'}</div><div class="table-scroll panel"><table class="community-table"><thead><tr><th>Имя</th><th>Роль</th><th>Источник</th><th>Статус</th></tr></thead><tbody>${directoryUsers.map(u=>`<tr><td>${esc(u.name)}</td><td>${esc({admin:'Администратор',moderator:'Модератор',participant:'Участник'}[u.role])}</td><td>${u.issuer?'Марафон':'Пульс'}</td><td>${Number(u.active)?'Активен':'Неактивен'}</td></tr>`).join('')}</tbody></table></div>`,'participants');
}
async function assessmentEditor(id){
  directoryUsers=(await api('directory')).users;
  assessmentDraft=id?assessmentData.assessments.find(a=>a.id===id):{title:'',max_points:1000,held_on:new Date().toLocaleDateString('en-CA'),scores:[]};
  const a=assessmentDraft;page='assessment-editor';
  shell(`<div class="page-heading"><button class="text-button" data-action="assessments">← Ведомости</button><h1>${a.id?'Изменить результаты':'Прошедший тест'}<span>.</span></h1><p>Пусто — не внесено. Ноль — участник получил 0 баллов.</p></div><form id="assessment-form"><div class="panel assessment-details"><label>Название теста<input name="title" maxlength="100" value="${esc(a.title)}" required placeholder="Например, Бытие · итоговый тест"></label><label>Дата теста<input name="held_on" type="date" value="${esc(a.held_on)}" required></label><label>Максимум баллов<input name="max_points" id="max-points" type="number" min="0.01" max="100000000" step="any" value="${a.max_points}" required></label></div><div class="panel"><label>Найти участника<input id="grade-search" type="search" placeholder="Имя участника"></label><div class="table-scroll"><table class="community-table grade-table"><thead><tr><th>Участник</th><th>Баллы</th><th>%</th><th>Примечание</th></tr></thead><tbody>${directoryUsers.filter(u=>Number(u.active)||a.scores.some(s=>s.user_id===u.id)).map(u=>{const s=a.scores.find(s=>s.user_id===u.id);return `<tr data-grade-user="${u.id}" data-name="${esc(u.name.toLocaleLowerCase())}"><td>${esc(u.name)}</td><td><input data-points type="number" min="0" step="any" max="${a.max_points}" value="${s?s.points:''}" inputmode="decimal" aria-label="Баллы: ${esc(u.name)}"></td><td><output>${s?Number((s.points/a.max_points*100).toFixed(2))+'%':'—'}</output></td><td><input data-note maxlength="500" value="${esc(s?.note||'')}" aria-label="Примечание: ${esc(u.name)}"></td></tr>`;}).join('')}</tbody></table></div></div><div class="editor-footer"><button class="outline" type="button" data-action="assessments">Отмена</button><button class="primary" type="submit">✓ Сохранить результаты</button></div></form>`,'assessments');
}
function exportAssessment(a){
  const cell=value=>{let s=String(value??'');if(/^[=+@\-\t\r]/.test(s))s="'"+s;return '"'+s.replaceAll('"','""')+'"';};
  const rows=[['Тест','Дата','Участник','Баллы','Максимум','Процент','Примечание'],...a.scores.map(s=>[a.title,a.held_on,s.name,s.points,a.max_points,s.percent,s.note])];
  const href=URL.createObjectURL(new Blob(['\ufeff'+rows.map(r=>r.map(cell).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
  const link=document.createElement('a');link.href=href;link.download='pulse-results-'+a.held_on+'.csv';link.click();setTimeout(()=>URL.revokeObjectURL(href),1000);
}
const originalCommunitySessions=dashboard;
dashboard=async function(tab='quizzes'){
  await originalCommunitySessions(tab);
  if(tab==='sessions'&&communityStaff())document.querySelectorAll('.session-row[data-id]').forEach(row=>{
    const wrapper=document.createElement('div');wrapper.className='session-with-link';row.replaceWith(wrapper);wrapper.append(row);
    const b=document.createElement('button');b.className='outline small';b.textContent='Связать участников';b.dataset.action='link-participants';b.dataset.id=row.dataset.id;wrapper.append(b);
  });
};
async function linkParticipants(room){
  directoryUsers=(await api('directory')).users;const data=await api('room_participants&room='+encodeURIComponent(room));
  const dialog=document.createElement('dialog');dialog.className='link-participants';
  dialog.innerHTML=`<h2>Связать прежние результаты</h2><p>Выберите аккаунт для игрового имени. Баллы и ответы сохранятся. Совпадение имени само по себе не подтверждает личность.</p>${data.players.map(p=>`<form data-player-link="${p.id}"><label>${esc(p.name)} · ${p.score} баллов<select name="user_id" required><option value="">Выберите аккаунт</option>${directoryUsers.map(u=>`<option value="${u.id}" ${p.user_id===u.id?'selected':''}>${esc(u.name)} · ${u.issuer?'марафон':'Пульс'} · ${esc(u.id.slice(-5))}</option>`).join('')}</select></label><button class="outline" type="submit">Сохранить</button></form>`).join('')}<button class="primary" type="button" id="close-links">Готово</button>`;
  document.body.append(dialog);dialog.onclose=()=>dialog.remove();dialog.querySelector('#close-links').onclick=()=>dialog.close();dialog.showModal();
}
document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-action]');if(!b)return;const action=b.dataset.action,id=b.dataset.id;
  if(!['catalog','account','register-page','legacy-login','marathon-login','public-launch','clone-quiz','visibility','results','assessments','participants','sync-marathon','new-assessment','edit-assessment','delete-assessment','export-assessment','link-participants'].includes(action))return;
  event.preventDefault();event.stopImmediatePropagation();if(b.disabled)return;b.disabled=true;
  try{
    if(action==='catalog')await catalogPage();
    if(action==='account')communityAuth();
    if(action==='register-page')communityAuth(true);
    if(action==='legacy-login')authPage();
    if(action==='marathon-login')location.assign((await api('marathon_begin',{})).url);
    if(action==='public-launch'){if(!boot.user)return communityAuth();await hostRoom((await api('create_room',{id})).id);}
    if(action==='clone-quiz'){if(!boot.user)return communityAuth();await api('clone_quiz',{id});await dashboard();toast('Личная копия добавлена в ваши опросы.');}
    if(action==='visibility'){
      const q=library.find(q=>q.id===id),visibility=q.visibility==='public'?'private':'public';
      confirmDialog(visibility==='public'?'Опубликовать опрос?':'Сделать опрос личным?',visibility==='public'?'Другие участники смогут запускать этот опрос и создавать свои копии.':'Опрос исчезнет из каталога. Уже созданные копии и игры сохранятся.',async()=>{await api('publish',{id,visibility});await dashboard();});
    }
    if(action==='results')await resultsPage();
    if(action==='assessments')await resultsPage(true);
    if(action==='participants')await participantsPage();
    if(action==='sync-marathon'){const r=await api('sync_marathon',{});toast(`Обновлено аккаунтов: ${r.imported}`);await participantsPage();}
    if(action==='new-assessment')await assessmentEditor();
    if(action==='edit-assessment')await assessmentEditor(id);
    if(action==='delete-assessment'){const a=assessmentData.assessments.find(a=>a.id===id);confirmDialog('Удалить ведомость?',`Будут удалены внесённые результаты теста «${a.title}».`,async()=>{await api('delete_assessment',{id,revision:a.revision});await resultsPage(true);});}
    if(action==='export-assessment')exportAssessment(assessmentData.assessments.find(a=>a.id===id));
    if(action==='link-participants')await linkParticipants(id);
  }catch(error){toast(error.message);}finally{b.disabled=false;}
},true);
document.addEventListener('submit',async event=>{
  const form=event.target;if(!['account-form','assessment-form'].includes(form.id)&&!form.dataset.playerLink)return;
  event.preventDefault();event.stopImmediatePropagation();const b=form.querySelector('[type="submit"]');if(b.disabled)return;b.disabled=true;
  try{
    const values=Object.fromEntries(new FormData(form));
    if(form.id==='account-form'){await api(form.dataset.register==='1'?'register':'account_login',values);boot=await api('bootstrap');await dashboard();}
    if(form.id==='assessment-form'){
      const scores=[...form.querySelectorAll('[data-grade-user]')].filter(row=>row.querySelector('[data-points]').value!=='').map(row=>({user_id:row.dataset.gradeUser,points:Number(row.querySelector('[data-points]').value),note:row.querySelector('[data-note]').value}));
      await api('save_assessment',{...values,id:assessmentDraft.id,revision:assessmentDraft.revision,scores});toast('Результаты сохранены.');await resultsPage(true);
    }
    if(form.dataset.playerLink){await api('link_player',{player_id:form.dataset.playerLink,user_id:values.user_id});toast('Аккаунт связан. Результаты сохранены.');}
  }catch(error){toast(error.message);}finally{b.disabled=false;}
},true);
document.addEventListener('input',event=>{
  if(event.target.id==='grade-search')document.querySelectorAll('[data-grade-user]').forEach(row=>row.hidden=!row.dataset.name.includes(event.target.value.toLocaleLowerCase()));
  if(event.target.matches('[data-points],#max-points')){
    const max=Number(document.querySelector('#max-points').value);
    document.querySelectorAll('[data-grade-user]').forEach(row=>{const input=row.querySelector('[data-points]');input.max=max;row.querySelector('output').textContent=input.value!==''&&max>0?(Number((Number(input.value)/max*100).toFixed(2))+'%'):'—';});
  }
});
async function communityInit(){
  const params=new URL(location.href).searchParams;
  if(params.has('marathon_code')){
    const payload={code:params.get('marathon_code'),state:params.get('marathon_state')};history.replaceState(null,'',location.pathname);
    try{await api('marathon_complete',payload);boot=await api('bootstrap');await dashboard();}catch(error){communityAuth();toast(error.message);}return;
  }
  if(!boot.user)await catalogPage();else await dashboard();
}

const communityAuthWithoutTelegram=communityAuth;
communityAuth=function(register=false){
  communityAuthWithoutTelegram(register);
  if(!boot.telegram?.configured)return;
  const area=document.createElement('div');area.className='pulse-telegram-login';
  area.innerHTML='<button type="button" class="primary marathon-login">➤ Войти через Telegram</button><p>Отдельный бот Пульса. Используйте Telegram, уже привязанный в марафоне.</p>';
  document.querySelector('#account-form').before(area);area.querySelector('button').onclick=pulseTelegramLogin;
};
async function pulseTelegramLogin(){
  try{
    boot=await api('bootstrap');
    const initData=window.Telegram?.WebApp?.initData;
    if(initData){await api('pulse_miniapp_login',{initData});boot=await api('bootstrap');await dashboard();return;}
    const request=await api('pulse_telegram_request',{});const dialog=document.createElement('dialog');
    dialog.innerHTML=`<h2>Вход через бота Пульса</h2><p>Откройте отдельного бота Пульса и нажмите «Подтвердить вход». После подтверждения здесь откроется ваш аккаунт марафона.</p><a class="primary" href="${esc(request.url)}" target="_blank" rel="noopener noreferrer">Открыть Telegram ↗</a><p class="pulse-telegram-status" role="status">Ждём подтверждения · 10 минут</p><button class="outline" type="button">Отмена</button>`;
    document.body.append(dialog);let timer;
    dialog.onclose=()=>{clearTimeout(timer);dialog.remove();};dialog.querySelector('button').onclick=()=>dialog.close();dialog.showModal();
    async function check(){
      if(!dialog.open)return;
      try{const result=await api('pulse_telegram_status',{token:request.token});if(result.ok){dialog.close();boot=await api('bootstrap');await dashboard();return;}timer=setTimeout(check,2000);}
      catch(error){if(dialog.open)dialog.querySelector('.pulse-telegram-status').textContent=error.message;}
    }
    timer=setTimeout(check,1000);
  }catch(error){toast(error.message);}
}
