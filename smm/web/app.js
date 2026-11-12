const d=window.SITE,$=s=>document.querySelector(s);
document.querySelectorAll('[data-brand]').forEach(e=>e.textContent=d.brand);document.querySelectorAll('[data-city]').forEach(e=>e.textContent=d.city);$('h1').textContent=d.headline;$('.intro').textContent=d.intro;
d.services.forEach(([title,copy],i)=>{const row=document.createElement('article');row.className='service';const num=document.createElement('span');num.textContent=`0${i+1}`;const h=document.createElement('h3');h.textContent=title;const p=document.createElement('p');p.textContent=copy;row.append(num,h,p);$('#service-list').append(row)});
const dialog=$('dialog'),content=$('.dialog-content');function close(){dialog.close();content.replaceChildren()}$('.close').onclick=close;dialog.addEventListener('close',()=>content.replaceChildren());dialog.addEventListener('click',e=>{if(e.target===dialog)close()});
d.works.forEach(w=>{const item=document.createElement('article');item.className='work';item.dataset.project=w.project;const b=document.createElement('button');b.className='work-preview';b.setAttribute('aria-label',`Смотреть ${w.title}`);const img=document.createElement('img');img.src=w.poster;img.alt=w.title;img.loading='lazy';const play=document.createElement('span');play.className='play';play.textContent='↗';b.append(img,play);const tag=document.createElement('p');tag.className='eyebrow';tag.textContent=w.tag;const h=document.createElement('h3');h.textContent=w.title;const note=document.createElement('p');note.className='note';note.textContent=w.description;const frame=document.createElement('div');frame.className='video-frame';frame.append(b);for(const [direction,label,symbol] of [[-1,'Предыдущая работа','<'],[1,'Следующая работа','>']]){const arrow=document.createElement('button');arrow.className='slide-arrow '+(direction<0?'slide-prev':'slide-next');arrow.setAttribute('aria-label',label);const svg=document.createElementNS('http://www.w3.org/2000/svg','svg');svg.setAttribute('viewBox','0 0 24 24');svg.setAttribute('aria-hidden','true');const path=document.createElementNS('http://www.w3.org/2000/svg','path');path.setAttribute('d',direction<0?'M15.5 5 L8.5 12 L15.5 19':'M8.5 5 L15.5 12 L8.5 19');svg.append(path);arrow.append(svg);arrow.onclick=()=>stepSlide(direction);frame.append(arrow)}item.append(frame,tag,h,note);$('.works').append(item);b.onclick=()=>{const v=document.createElement('video');v.src=w.video;v.controls=true;v.playsInline=true;v.autoplay=true;const h=document.createElement('h3');h.textContent=w.title;const p=document.createElement('p');p.textContent=w.description+(w.contribution?' '+w.contribution:'');content.replaceChildren(v,h,p);dialog.showModal()}});
document.querySelectorAll('.reference').forEach(b=>b.onclick=()=>{const img=document.createElement('img');img.src=d.reference;img.alt='Визуальный референс — не подтверждённый результат';const p=document.createElement('p');p.textContent='Только визуальный референс. Статистика не подтверждена и не является обещанием результата.';content.replaceChildren(img,p);dialog.showModal()});
let count=0;for(const [key,label] of [['telegram','Telegram'],['instagram','Instagram']]){if(!d[key])continue;try{const u=new URL(d[key]);if(u.protocol!=='https:')continue;const a=document.createElement('a');a.href=u.href;a.className='button';a.textContent=label+' ↗';a.rel='noopener noreferrer';a.target='_blank';$('#contacts').append(a);count++}catch{}}
if(!count){const p=document.createElement('p');p.className='contact-placeholder';p.textContent='Контакты скоро появятся. Telegram и Instagram пока не указаны.';$('#contacts').append(p)}

