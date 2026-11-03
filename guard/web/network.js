'use strict';
let inspectedIp='',ipGeneration=0,currentIpReport=null,currentIpSsh=null,currentIpGeo=null,currentProtection=null,ipEventsPage=0;
function ipButton(ip){return `<button class="ip-link" data-ip="${esc(ip)}">${esc(ip)}</button>`;}
function renderProtection(data,recent={peers:[]}){
 const rows=(data.blocked||[]).map(b=>[ipButton(b.ip),esc(date(b.created)),esc(date(b.expires)),badge('Все порты','bad'),`<button data-ip="${esc(b.ip)}">Подробности / снять</button>`]);
 return `<div class="metrics">${metric('Сетевая защита',data.ready?'Работает':'Недоступна','HTTP/S, SSH и опубликованные порты Docker')}${metric('Заблокировано IP',(data.blocked||[]).length,'Только отдельные адреса, без диапазонов')}${metric('Пакетов отброшено',data.dropped_packets??'—','С момента создания правил')}${metric('Ваш IP',data.client_ip||'—','Текущий адрес нельзя заблокировать')}</div>${data.error?'<div class="warning">'+esc(data.error)+'</div>':''}`+panel('Проверить IP','Откройте адрес, чтобы увидеть запросы, входы, примерную географию и принять меры.',`<form id="ip-lookup-form" class="split"><input name="ip" placeholder="Например, 34.15.162.36" aria-label="IP для просмотра" required maxlength="64"><button class="primary">Посмотреть действия</button></form><p class="pill-count">Блокировка действует на весь сервер: все его домены, SSH и другие входящие соединения. Адрес может быть общим для нескольких людей, например при VPN или NAT. Ограничение истекает по таймеру ядра, даже если Guard остановлен.</p>`)+panel('Активные блокировки','Можно снять ограничение раньше срока. Сроки: 15 минут, час или сутки.',table(['IP','Установлена','Истекает','Область','Действие'],rows))+panel('IP за последние сутки','Сохранённые HTTP-запросы: нажмите адрес, чтобы открыть карту и историю.',recent.error?'<div class="warning">Не удалось загрузить последние IP. Обновите страницу.</div>':table(['IP','Запросов','Последний запрос'],(recent.peers||[]).map(r=>[ipButton(r.ip),r.requests,esc(date(r.last_seen))])));
}
async function openIpDetails(raw){
 const ip=String(raw||'').trim();if(!ip)return;
 const generation=++ipGeneration;inspectedIp=ip;currentIpReport=currentIpSsh=currentIpGeo=currentProtection=null;
 ipEventsPage=0;$('ip-overview').textContent='';$('ip-title').textContent=ip;$('ip-action-status').textContent='';$('ip-http').textContent='Загружаю историю запросов…';$('ip-geo').textContent='Определяю сеть и примерный регион…';$('ip-ssh').textContent='Проверяю журналы входов…';$('ip-controls').textContent='Проверяю сетевую защиту…';
 if(!$('ip-dialog').open)$('ip-dialog').showModal();
 const period=$('ip-period').value;
 const query='?ip='+encodeURIComponent(ip)+'&period='+period;
 api('/api/ip/http'+query).then(data=>{if(generation!==ipGeneration)return;currentIpReport=data;inspectedIp=data.ip;$('ip-title').textContent=data.ip;drawIpHttp(data);drawIpControls();}).catch(error=>{if(generation===ipGeneration)$('ip-http').textContent=error.message;});
 api('/api/protection').then(data=>{if(generation!==ipGeneration)return;currentProtection=data;drawIpControls();}).catch(error=>{if(generation===ipGeneration)$('ip-controls').textContent=error.message;});
 api('/api/ip/ssh'+query).then(data=>{if(generation!==ipGeneration)return;currentIpSsh=data;drawIpSsh(data);}).catch(error=>{if(generation===ipGeneration)$('ip-ssh').textContent=error.message;});
 api('/api/ip/geo?ip='+encodeURIComponent(ip)).then(data=>{if(generation!==ipGeneration)return;currentIpGeo=data;drawIpGeo(data);}).catch(error=>{if(generation===ipGeneration)$('ip-geo').textContent=error.message;});
}
function drawIpHttp(data){
 const statuses=Object.entries(data.statuses).map(([code,count])=>`${code}: ${count}`).join(' · ')||'Нет записей';
 const findings=data.findings.map(text=>`<p class="ip-finding">${esc(text)}</p>`).join('');
 $('ip-overview').innerHTML=`<h3>Что делал этот IP</h3><div class="ip-summary"><span>Запросов: <strong>${esc(data.total)}</strong></span><span>Пик за 60 секунд: <strong>${esc(data.peak_per_minute)}</strong></span><span>Первый: ${esc(date(data.first_seen))}</span><span>Последний: ${esc(date(data.last_seen))}</span></div><p>${esc(statuses)}</p>${findings}`;
 $('ip-http').innerHTML=`<h3>Сайты</h3>${table(['Домен','Запросов'],data.sites.map(r=>[esc(r.host),r.count]))}<h3>Частые адреса</h3>${table(['Метод','Путь','Запросов'],data.paths.map(r=>[esc(r.method),'<span class="ip-path">'+esc(r.path)+'</span>',r.count]))}<h3>Хронология запросов</h3>${table(['Время','Сайт / метод','Путь / действие','Ответ','Объём / время','Клиент'],data.events.slice(ipEventsPage*50,(ipEventsPage+1)*50).map(e=>[esc(date(e.time)),esc(e.host)+'<br>'+esc(e.method)+' · '+esc(e.protocol),'<div class="ip-path">'+esc(e.path)+'</div>'+(e.action?'<small>action='+esc(e.action)+'</small>':'')+(e.query_keys?.length?'<br><small>Параметры: '+esc(e.query_keys.join(', '))+'</small>':''),badge(e.status,e.status>=400?'bad':'good'),esc(e.response_bytes)+' байт<br>'+esc(e.duration_ms??'—')+' мс','<div class="ip-agent">'+esc(e.user_agent||'Не указан')+'</div><small>Порт клиента: '+esc(e.source_port||'—')+'</small>']))}<div class="split"><button id="ip-prev" ${ipEventsPage===0?'disabled':''}>Назад</button><span>Страница ${ipEventsPage+1} из ${Math.max(1,Math.ceil(data.events.length/50))}</span><button id="ip-next" ${(ipEventsPage+1)*50>=data.events.length?'disabled':''}>Далее</button></div><p class="pill-count">До 500 последних строк; итоги рассчитаны по всем сохранённым событиям за период. История хранится 7 дней, максимум 200 000 записей на сервер. Тела POST, cookies, пароли и значения секретных параметров не сохраняются. Код 2xx сам по себе не означает взлом.</p><button id="ip-export">Скачать отчёт JSON</button>`;
}
function drawIpControls(){
 const data=currentProtection;if(!data||!currentIpReport)return;
 const blocked=(data.blocked||[]).find(b=>b.ip===inspectedIp);
 const protectedIp=currentIpReport.is_public===false||inspectedIp===data.client_ip||(data.protected_ips||[]).includes(inspectedIp);
 $('ip-controls').innerHTML=data.ready?`<div class="split">${badge(blocked?'Полностью заблокирован':'Не заблокирован',blocked?'bad':'good')}${protectedIp?badge('Адрес защищён'):''}${blocked?'<span>До '+esc(date(blocked.expires))+'</span>':`<select id="ip-duration" aria-label="Срок блокировки"><option value="900">15 минут</option><option value="3600" selected>1 час</option><option value="86400">24 часа</option></select>`}<button id="ip-enforce" class="${blocked?'secondary':'danger-button'}" ${protectedIp?'disabled':''}>${blocked?'Снять блокировку':'Заблокировать на всём сервере'}</button></div><p class="pill-count">Все домены, HTTP/HTTPS, SSH, Docker и прочие входящие подключения. Ваш текущий IP, сам сервер и служебные адреса защищены от блокировки.</p>`:'<div class="warning">'+esc(data.error||'Сетевая защита не подключена')+'</div>';
}
function drawIpSsh(data){
 const success=data.ssh.filter(e=>e.result==='success').length;
 $('ip-ssh').innerHTML='<h3>SSH и входы в Guard</h3><p>'+(success?'Обнаружены успешные SSH-входы с этого IP: '+esc(success):'Успешных SSH-входов с этого IP в доступной выборке нет.')+'</p>'+table(['Время','Пользователь SSH','Результат','Способ'],data.ssh.map(e=>[esc(date(e.time)),esc(e.user),badge(e.result==='success'?'Успешно':'Отказ',e.result==='success'?'good':'bad'),esc(e.method)]))+table(['Время','Вход в Guard'],data.guard.map(e=>[esc(date(e.created)),badge(e.action==='login_success'?'Успешно':'Неверный пароль',e.action==='login_success'?'good':'bad')]))+'<p class="pill-count">'+esc(data.note)+' После полной сетевой блокировки новые соединения отбрасываются до сайта и SSH, поэтому их URL и попытки входа уже не попадают в эти журналы.</p>';
}
function drawIpGeo(data){
 let country=data.country||'Не определена';try{if(data.country)country=new Intl.DisplayNames(['ru'],{type:'region'}).of(data.country);}catch(error){}
 let map='';
 if(data.available){
  const latitude=Number(data.latitude),longitude=Number(data.longitude);
  if(Number.isFinite(latitude)&&Number.isFinite(longitude)&&Math.abs(latitude)<=90&&Math.abs(longitude)<=180){
   const bbox=[Math.max(-180,longitude-.3),Math.max(-90,latitude-.2),Math.min(180,longitude+.3),Math.min(90,latitude+.2)].join(',');
   const url='https://www.openstreetmap.org/export/embed.html?'+new URLSearchParams({bbox,layer:'mapnik',marker:latitude+','+longitude});
   map=`<iframe class="ip-map" loading="lazy" title="Примерный регион сети IP" src="${esc(url)}" sandbox="allow-scripts allow-same-origin" referrerpolicy="no-referrer"></iframe><p class="pill-count">Карта © <a href="https://www.openstreetmap.org/?mlat=${latitude}&mlon=${longitude}#map=10/${latitude}/${longitude}" target="_blank" rel="noopener noreferrer">OpenStreetMap contributors</a></p>`;
  }
 }
 $('ip-geo').innerHTML=`<h3>Примерное происхождение IP</h3><div class="ip-summary"><span>Страна: <strong>${esc(country)}</strong></span><span>Регион: ${esc(data.region||'—')}</span><span>Город: ${esc(data.city||'—')}</span><span>Сеть / ASN: <strong>${esc(data.org||'—')}</strong></span><span>Имя узла: ${esc(data.hostname||'—')}</span>${data.cloud_region?'<span>Регион облака: '+esc(data.cloud_region)+' · '+esc(data.cloud_prefix)+'</span>':''}<span>Источник: ${esc(data.source||'—')} · ${esc(date(data.fetched_at))}</span></div><p class="warning">${esc(data.note||'Примерная география сети или дата-центра, а не человека.')}</p>${data.error?'<p>'+esc(data.error)+'</p>':''}${map}`;
}
$('content').addEventListener('click',e=>{const b=e.target.closest('[data-ip]');if(b)openIpDetails(b.dataset.ip);});
$('content').addEventListener('submit',e=>{if(e.target.id==='ip-lookup-form'){e.preventDefault();openIpDetails(new FormData(e.target).get('ip'));}});
$('ip-close').addEventListener('click',()=>{$('ip-dialog').close();ipGeneration++;});
$('ip-period').addEventListener('change',()=>openIpDetails(inspectedIp));
$('ip-dialog').addEventListener('click',async e=>{
 if((e.target.id==='ip-prev'||e.target.id==='ip-next')&&currentIpReport){ipEventsPage+=e.target.id==='ip-next'?1:-1;ipEventsPage=Math.max(0,Math.min(Math.ceil(currentIpReport.events.length/50)-1,ipEventsPage));drawIpHttp(currentIpReport);}

 if(e.target.id==='ip-enforce'){
  const b=e.target,blocked=(currentProtection.blocked||[]).some(item=>item.ip===inspectedIp),duration=blocked?0:Number($('ip-duration').value);
  if(!confirm(blocked?'Снять блокировку IP '+inspectedIp+' на всём сервере?':'Заблокировать IP '+inspectedIp+' на всех портах сервера? Это закроет HTTP/HTTPS, SSH и Docker. Другие люди с тем же IP тоже потеряют доступ.'))return;
  b.disabled=true;$('ip-action-status').textContent='Применяю правило…';
  try{currentProtection=await api('/api/protection/action',{action:blocked?'unblock':'block',ip:inspectedIp,duration});currentProtection.client_ip=currentProtection.client_ip||'';drawIpControls();$('ip-action-status').textContent=blocked?'Блокировка снята.':'IP полностью заблокирован.';if(tab==='protection')render();}
  catch(error){$('ip-action-status').textContent=error.message;b.disabled=false;}
 }
 if(e.target.id==='ip-export'&&currentIpReport){
  const data={http:currentIpReport,ssh:currentIpSsh,geography:currentIpGeo,exported_at:new Date().toISOString()};
  const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'}));const link=document.createElement('a');link.href=url;link.download='guard-ip-'+inspectedIp.replace(/:/g,'_')+'.json';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
 }
});
