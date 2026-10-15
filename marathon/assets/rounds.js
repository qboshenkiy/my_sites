// Keep requests tied to the round that was visible when the form was opened.
const apiBeforeRounds=api;
api=async function(action,data,params=''){
 if(data&&['week_result','complete_week','clear_week_result','add_reading','save_report'].includes(action)){
  const id=data.user||profileData?.user.id||boot.user.id;
  const round=profileData?.user.id===id?profileData.marathon.round:users.find(u=>u.id===id)?.round||(boot.user.id===id?boot.user.round:1);
  const m=profileData?.user.id===id?profileData.marathon:boot.marathon;let week=Number(data.week||0);if(!week&&data.date)week=Math.floor((Date.parse(data.date+'T00:00:00Z')-Date.parse(m.start+'T00:00:00Z'))/604800000)+1;
  const results=profileData?.user.id===id?profileData.stats.reports:users.find(u=>u.id===id)?.weekly;
  data={...data,round:round||1,cycle:results?.find(w=>w.week===week)?.cycle||1};
 }
 return apiBeforeRounds(action,data,params);
};
// Every weekly pass keeps its own completion and daily entries.
const cardBeforeRepeats=weeklyCard;
weeklyCard=function(w,u,featured=false){
 const canRepeat=w.week===profileData.marathon.current&&w.completed&&(u.id===boot.user.id||boot.user.role==='admin');
 const extra=`<div class="weekly-repeat-summary"><strong>Круг ${w.cycle} · завершено кругов: ${w.completedCycles}</strong><p>Всего за эту неделю с повторами: ${w.totalChapters} глав.</p>${w.repeats.length?`<details><summary>История повторов · ${w.repeats.length}</summary>${w.repeats.map(r=>`<p>✓ Круг ${r.cycle}: ${r.chapters} глав за ${r.days} ${readingDayWord(r.days)} · ${date(r.completedOn)}</p>`).join('')}</details>`:''}${canRepeat?`<button class="outline" data-week-repeat="${w.week}" data-cycle="${w.cycle}">🔁 Прочитать этот план ещё раз</button>`:''}</div>`;
 return cardBeforeRepeats(w,u,featured).replace('</article>',extra+'</article>');
};
const profileBeforeRepeats=drawProfile;
drawProfile=function(){
 const before=boot.marathon;boot.marathon=profileData.marathon;try{profileBeforeRepeats()}finally{boot.marathon=before}
 const {stats:s,marathon:m}=profileData;
 const first=document.querySelector('.reader-summary>div:first-child b');if(first)first.textContent=s.totalChapters;
 const days=document.querySelector('.reader-summary>div:nth-child(2) b');if(days)days.textContent=s.totalDays;
 const label=document.querySelector('.marathon-label>span');if(label)label.textContent=m.start.slice(0,4)+' / '+m.end.slice(0,4);
 if(s.pace){const info=document.createElement('div');info.className='panel weekly-current-progress';info.innerHTML=`<div class="section-title"><h2>Прогресс текущей недели</h2><strong>${s.progress}%</strong></div><p>Неделя ${s.pace.week} · круг ${s.pace.cycle} · ${s.pace.chapters} из ${s.pace.goal} глав</p><div class="mini-progress"><i style="width:${s.progress}%"></i></div>`;document.querySelector('.reader-summary')?.after(info)}
 const note=document.querySelector('.reader-other-weeks .section-title small');if(note)note.textContent=boot.user.role==='admin'?'Все недели марафона':'Прошедшие недели';
};
document.addEventListener('click',e=>{
 const b=e.target.closest('[data-week-repeat]');if(!b||busy)return;
 const w=profileData.stats.reports.find(w=>w.week===Number(b.dataset.weekRepeat));if(!w)return;
 dialog(`<h2>Начать круг ${w.cycle+1} недели ${w.week}?</h2><p>Ещё раз прочитать тот же план: ${w.goal} глав. Срок прежний — ${date(w.end)}. Результат завершённого круга сохранится в истории, прогресс нового начнётся с нуля.</p>${bookList(w.books,true)}<form id="weekly-repeat-form"><input type="hidden" name="user" value="${profileData.user.id}"><input type="hidden" name="week" value="${w.week}"><input type="hidden" name="cycle" value="${w.cycle}"><p class="form-feedback" role="alert"></p><button class="primary" type="submit">Подтвердить повтор</button></form>`);
});
document.addEventListener('submit',async e=>{
 if(e.target.id!=='weekly-repeat-form')return;e.preventDefault();if(busy)return;busy=true;const f=e.target,b=f.querySelector('[type=submit]');b.disabled=true;
 try{const data=Object.fromEntries(new FormData(f));await api('start_week_repeat',data);document.querySelector('dialog')?.close();await profile(data.user);toast('Новый круг недели начат. Прежний результат сохранён.')}catch(err){f.querySelector('.form-feedback').textContent=err.message}finally{busy=false;b.disabled=false}
});
