const d=window.SITE,$=s=>document.querySelector(s);
document.querySelectorAll('[data-brand]').forEach(e=>e.textContent=d.brand);document.querySelectorAll('[data-city]').forEach(e=>e.textContent=d.city);$('h1').textContent=d.headline;$('.intro').textContent=d.intro;
d.services.forEach(([title,copy],i)=>{const row=document.createElement('article');row.className='service';const num=document.createElement('span');num.textContent=`0${i+1}`;const h=document.createElement('h3');h.textContent=title;const p=document.createElement('p');p.textContent=copy;row.append(num,h,p);$('#service-list').append(row)});
const dialog=$('dialog'),content=$('.dialog-content');function close(){dialog.close();content.replaceChildren()}$('.close').onclick=close;dialog.addEventListener('close',()=>content.replaceChildren());dialog.addEventListener('click',e=>{if(e.target===dialog)close()});
d.works.forEach(w=>{const item=document.createElement('article');item.className='work';item.dataset.project=w.project;const b=document.createElement('button');b.className='work-preview';b.setAttribute('aria-label',`Смотреть ${w.title}`);const img=document.createElement('img');img.src=w.poster;img.alt=w.title;img.loading='lazy';const play=document.createElement('span');play.className='play';play.textContent='↗';b.append(img,play);const tag=document.createElement('p');tag.className='eyebrow';tag.textContent=w.tag;const h=document.createElement('h3');h.textContent=w.title;const note=document.createElement('p');note.className='note';note.textContent=w.description;item.append(b,tag,h,note);$('.works').append(item);b.onclick=()=>{const v=document.createElement('video');v.src=w.video;v.controls=true;v.playsInline=true;v.autoplay=true;const h=document.createElement('h3');h.textContent=w.title;const p=document.createElement('p');p.textContent=w.description+(w.contribution?' '+w.contribution:'');content.replaceChildren(v,h,p);dialog.showModal()}});
document.querySelectorAll('.reference').forEach(b=>b.onclick=()=>{const img=document.createElement('img');img.src=d.reference;img.alt='Визуальный референс — не подтверждённый результат';const p=document.createElement('p');p.textContent='Только визуальный референс. Статистика не подтверждена и не является обещанием результата.';content.replaceChildren(img,p);dialog.showModal()});
let count=0;for(const [key,label] of [['telegram','Telegram'],['instagram','Instagram']]){if(!d[key])continue;try{const u=new URL(d[key]);if(u.protocol!=='https:')continue;const a=document.createElement('a');a.href=u.href;a.className='button';a.textContent=label+' ↗';a.rel='noopener noreferrer';a.target='_blank';$('#contacts').append(a);count++}catch{}}
if(!count){const p=document.createElement('p');p.className='contact-placeholder';p.textContent='Контакты скоро появятся. Telegram и Instagram пока не указаны.';$('#contacts').append(p)}

const filters=$('.project-filters');
for(const [id,label] of [['all','Все работы'],...d.projects.map(p=>[p.id,p.name])]){
 const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('aria-pressed',String(id==='all'));
 button.onclick=()=>{filters.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));document.querySelectorAll('.work').forEach(w=>w.hidden=id!=='all'&&w.dataset.project!==id)};filters.append(button);
}
for(const project of d.projects){
 const a=document.createElement('a');a.href=project.url;a.target='_blank';a.rel='noopener noreferrer';const label=document.createElement('strong');label.textContent=project.name;const category=document.createElement('span');category.textContent=project.category;const icon=document.createElement('span');icon.className='instagram-mark';icon.setAttribute('aria-hidden','true');const lens=document.createElement('i');icon.append(lens);const details=document.createElement('div');details.append(label,category);const action=document.createElement('span');action.className='profile-action';action.textContent='Instagram ↗';a.setAttribute('aria-label',project.name+' — открыть Instagram');a.append(icon,details,action);$('.project-profiles').append(a);
}

