// Keep requests tied to the round that was visible when the form was opened.
const apiBeforeRounds=api;
api=async function(action,data,params=''){
 if(data&&['week_result','complete_week','clear_week_result','add_reading','save_report','correct_week_completion'].includes(action)){
  const id=data.user||profileData?.user.id||boot.user.id;
  const round=profileData?.user.id===id?profileData.marathon.round:users.find(u=>u.id===id)?.round||(boot.user.id===id?boot.user.round:1);
  const m=profileData?.user.id===id?profileData.marathon:boot.marathon;let week=Number(data.week||0);if(!week&&data.date)week=Math.floor((Date.parse(data.date+'T00:00:00Z')-Date.parse(m.start+'T00:00:00Z'))/604800000)+1;
  const results=profileData?.user.id===id?profileData.stats.reports:users.find(u=>u.id===id)?.weekly;
  data={...data,round:round||1,cycle:results?.find(w=>w.week===week)?.cycle??1};
 }
 return apiBeforeRounds(action,data,params);
};
// Every weekly pass keeps its own completion and daily entries.
const cardBeforeRepeats=weeklyCard;
weeklyCard=function(w,u,featured=false){
 const canRepeat=w.week===profileData.marathon.current&&(w.completed||w.cycle===0)&&(u.id===boot.user.id||boot.user.role==='admin');
 const manage=u.id===boot.user.id||boot.user.role==='admin';
 const removeButton=r=>manage&&r.cycle>0?`<button class="text-button danger-button" data-cycle-delete="${r.cycle}" data-cycle-week="${w.week}">Удалить круг ${r.cycle}</button>`:'';
 const extra=`<div class="weekly-repeat-summary"><strong>${w.cycle>0?`Круг ${w.cycle}`:'Нет активного круга'} · завершено кругов: ${w.completedCycles}</strong><p>Всего за эту неделю с повторами: ${w.totalChapters} глав.</p>${w.repeats.length?`<details><summary>История повторов · ${w.repeats.length}</summary>${w.repeats.map(r=>`<p>${r.completed?'✓':'◷'} Круг ${r.cycle}: ${r.chapters} глав за ${r.days} ${readingDayWord(r.days)}${r.completedOn?' · '+date(r.completedOn):' · не завершён'} ${removeButton(r)}</p>`).join('')}</details>`:''}${manage&&w.deletedRepeats?.length?`<details><summary>Удалённые круги · ${w.deletedRepeats.length}</summary>${w.deletedRepeats.map(r=>`<p>Круг ${r.cycle} · ${r.chapters} глав <button class="text-button" data-cycle-restore="${r.cycle}" data-cycle-week="${w.week}">Восстановить в историю</button></p>`).join('')}</details>`:''}${manage?removeButton(w):''}${boot.user.role==='admin'&&w.canComplete?`<button class="outline" data-completion-correct="${w.week}" data-user="${u.id}">${w.completed?'Исправить дату выполнения':'Внести выполнение за другую дату'}</button>`:''}${canRepeat?`<button class="outline" data-week-repeat="${w.week}" data-cycle="${w.cycle}">${w.cycle===0?'Начать новый круг':'🔁 Прочитать этот план ещё раз'}</button>`:''}</div>`;
 return cardBeforeRepeats(w,u,featured).replace('</article>',extra+'</article>');
};
const profileBeforeRepeats=drawProfile;
drawProfile=function(){
 const before=boot.marathon;boot.marathon=profileData.marathon;try{profileBeforeRepeats()}finally{boot.marathon=before}
 const {stats:s,marathon:m}=profileData;
 const first=document.querySelector('.reader-summary>div:first-child b');if(first)first.textContent=s.totalChapters;
 const days=document.querySelector('.reader-summary>div:nth-child(2) b');if(days)days.textContent=s.totalDays;
 const label=document.querySelector('.marathon-label>span');if(label)label.textContent=m.start.slice(0,4)+' / '+m.end.slice(0,4);
 if(s.pace){const info=document.createElement('div');info.className='panel weekly-current-progress';info.innerHTML=`<div class="section-title"><h2>Прогресс текущей недели</h2><strong>${s.progress}%</strong></div><p>Неделя ${s.pace.week} · ${s.pace.cycle>0?'круг '+s.pace.cycle:'нет активного круга'} · ${s.pace.chapters} из ${s.pace.goal} глав</p><div class="mini-progress"><i style="width:${s.progress}%"></i></div>`;document.querySelector('.reader-summary')?.after(info)}
 const note=document.querySelector('.reader-other-weeks .section-title small');if(note)note.textContent=boot.user.role==='admin'?'Все недели марафона':'Прошедшие недели';
};
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-week-repeat]');if(!b||busy)return;
 const w=profileData.stats.reports.find(w=>w.week===Number(b.dataset.weekRepeat));if(!w)return;
 dialog(`<h2>Начать круг ${w.nextCycle} недели ${w.week}?</h2><p>Ещё раз прочитать тот же план: ${w.goal} глав. Срок прежний — ${date(w.end)}. ${w.cycle>0?'Результат завершённого круга сохранится в истории. ' : ''}Прогресс нового круга начнётся с нуля.</p>${bookList(w.books,true)}<form id="weekly-repeat-form"><input type="hidden" name="user" value="${profileData.user.id}"><input type="hidden" name="week" value="${w.week}"><input type="hidden" name="cycle" value="${w.cycle}"><p class="form-feedback" role="alert"></p><button class="primary" type="submit">Подтвердить повтор</button></form>`);
});
document.addEventListener('submit',async e=>{
 if(e.target.id!=='weekly-repeat-form')return;e.preventDefault();if(busy)return;busy=true;const f=e.target,b=f.querySelector('[type=submit]');b.disabled=true;
 try{const data=Object.fromEntries(new FormData(f));await api('start_week_repeat',data);document.querySelector('dialog')?.close();await profile(data.user);toast('Новый круг недели начат. Прежний результат сохранён.')}catch(err){f.querySelector('.form-feedback').textContent=err.message}finally{busy=false;b.disabled=false}
});