const filters=$('.project-filters');
for(const [id,label] of [['all','Все работы'],...d.projects.map(p=>[p.id,p.name])]){
 const button=document.createElement('button');button.type='button';button.textContent=label;button.setAttribute('aria-pressed',String(id==='all'));
 button.onclick=()=>{filters.querySelectorAll('button').forEach(b=>b.setAttribute('aria-pressed',String(b===button)));selectProject(id)};filters.append(button);
}
for(const project of d.projects){
 const a=document.createElement('a');a.href=project.url;a.target='_blank';a.rel='noopener noreferrer';const label=document.createElement('strong');label.textContent=project.name;const category=document.createElement('span');category.textContent=project.category;const icon=document.createElement('span');icon.className='instagram-mark';icon.setAttribute('aria-hidden','true');const lens=document.createElement('i');icon.append(lens);const details=document.createElement('div');details.append(label,category);const action=document.createElement('span');action.className='profile-action';action.textContent='Instagram ↗';a.setAttribute('aria-label',project.name+' — открыть Instagram');a.append(icon,details,action);$('.project-profiles').append(a);
}

for(const study of d.cases||[]){
 const article=document.createElement('article');article.className='case-panel';
 function text(tag,value,cls){const e=document.createElement(tag);e.textContent=value;if(cls)e.className=cls;return e}
 article.append(text('p',study.period,'eyebrow'),text('h2',study.title),text('h3',study.goal),text('p',study.description,'case-description'),text('p',study.resultsPeriod,'case-period'));
 const metrics=document.createElement('div');metrics.className='case-metrics';
 for(const metric of study.metrics){const e=document.createElement('div');const value=text('strong',metric.value);if(Number.isFinite(metric.count)){value.dataset.count=metric.count;value.dataset.divisor=metric.divisor||1;value.dataset.suffix=metric.suffix||'';value.dataset.decimals=metric.decimals||0;value.dataset.final=metric.value;value.dataset.prefix=metric.prefix||''}e.append(value,text('span',metric.label));metrics.append(e)}article.append(metrics);
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
 const targets=document.querySelectorAll('.hero-copy,.hero-art,.section-head,.service,.work,.steps article,.case-panel,.about-photo,.about-copy,.project-profiles a,.project-filters,.approach>h2,.approach>.eyebrow,.about-badges span,.skill-chips span,#case-studies>.eyebrow,#contact');
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
  const el=entry.target,target=Number(el.dataset.count),divisor=Number(el.dataset.divisor),suffix=el.dataset.suffix,decimals=Number(el.dataset.decimals),final=el.dataset.final,prefix=el.dataset.prefix||'';
  const started=performance.now(),duration=1600;
  const tick=now=>{const progress=Math.min((now-started)/duration,1),amount=target*(1-Math.pow(1-progress,3));el.textContent=progress===1?final:prefix+(amount/divisor).toLocaleString('ru-RU',{maximumFractionDigits:decimals})+suffix;if(progress<1)requestAnimationFrame(tick)};
  requestAnimationFrame(tick);
 }},{threshold:.7});document.querySelectorAll('[data-count]').forEach(el=>counters.observe(el));
}

