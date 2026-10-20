let roomReportData=null,roomReportLinks={},roomReportDirty=false;
const reportNumber=n=>Number(n).toLocaleString('ru-RU',{maximumFractionDigits:2});
const reportDate=stamp=>new Date(stamp*1000).toLocaleDateString('ru-RU',{day:'numeric',month:'long',year:'numeric'});
const reportDashboard=dashboard;
function reportMobileNavigation(){
  const sidebar=document.querySelector('.sidebar');sidebar.classList.add('report-navigation');
  const button=document.createElement('button');button.className='outline report-menu-button';button.textContent='☰ Меню';button.setAttribute('aria-expanded','false');
  button.onclick=()=>button.setAttribute('aria-expanded',String(sidebar.classList.toggle('report-menu-open')));
  sidebar.querySelector('.brand').after(button);
}
dashboard=async function(tab='quizzes'){
  if(tab!=='sessions'||!boot.user)return reportDashboard(tab);
  stopPoll();page='sessions';const data=await api('quizzes');library=data.quizzes;rooms=data.rooms;
  shell(`<section class="report-heading"><div><div class="eyebrow">ИГРЫ И РЕЗУЛЬТАТЫ</div><h1>История игр<span>.</span></h1><p>Одна игра — одна ведомость. Свяжите игровые имена с участниками, и баллы появятся в их профилях.</p></div><button class="outline" data-action="dashboard">← К опросам</button></section><div class="report-session-grid">${rooms.map(r=>`<article class="report-session panel"><div class="report-session-top"><span class="report-pill ${r.status==='finished'?'is-done':''}">${r.status==='finished'?'✓ Завершена':r.status==='lobby'?'Ожидает игроков':'Идёт игра'}</span><span class="report-code">#${esc(r.code)}</span></div><h2>${esc(r.title)}</h2><p>${reportDate(r.created_at)}</p><div class="report-session-stats"><span><strong>${r.player_count}</strong> игроков</span><span><strong>${r.linked_count}</strong> связаны с аккаунтами</span></div><div class="report-session-bottom">${communityStaff()?`<button class="primary" data-action="link-participants" data-id="${r.id}">${r.assessment_id?'Открыть ведомость':r.status==='finished'?'Оформить результаты':'Сопоставить игроков'} →</button>`:''}<button class="text-button" data-action="host" data-id="${r.id}">Открыть игру ↗</button></div>${r.assessment_id?'<small class="report-connected">✓ Ведомость сохранена в результатах участников</small>':''}</article>`).join('')||'<div class="report-empty panel"><span>◷</span><h2>Здесь будут ваши игры</h2><p>Проведите викторину — её результаты останутся в истории.</p></div>'}</div>`,'sessions');
  reportMobileNavigation();
};
function reportMax(){return document.querySelector('#report-auto-max')?.checked?Number(roomReportData.maximum.points):Number(document.querySelector('#report-max').value);}
function reportParticipants(){return roomReportData.players.filter(p=>roomReportLinks[p.id]);}
async function linkParticipants(room){
  stopPoll();page='room-report';directoryUsers=(await api('directory')).users;
  roomReportData=await api('room_participants&room='+encodeURIComponent(room));roomReportLinks=Object.fromEntries(roomReportData.players.map(p=>[p.id,p.user_id]));roomReportDirty=false;
  const d=roomReportData,r=d.room,automatic=d.report?.source_max_override==null&&d.maximum.points>0;
  const maximum=d.report?.source_max_override??d.maximum.points;
  shell(`<section class="report-heading"><div><button class="text-button report-back" data-action="report-back">← История игр</button><div class="eyebrow">ВЕДОМОСТЬ РЕЗУЛЬТАТОВ ИГРЫ</div><h1>${esc(r.title)}<span>.</span></h1><p>${reportDate(r.created_at)} <span class="report-dot">·</span> Игра #${esc(r.code)}</p></div><span class="report-pill ${r.status==='finished'?'is-done':''}">${r.status==='finished'?'✓ Игра завершена':'Игра ещё не завершена'}</span></section><section class="report-summary"><div><span>Играли</span><strong>${d.players.length}</strong><small>результаты сохранены</small></div><div><span>Связаны с аккаунтами</span><strong id="report-linked">0</strong><small id="report-unlinked"></small></div><div><span>Ведомость</span><strong class="report-summary-label">${d.report?'Создана':'Автоматически'}</strong><small>${d.report?'обновится при сохранении':'после сохранения связей'}</small></div></section><div class="report-layout"><section class="panel report-matching"><div class="section-heading"><div><h2>Игрок → участник</h2><p>Выберите, кому принадлежат сохранённые баллы.</p></div><span class="report-pill">Без повторного ввода</span></div><div class="report-filters"><label class="search"><span>⌕</span><input id="report-player-search" placeholder="Найти игровое имя…" aria-label="Поиск игроков"></label><label class="report-check"><input type="checkbox" id="report-only-unlinked">Только без аккаунта</label></div><div id="report-player-list">${d.players.map((p,i)=>`<article class="report-player" data-report-player="${p.id}" data-player-name="${esc(p.name.toLocaleLowerCase())}"><div class="report-player-score"><span class="report-place">${i+1}</span><div><strong>${esc(p.name)}</strong><span>${reportNumber(p.score)} баллов <b data-player-percent="${p.id}"></b></span></div></div><span class="report-arrow" aria-hidden="true">→</span><div class="report-player-account"><div data-account-view="${p.id}"></div><div class="report-player-controls"><button class="outline small" data-action="report-choose" data-id="${p.id}">Выбрать участника</button><button class="text-button danger" data-action="report-unlink" data-id="${p.id}" aria-label="Убрать связь">×</button></div></div></article>`).join('')||'<div class="report-empty">В игре пока нет участников.</div>'}</div><p id="report-filter-empty" class="report-empty" hidden>По вашему запросу игроков нет.</p></section><aside><section class="panel report-settings"><div class="eyebrow">РАСЧЁТ ПРОЦЕНТОВ</div><h2>Баллы уже здесь</h2><p>Пульс перенесёт их в ведомость после сопоставления аккаунтов.</p><label class="report-check"><input id="report-auto-max" type="checkbox" ${automatic?'checked':''} ${d.maximum.points>0?'':'disabled'}>Определять максимум автоматически</label><label>Максимум баллов<input id="report-max" type="number" min="1" max="100000000" step="any" value="${maximum||Math.max(1,...d.players.map(p=>Number(p.score)))}" inputmode="decimal"></label><p id="report-max-basis" class="report-help"></p><div class="report-formula"><small>Пример расчёта</small><strong id="report-example"></strong><span>баллы ÷ максимум × 100%</span></div><div class="report-info"><strong>Что увидит участник?</strong><p>Название теста, свои баллы и процент в «Моих результатах». Чужие оценки ему не показываются.</p></div><button class="text-button" data-action="report-open-results">Все ведомости ↗</button></section></aside></div><div class="report-save-bar"><div><strong id="report-save-state">${d.report?'Ведомость сохранена':'Выберите аккаунты игроков'}</strong><span id="report-save-detail">Баллы и ответы исходной игры сохраняются.</span></div><button class="primary" data-action="report-save">${d.report?'Сохранить изменения':'Сохранить связи и создать ведомость'} →</button></div>`,'sessions');
  reportMobileNavigation();
  updateRoomReport();
}
function updateRoomReport(){
  const d=roomReportData,max=reportMax(),linked=reportParticipants().length;
  document.querySelector('#report-linked').textContent=linked;
  document.querySelector('#report-unlinked').textContent=linked===d.players.length?'Все участники сопоставлены':`${d.players.length-linked} ещё нужно сопоставить`;
  document.querySelector('#report-max').disabled=document.querySelector('#report-auto-max').checked;
  document.querySelector('#report-max-basis').textContent=document.querySelector('#report-auto-max').checked?d.maximum.label:'100% — указанный вами максимум. Он должен быть не меньше лучшего результата игры.';
  const example=d.players[0]?.score??0;
  document.querySelector('#report-example').textContent=max>0?`${reportNumber(example)} / ${reportNumber(max)} = ${reportNumber(example/max*100)}%`:'Укажите максимум';
  for(const p of d.players){
    const uid=roomReportLinks[p.id],u=directoryUsers.find(u=>u.id===uid);
    const view=document.querySelector(`[data-account-view="${p.id}"]`);
    view.innerHTML=u?`<span class="report-avatar">${esc(u.name.slice(0,1))}</span><div><strong>${esc(u.name)}</strong><small>${u.issuer?'Участник марафона':'Аккаунт Пульса'}${Number(u.active)?'':' · неактивен'}</small></div>`:'<span class="report-account-empty">Аккаунт ещё не выбран</span>';
    document.querySelector(`[data-action="report-unlink"][data-id="${p.id}"]`).hidden=!uid;
    document.querySelector(`[data-action="report-choose"][data-id="${p.id}"]`).textContent=uid?'Изменить':'Выбрать участника';
    document.querySelector(`[data-player-percent="${p.id}"]`).textContent=max>0?`· ${reportNumber(p.score/max*100)}%`:'';
  }
  if(roomReportDirty){document.querySelector('#report-save-state').textContent='Есть несохранённые изменения';document.querySelector('#report-save-detail').textContent=`В ведомость попадёт участников: ${linked}.`}
  filterReportPlayers();
}
function filterReportPlayers(){
  const search=document.querySelector('#report-player-search').value.toLocaleLowerCase(),only=document.querySelector('#report-only-unlinked').checked;let shown=0;
  document.querySelectorAll('[data-report-player]').forEach(row=>{row.hidden=!row.dataset.playerName.includes(search)||(only&&!!roomReportLinks[row.dataset.reportPlayer]);if(!row.hidden)shown++});
  document.querySelector('#report-filter-empty').hidden=shown>0;
}
function chooseReportParticipant(playerId){
  const p=roomReportData.players.find(p=>p.id===playerId),dialog=document.createElement('dialog');dialog.className='report-picker';
  dialog.innerHTML=`<div class="report-picker-head"><div><div class="eyebrow">СВЯЗАТЬ С АККАУНТОМ</div><h2>${esc(p.name)}</h2><p>${reportNumber(p.score)} баллов из игры</p></div><button class="icon-button" aria-label="Закрыть">×</button></div><label class="report-picker-search">⌕<input type="search" id="report-account-search" placeholder="Имя участника…" autocomplete="off" aria-label="Поиск участника"></label><div id="report-account-options"></div><p class="report-help">Совпадение имени — только подсказка. Вы сами подтверждаете, кому принадлежат баллы.</p>`;
  function options(){
    const text=dialog.querySelector('input').value.toLocaleLowerCase();
    const users=directoryUsers.filter(u=>(Number(u.active)||u.id===roomReportLinks[playerId])&&u.name.toLocaleLowerCase().includes(text)).sort((a,b)=>Number(!!b.issuer)-Number(!!a.issuer)||a.name.localeCompare(b.name,'ru'));
    dialog.querySelector('#report-account-options').innerHTML=users.map(u=>{const other=roomReportData.players.find(p=>p.id!==playerId&&roomReportLinks[p.id]===u.id);return `<button class="report-account-option" data-pick-account="${u.id}" ${other?'disabled':''}><span class="report-avatar">${esc(u.name.slice(0,1))}</span><span><strong>${esc(u.name)}</strong><small>${other?'Уже связан с «'+esc(other.name)+'»':u.issuer?'Марафон · '+esc(u.id.slice(-5)):'Пульс · '+esc(u.id.slice(-5))}</small></span><b>${u.id===roomReportLinks[playerId]?'✓':'→'}</b></button>`;}).join('')||'<div class="report-empty">Участники не найдены. Обновите список из марафона в разделе «Участники».</div>';
  }
  document.body.append(dialog);dialog.querySelector('.icon-button').onclick=()=>dialog.close();dialog.onclose=()=>dialog.remove();dialog.querySelector('input').oninput=options;
  dialog.onclick=event=>{const b=event.target.closest('[data-pick-account]');if(!b||b.disabled)return;roomReportLinks[playerId]=b.dataset.pickAccount;roomReportDirty=true;dialog.close();updateRoomReport();};
  options();dialog.showModal();dialog.querySelector('input').focus();
}
document.addEventListener('input',e=>{
  if(e.target.id==='report-player-search')filterReportPlayers();
  if(e.target.id==='report-max'){roomReportDirty=true;updateRoomReport();}
});
document.addEventListener('change',e=>{
  if(e.target.id==='report-only-unlinked')filterReportPlayers();
  if(e.target.id==='report-auto-max'){roomReportDirty=true;if(e.target.checked)document.querySelector('#report-max').value=roomReportData.maximum.points;updateRoomReport();}
});
document.addEventListener('click',async event=>{
  const b=event.target.closest('[data-action]');if(!b)return;const action=b.dataset.action;
  if(!['report-save','report-choose','report-unlink','report-back','report-open-results'].includes(action))return;
  event.preventDefault();event.stopImmediatePropagation();if(b.disabled)return;
  if(action==='report-choose')return chooseReportParticipant(b.dataset.id);
  if(action==='report-unlink'){roomReportLinks[b.dataset.id]=null;roomReportDirty=true;updateRoomReport();return;}
  if(action==='report-back'||action==='report-open-results'){
    const go=async()=>action==='report-back'?dashboard('sessions'):resultsPage(true);
    if(roomReportDirty)return confirmDialog('Уйти без сохранения?','Изменения связей ещё не сохранены. Ведомость останется в прежнем виде.',go);return go();
  }
  b.disabled=true;
  try{
    const max=reportMax();if(!Number.isFinite(max)||max<=0)throw Error('Укажите положительный максимум баллов.');
    const result=await api('link_room_players',{room:roomReportData.room.id,revision:roomReportData.room.revision,max_points:document.querySelector('#report-auto-max').checked?null:max,links:roomReportData.players.map(p=>({player_id:p.id,user_id:roomReportLinks[p.id]||null}))});
    roomReportDirty=false;await linkParticipants(roomReportData.room.id);
    toast(result.warning||'Ведомость обновлена. Баллы появились в профилях участников.');
  }catch(error){toast(error.message);}finally{b.disabled=false;}
},true);