// Deletion is reversible; mutations carry the active pass seen by the user.
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-cycle-delete],[data-cycle-restore]');if(!b||busy)return;
 const w=profileData.stats.reports.find(w=>w.week===Number(b.dataset.cycleWeek));if(!w)return;
 const restore=b.dataset.cycleRestore!==undefined,cycle=Number(restore?b.dataset.cycleRestore:b.dataset.cycleDelete);
 dialog(`<h2>${restore?'Восстановить':'Удалить'} круг ${cycle} недели ${w.week}?</h2><p>${restore?`Результат вернётся в историю и общий итог. ${w.cycle>0?'Текущий проход останется прежним.':'Этот круг снова станет активным.'}`:cycle===w.cycle?'Текущий проход будет удалён. Последний сохранённый проход вернётся в текущий; если его нет, активного круга не останется. Новый автоматически не создаётся. Результат можно восстановить из удалённых кругов.':'Этот проход исчезнет из истории и общих итогов. Его можно будет восстановить.'}</p><form id="cycle-change-form"><input type="hidden" name="user" value="${profileData.user.id}"><input type="hidden" name="week" value="${w.week}"><input type="hidden" name="cycle" value="${cycle}"><input type="hidden" name="active_cycle" value="${w.cycle}"><input type="hidden" name="restore" value="${restore?1:0}"><p class="form-feedback" role="alert"></p><button class="primary" type="submit">${restore?'Восстановить':'Подтвердить удаление'}</button></form>`);
});
document.addEventListener('submit',async e=>{
 if(e.target.id!=='cycle-change-form')return;e.preventDefault();if(busy)return;busy=true;const f=e.target,b=f.querySelector('[type=submit]');b.disabled=true;
 try{const data=Object.fromEntries(new FormData(f));await api(data.restore==='1'?'restore_week_cycle':'delete_week_cycle',data);document.querySelector('dialog')?.close();await profile(data.user);toast(data.restore==='1'?'Круг восстановлен в истории.':'Круг удалён. Итоги пересчитаны.')}catch(err){f.querySelector('.form-feedback').textContent=err.message}finally{busy=false;b.disabled=false}
});

// Administrators can correct the actual finish date without reopening a week for everyone.
document.addEventListener('click',e=>{
 const button=e.target.closest('[data-completion-correct]');if(!button||busy||boot.user.role!=='admin')return;
 const id=button.dataset.user,week=Number(button.dataset.completionCorrect),w=editableWeek(id,week);if(!w)return;
 const today=profileData?.user.id===id?profileData.marathon.today:boot.marathon.today,onTime=w.end<today?w.end:today;
 const d=dialog(`<h2>${w.completed?'Исправить выполнение':'Внести выполнение'} · неделя ${week}</h2><p>Срок недели — ${date(w.end)}. Выберите дату, когда участник действительно закончил план.</p><form id="completion-correction-form"><input type="hidden" name="user" value="${id}"><input type="hidden" name="week" value="${week}"><label>Фактическая дата завершения<input type="date" name="completed_on" required min="${w.start}" max="${today}" value="${w.completedOn||onTime}"></label><button type="button" class="outline" data-finish-on-time>✓ Выполнено в срок</button><p class="soft-note">Весь план будет отмечен выполненным. Дни чтения пересчитаются по выбранной дате. Ежедневные отметки и история других кругов сохранятся.</p><p class="form-feedback" role="alert"></p><button class="primary" type="submit">Сохранить выполнение</button></form>`);
 d.querySelector('[data-finish-on-time]').onclick=()=>{d.querySelector('[name=completed_on]').value=onTime;};
});
document.addEventListener('submit',async e=>{
 if(e.target.id!=='completion-correction-form')return;e.preventDefault();if(busy)return;busy=true;
 const form=e.target,button=form.querySelector('[type=submit]');button.disabled=true;
 try{const data=Object.fromEntries(new FormData(form)),wasProfile=view==='profile';await api('correct_week_completion',data);document.querySelector('dialog')?.close();boot=await api('bootstrap');wasProfile?await profile(data.user):await loadOverview(view);toast('Дата и статус выполнения исправлены.');}
 catch(error){form.querySelector('.form-feedback').textContent=error.message;}
 finally{busy=false;button.disabled=false;}
});