const gallery=$('.works');
let activeProject='all',activeSlide=0,lastManualChange=0,sliderHovered=false,sliderFocused=false,slideTransitioning=false,transitionTimer=0;
function availableSlides(){return [...gallery.querySelectorAll('.work')].filter(card=>activeProject==='all'||card.dataset.project===activeProject)}
function showSlide(animate=false){if(animate){if(slideTransitioning)return;slideTransitioning=true;gallery.classList.add('is-switching');transitionTimer=setTimeout(()=>{showSlide(false);gallery.classList.remove('is-switching');slideTransitioning=false},180);return}const slides=availableSlides();if(!slides.length)return;activeSlide=(activeSlide+slides.length)%slides.length;gallery.querySelectorAll('.work').forEach(card=>{card.hidden=true;card.classList.remove('slide-active')});const current=slides[activeSlide];current.hidden=false;current.classList.add('is-visible','slide-active');gallery.setAttribute('aria-label',`Видеопортфолио: ${activeSlide+1} из ${slides.length}`)}
function selectProject(id){clearTimeout(transitionTimer);slideTransitioning=false;gallery.classList.remove('is-switching');activeProject=id;activeSlide=0;lastManualChange=Date.now();showSlide()}
function stepSlide(direction,manual=true){if(slideTransitioning)return;activeSlide+=direction;if(manual)lastManualChange=Date.now();showSlide(!window.matchMedia('(prefers-reduced-motion: reduce)').matches)}
showSlide();
gallery.addEventListener('pointerenter',event=>{if(event.pointerType==='mouse')sliderHovered=true});gallery.addEventListener('pointerleave',()=>sliderHovered=false);
gallery.addEventListener('focusin',()=>sliderFocused=true);gallery.addEventListener('focusout',event=>{if(!gallery.contains(event.relatedTarget))sliderFocused=false});
if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches)setInterval(()=>{if(document.hidden||dialog.open||sliderHovered||sliderFocused||document.body.classList.contains('is-loading')||Date.now()-lastManualChange<8000)return;const rect=gallery.getBoundingClientRect();if(rect.bottom>0&&rect.top<innerHeight)stepSlide(1,false)},d.slideshow?.intervalMs||6500);
const progress=document.createElement('div');progress.className='page-progress';progress.setAttribute('aria-hidden','true');document.body.append(progress);
let scrollPending=false;
const updateProgress=()=>{const length=document.documentElement.scrollHeight-innerHeight;progress.style.transform=`scaleX(${length>0?Math.max(0,Math.min(1,scrollY/length)):0})`;scrollPending=false};
addEventListener('scroll',()=>{if(!scrollPending){scrollPending=true;requestAnimationFrame(updateProgress)}},{passive:true});addEventListener('resize',updateProgress);updateProgress();

const ambient=document.createElement('div');ambient.className='ambient-scene';ambient.setAttribute('aria-hidden','true');
for(let i=0;i<3;i++){const orb=document.createElement('span');orb.className=`ambient-orb orb-${i+1}`;ambient.append(orb)}document.body.prepend(ambient);
// Place moving light behind the windows, rather than over their text.
for(const panel of document.querySelectorAll('.case-panel,.project-profiles a')){const halo=document.createElement('div');halo.className='window-aura';panel.before(halo);halo.append(panel)}

async function preloadPortfolio(){
 const loader=$('#page-loader'),bar=loader.querySelector('.loader-track span'),status=loader.querySelector('.loader-status');document.body.classList.add('is-loading');
 const surfaces=[...document.querySelectorAll('header,main,footer')];surfaces.forEach(e=>e.inert=true);
 const urls=[...new Set([d.about?.photo,...d.works.map(w=>w.poster)].filter(Boolean))];let ready=0;
 const images=urls.map(url=>new Promise(resolve=>{const img=new Image();const done=()=>{ready++;const percent=Math.round(ready/urls.length*100);bar.style.transform=`scaleX(${percent/100})`;status.textContent=`Подготавливаем фото и работы · ${percent}%`;resolve()};img.onload=async()=>{try{await img.decode()}catch{}done()};img.onerror=done;img.src=url}));
 await Promise.all([Promise.race([Promise.all(images),new Promise(resolve=>setTimeout(resolve,8000))]),new Promise(resolve=>setTimeout(resolve,1200))]);
 status.textContent='Открываем портфолио';bar.style.transform='scaleX(1)';loader.classList.add('is-finished');document.body.classList.remove('is-loading');surfaces.forEach(e=>e.inert=false);
 setTimeout(()=>loader.remove(),600);
}
preloadPortfolio();

const headline=$('h1'),accent='заметным.';if(headline.textContent.includes(accent)){const parts=headline.textContent.split(accent);const emphasis=document.createElement('span');emphasis.className='headline-accent';emphasis.textContent=accent;headline.replaceChildren(document.createTextNode(parts[0]),emphasis,document.createTextNode(parts.slice(1).join(accent)))}
if(!window.matchMedia('(prefers-reduced-motion: reduce)').matches){
 const glow=document.createElement('span');glow.className='scroll-glow';ambient.append(glow);let queued=false;
 const moveGlow=()=>{glow.style.setProperty('--glow-x',`${Math.sin(scrollY/650)*26}vw`);glow.style.setProperty('--glow-y',`${Math.cos(scrollY/900)*16}vh`);queued=false};
 addEventListener('scroll',()=>{if(!queued){queued=true;requestAnimationFrame(moveGlow)}},{passive:true});moveGlow();
}