for(const study of d.cases||[]){
 const article=document.createElement('article');article.className='case-panel';
 function text(tag,value,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e}
 article.append(text('p',study.period,'eyebrow'),text('h2',study.title),text('h3',study.goal),text('p',study.description,'case-description'),text('p',study.resultsPeriod,'case-period'));
 const metrics=document.createElement('div');metrics.className='case-metrics';
 for(const metric of study.metrics){const e=document.createElement('div');const value=text('strong',metric.value);if(Number.isFinite(metric.count)){value.dataset.count=metric.count;value.dataset.divisor=metric.divisor||1;value.dataset.suffix=metric.suffix||'';value.dataset.decimals=metric.decimals||0;value.dataset.final=metric.value}e.append(value,text('span',metric.label));metrics.append(e)}article.append(metrics);
 const list=document.createElement('ul');for(const outcome of study.outcomes)list.append(text('li',outcome));article.append(list,text('p',study.source,'note'));$('.case-list').append(article);
}


if(d.about){
 const about=d.about,box=$('.about-copy');
 function add(tag,value,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;box.append(e);return e}
 add('p','ОБО МНЕ','eyebrow');add('h2',about.name+' / THUGGER SMM');add('p',about.role,'about-role');
 const badges=add('div','','about-badges');for(const label of [about.experience,'Bishkek']){const span=document.createElement('span');span.textContent=label;badges.append(span)}
 about.paragraphs.forEach(p=>add('p',p,'about-text'));
 const skills=add('div','','skill-chips');about.skills.forEach(skill=>{const span=document.createElement('span');span.textContent=skill;skills.append(span)});
}
if(d.telegram){
 for(const selector of ['.actions .button','.nav-contact']){const a=$(selector);a.href=d.telegram;a.target='_blank';a.rel='noopener noreferrer'}
 const contact=$('#contacts .button');if(contact){contact.classList.add('instagram-cta');contact.textContent='Обсудить проект в Telegram ↗'}
 const sticky=document.createElement('a');sticky.className='mobile-cta';sticky.href=d.telegram;sticky.target='_blank';sticky.rel='noopener noreferrer';sticky.setAttribute('aria-label','Обсудить проект с Егором в Telegram');sticky.textContent='Обсудить проект в Telegram ↗';document.body.append(sticky);
}
// Enhance only when supported; content stays visible without motion or JavaScript.
if('IntersectionObserver' in window&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
 const targets=document.querySelectorAll('.hero-copy,.hero-art,.section-head,.service,.work,.steps article,.case-panel,.about-photo,.about-copy,.project-profiles a,#contact');
 const observer=new IntersectionObserver(entries=>{for(const entry of entries){if(!entry.isIntersecting)continue;entry.target.classList.add('is-visible');observer.unobserve(entry.target)}},{threshold:0.08});
 targets.forEach((target,i)=>{target.classList.add('reveal');target.style.setProperty('--reveal-delay',`${i%3*90}ms`);observer.observe(target)});
 document.querySelectorAll('.project-filters button').forEach(button=>button.addEventListener('click',()=>{
  document.querySelectorAll('.work:not([hidden])').forEach(card=>{card.classList.add('is-visible');observer.unobserve(card)});
 }));
}

// Animate the supplied case values once on entry; never invent or fetch live statistics.
if('IntersectionObserver' in window&&!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
 const counters=new IntersectionObserver(entries=>{for(const entry of entries){
  if(!entry.isIntersecting)continue;counters.unobserve(entry.target);
  const el=entry.target,target=Number(el.dataset.count),divisor=Number(el.dataset.divisor),suffix=el.dataset.suffix,decimals=Number(el.dataset.decimals),final=el.dataset.final;
  const started=performance.now(),duration=1600;
  const tick=now=>{const progress=Math.min((now-started)/duration,1),amount=target*(1-Math.pow(1-progress,3));el.textContent=progress===1?final:(amount/divisor).toLocaleString('ru-RU',{maximumFractionDigits:decimals})+suffix;if(progress<1)requestAnimationFrame(tick)};
  requestAnimationFrame(tick);
 }},{threshold:.7});document.querySelectorAll('[data-count]').forEach(el=>counters.observe(el));
}
