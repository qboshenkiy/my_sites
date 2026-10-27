/* Published scores are immutable snapshots until staff explicitly republishes. */
let standingsState=null;
async function standingsPage(){
 if(!boot.user)return communityAuth();stopPoll();page='standings';
 standingsState=await api('standings');const data=standingsState;
 shell(`<div class="forms-heading"><div><div class="eyebrow">ЗАКРЕПЛЁННЫЕ РЕЗУЛЬТАТЫ</div><h1>Общий рейтинг<span>.</span></h1><p>Опубликованные результаты: от первого места к последнему.</p></div><div class="forms-row-actions"><button class="outline" data-standings-export ${!data.tests.length?'disabled':''}>${AppUI.icon('download')} Скачать CSV</button>${communityStaff()?'<button class="primary" data-action="assessments">Публиковать результаты</button>':''}</div></div><section class="panel standings-summary"><div><strong>${data.published_count}</strong><span>закреплённых тестов</span></div><div><strong>${data.participants.length}</strong><span>участников</span></div><div><strong>${Number(data.max_points).toLocaleString('ru-RU')}</strong><span>максимум баллов</span></div></section><details class="forms-note standings-method"><summary>Как считаются места</summary><p>Общий процент = сумма закреплённых баллов ÷ сумма максимумов всех опубликованных тестов × 100%. Пропуск показан как «—» и даёт 0 баллов в общем итоге. При равном проценте место одинаковое: например, 1, 1, 3.</p></details>${data.tests.length?`<section class="panel standings-panel"><button class="outline standings-mobile-toggle" data-standings-details>Показать баллы по тестам</button><div class="section-heading"><div><h2>Таблица результатов</h2><p>Место не меняется при поиске участника.</p></div><label class="standings-search">Поиск участника<input type="search" data-standings-search placeholder="Имя участника"></label></div><div class="table-scroll"><table class="community-table standings-table"><thead><tr><th>Место</th><th>Участник</th><th>Общий процент</th><th>Баллы</th><th>Пройдено</th>${data.tests.map(t=>`<th><span>${esc(t.title)}</span><small>${esc(t.held_on)} · из ${t.max_points}</small></th>`).join('')}</tr></thead><tbody>${data.participants.map(p=>`<tr class="${p.id===boot.user.id?'my-standing':''}" data-standing-name="${esc(p.name.toLocaleLowerCase())}"><td><strong class="standing-rank">${p.rank}</strong></td><td><strong>${esc(p.name)}</strong>${p.id===boot.user.id?'<small>Это вы</small>':''}${!p.active?'<small>Архивный аккаунт</small>':''}</td><td><strong class="percent-result">${p.percent.toLocaleString('ru-RU')}%</strong><progress max="100" value="${p.percent}" aria-label="Общий процент ${p.percent}%"></progress></td><td>${p.points.toLocaleString('ru-RU')} / ${Number(data.max_points).toLocaleString('ru-RU')}</td><td>${p.completed} / ${data.tests.length}</td>${data.tests.map(t=>`<td>${Object.hasOwn(p.scores,t.id)?Number(p.scores[t.id]).toLocaleString('ru-RU'):'<span class="missing-score" title="Результат не внесён">—</span>'}</td>`).join('')}</tr>`).join('')}</tbody></table></div><p class="standings-no-matches" hidden>Участники не найдены.</p></section>`:`<section class="panel forms-empty"><h2>Пока ничего не закреплено</h2><p>Опубликуйте результат в ведомости. Он появится здесь и будет участвовать в расчёте общего места.</p>${communityStaff()?'<button class="primary" data-action="assessments">Открыть ведомости</button>':''}</section>`}`,'standings');
 requestAnimationFrame(()=>window.scrollTo({top:0,behavior:'instant'}));
}
document.addEventListener('click',event=>{
 if(event.target.closest('[data-standings-details]')){const panel=document.querySelector('.standings-panel'),open=panel.classList.toggle('show-details');event.target.closest('button').textContent=open?'Скрыть подробные баллы':'Показать баллы по тестам';return;}
 const publish=event.target.closest('[data-publish-results]'),remove=event.target.closest('[data-unpublish-results]');
 if(publish||remove){
  event.preventDefault();const id=(publish||remove).dataset[publish?'publishResults':'unpublishResults'];
  const assessment=assessmentData.assessments.find(a=>a.id===id);if(!assessment)return;
  confirmDialog(publish?'Закрепить результат в общем рейтинге?':'Открепить результат?',publish?'Имена, баллы и максимум этой ведомости будут видны вошедшим участникам и учтены в общем рейтинге. Дальнейшие изменения нужно публиковать повторно.':'Этот тест перестанет влиять на общий рейтинг. Сама ведомость и исходные ответы сохранятся.',async()=>{
   await api(publish?'publish_results':'unpublish_results',{id,revision:assessment.revision,publication_version:assessment.publication?.version||0});
   toast(publish?'Результат закреплён. Общий рейтинг пересчитан.':'Результат откреплён.');await resultsPage(true);
  });
 }
 if(event.target.closest('[data-standings-export]')&&standingsState){
  const d=standingsState,rows=[['Место','Участник','Общий процент','Баллы','Максимум','Пройдено',...d.tests.map(t=>t.title)],...d.participants.map(p=>[p.rank,p.name,p.percent,p.points,d.max_points,p.completed,...d.tests.map(t=>p.scores[t.id]??'')])];
  const safe=v=>{const s=String(v??'');return '"'+(/^[=+\-@\t\r]/.test(s)?"'":'')+s.replace(/"/g,'""')+'"';};
  const blob=new Blob(['\ufeff'+rows.map(row=>row.map(safe).join(';')).join('\r\n')],{type:'text/csv;charset=utf-8'}),url=URL.createObjectURL(blob),a=document.createElement('a');a.href=url;a.download='pulse-общий-рейтинг.csv';a.click();URL.revokeObjectURL(url);
 }
});
document.addEventListener('input',event=>{
 if(!event.target.matches('[data-standings-search]'))return;
 const value=event.target.value.trim().toLocaleLowerCase();let count=0;
 document.querySelectorAll('[data-standing-name]').forEach(row=>{row.hidden=!row.dataset.standingName.includes(value);if(!row.hidden)count++;});
 document.querySelector('.standings-no-matches').hidden=count>0;
});
