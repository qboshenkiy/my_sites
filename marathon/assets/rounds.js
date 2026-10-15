// Keep requests tied to the round that was visible when the form was opened.
const apiBeforeRounds=api;
api=async function(action,data,params=''){
 if(data&&['week_result','complete_week','clear_week_result','add_reading','save_report'].includes(action)){
  const id=data.user||profileData?.user.id||boot.user.id;
  const round=profileData?.user.id===id?profileData.marathon.round:users.find(u=>u.id===id)?.round||(boot.user.id===id?boot.user.round:1);
  data={...data,round:round||1};
 }
 return apiBeforeRounds(action,data,params);
};
const profileBeforeRounds=drawProfile;
drawProfile=function(){
 const overviewCalendar=boot.marathon;boot.marathon=profileData.marathon;try{profileBeforeRounds()}finally{boot.marathon=overviewCalendar}const {user:u,stats:s,marathon:m,rounds=[]}=profileData;
 const panel=document.createElement('section');panel.className='panel round-panel';
 panel.innerHTML=`<div class="section-title"><div><h2>Круг ${m.round||1}</h2><p>Старт: ${date(m.start)} · ${s.goalWeeks}/22 недель выполнено</p></div>${s.goalWeeks===22&&(u.id===boot.user.id||boot.user.role==='admin')?`<button class="primary" data-round-start="${u.id}">Начать круг ${(m.round||1)+1}</button>`:''}</div>${rounds.some(r=>!r.active)?`<div class="reader-actions">${rounds.filter(r=>!r.active).map(r=>`<button class="outline small" data-round-history="${r.number}" data-user="${u.id}">📜 Круг ${r.number} · ${r.chapters} глав</button>`).join('')}</div>`:'<p>Завершённые круги появятся здесь и сохранят результаты.</p>'}`;
 document.querySelector('.reader-heading')?.after(panel);
 if(boot.user.role==='admin'&&m.round>1)document.querySelectorAll('.reading-week').forEach(card=>{const week=Number(card.querySelector('[data-week-edit]')?.dataset.weekEdit||card.querySelector('[data-v3=complete]')?.dataset.week);let w=s.reports.find(r=>r.week===week);if(!w){const title=card.querySelector('h2')?.textContent;w=s.reports.find(r=>'Неделя '+r.week===title)}if(!w||w.week>=m.current)return;const b=document.createElement('button');b.className='text-button';b.dataset.roundLock=w.week;b.dataset.user=u.id;b.dataset.open=w.reopened?0:1;b.textContent=w.reopened?'Закрыть исправления':'Открыть неделю для исправлений';card.append(b)});
};
const overviewBeforeRounds=drawOverview;
drawOverview=function(tab){overviewBeforeRounds(tab);document.querySelectorAll('tbody tr').forEach(row=>{const id=row.querySelector('[data-action=profile]')?.dataset.id,u=users.find(u=>u.id===id);if(!u||u.round<=1)return;const person=row.querySelector('.person-cell small');if(person)person.textContent+=' · Круг '+u.round;if(tab==='team')return;const w=u.weekly[(matrixWeek||currentWeek())-1];const edit=row.querySelector('[data-v2=week-edit]');if(edit)edit.disabled=!w.editable;const complete=row.querySelector('[data-v2=complete]');if(complete)complete.disabled=!w.canComplete;const label=document.createElement('small');label.textContent=' '+date(w.start)+' — '+date(w.end);row.querySelector('.person-cell span:last-child')?.append(label)});};
document.addEventListener('click',async e=>{const history=e.target.closest('[data-round-history]'),start=e.target.closest('[data-round-start]'),lock=e.target.closest('[data-round-lock]');if(busy)return;try{
 if(history){busy=true;const a=await api('round_history',undefined,'&user='+encodeURIComponent(history.dataset.user)+'&round='+history.dataset.roundHistory);dialog(`<h2>Круг ${a.marathon.round} · история</h2><p>С ${date(a.marathon.start)} · ${a.stats.chapters} глав · ${a.stats.goalWeeks}/22 недель. Архив доступен для просмотра.</p><div class="table-scroll"><table><thead><tr><th>Неделя</th><th>Главы</th><th>Дни</th><th>Завершён</th></tr></thead><tbody>${a.stats.reports.map(w=>`<tr><td>${w.week}<small>${esc(w.title||planBookLabel(w.books))}</small></td><td>${w.chapters}/${w.goal}</td><td>${w.days}</td><td>${w.completedOn?date(w.completedOn):'—'}</td></tr>`).join('')}</tbody></table></div>`)}
 if(start){const m=profileData.marathon;dialog(`<h2>Начать круг ${m.round+1}?</h2><p>Прежние результаты сохранятся в истории. Новый круг — те же книги и главы, 22 недели с сегодняшнего дня. Telegram будет учитывать главы в новом круге.</p><form id="start-round-form"><input type="hidden" name="user" value="${start.dataset.roundStart}"><input type="hidden" name="round" value="${m.round}"><p class="form-feedback" role="alert"></p><button class="primary" type="submit">Подтвердить начало нового круга</button></form>`)}
 if(lock){busy=true;await api('week_lock',{user:lock.dataset.user,round:profileData.marathon.round,week:lock.dataset.roundLock,open:lock.dataset.open});await profile(lock.dataset.user)}
 }catch(err){toast(err.message)}finally{busy=false}});
function planBookLabel(books){return (books||[]).map(b=>b.title+' '+b.chapter_from+'–'+b.chapter_to).join('; ')}
document.addEventListener('submit',async e=>{if(e.target.id!=='start-round-form')return;e.preventDefault();if(busy)return;busy=true;const form=e.target,feedback=form.querySelector('.form-feedback'),b=form.querySelector('[type=submit]');b.disabled=true;try{const data=Object.fromEntries(new FormData(form));await api('start_round',data);document.querySelector('dialog')?.close();boot=await api('bootstrap');await profile(data.user);toast('Новый круг начат. История сохранена.')}catch(err){feedback.textContent=err.message}finally{busy=false;b.disabled=false}});
