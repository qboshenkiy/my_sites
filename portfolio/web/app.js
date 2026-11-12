const data=window.PORTFOLIO,$=s=>document.querySelector(s),reduced=matchMedia('(prefers-reduced-motion: reduce)');
$('.hero-subtitle').textContent=data.subtitle;
$('h1').replaceChildren(...data.headline.map((line,i)=>{const s=document.createElement('span');s.textContent=line;if(i===data.headline.length-1)s.className='accent';return s}));
document.querySelectorAll('[data-telegram]').forEach(a=>{a.href=data.telegram;a.target='_blank';a.rel='noopener noreferrer'});$('.contact-handle').textContent=data.telegramLabel;
const dialog=$('dialog');$('.dialog-close').onclick=()=>dialog.close();dialog.addEventListener('click',e=>{if(e.target===dialog)dialog.close()});
for(const [i,project] of data.projects.entries()){
 const card=document.createElement('article');card.className='project-card';
 const top=document.createElement('div');top.className='project-top';const index=document.createElement('span');index.textContent=`0${i+1} / ${project.type}`;const arrow=document.createElement('a');arrow.href=project.url;arrow.target='_blank';arrow.rel='noopener noreferrer';arrow.textContent='↗';arrow.setAttribute('aria-label',`Открыть ${project.name}`);top.append(index,arrow);
 const frame=document.createElement('div');frame.className='project-frame '+project.layout;
 const preview=document.createElement('button');preview.className='project-preview';preview.setAttribute('aria-label',`Увеличить превью ${project.name}`);
 const img=document.createElement('img');img.src=project.image;img.alt=`Превью проекта ${project.name}`;img.loading='lazy';img.width=project.layout==='mobile'?500:1280;img.height=project.layout==='mobile'?1000:800;
 const hint=document.createElement('span');hint.className='preview-hint';hint.textContent='Рассмотреть ↗';preview.append(img,hint);frame.append(preview);
 if(project.layout==='mobile'){const mark=document.createElement('span');mark.className='project-watermark';mark.textContent='SMM';mark.setAttribute('aria-hidden','true');frame.append(mark)}
 const title=document.createElement('h3');const link=document.createElement('a');link.href=project.url;link.target='_blank';link.rel='noopener noreferrer';link.textContent=project.name+' ↗';title.append(link);
 const line=document.createElement('p');line.className='project-line';line.textContent=project.line;
 const tags=document.createElement('div');tags.className='tags';for(const value of project.tags){const t=document.createElement('span');t.textContent=value;tags.append(t)}
 card.append(top,frame,title,line,tags);$('.project-grid').append(card);
 preview.onclick=()=>{dialog.querySelector('img').src=project.image;dialog.querySelector('img').alt=`Превью ${project.name}`;dialog.querySelector('h3').textContent=project.name;dialog.querySelector('a').href=project.url;dialog.showModal()};
}
let motionEnabled=!reduced.matches;try{if(localStorage.getItem('vano-motion')==='off')motionEnabled=false}catch{}
function setMotion(){document.documentElement.classList.toggle('motion-off',!motionEnabled);$('.motion-toggle').setAttribute('aria-pressed',String(motionEnabled));$('.motion-toggle').textContent=motionEnabled?'Анимация: вкл.':'Анимация: выкл.'}
setMotion();$('.motion-toggle').onclick=()=>{motionEnabled=!motionEnabled;setMotion();try{localStorage.setItem('vano-motion',motionEnabled?'on':'off')}catch{}};
if('IntersectionObserver' in window){const observer=new IntersectionObserver(entries=>entries.forEach(e=>{if(e.isIntersecting){e.target.classList.add('shown');observer.unobserve(e.target)}}),{threshold:.12});document.querySelectorAll('.section-intro,.project-card,#contact').forEach(e=>{e.classList.add('reveal');observer.observe(e)})}
let scrollQueued=false;const update=()=>{const range=document.documentElement.scrollHeight-innerHeight;$('.reading-progress').style.transform=`scaleX(${range>0?scrollY/range:0})`;if(motionEnabled){$('.scroll-light').style.transform=`translate3d(${Math.sin(scrollY/650)*24}vw,${Math.cos(scrollY/850)*15}vh,0)`}scrollQueued=false};addEventListener('scroll',()=>{if(!scrollQueued){scrollQueued=true;requestAnimationFrame(update)}},{passive:true});addEventListener('resize',update);update();
if(matchMedia('(pointer:fine)').matches){document.querySelectorAll('.project-card').forEach(card=>{card.addEventListener('pointermove',e=>{if(!motionEnabled)return;const r=card.getBoundingClientRect();card.style.setProperty('--tilt-x',`${-(e.clientY-r.y-r.height/2)/r.height*3}deg`);card.style.setProperty('--tilt-y',`${(e.clientX-r.x-r.width/2)/r.width*3}deg`)});card.addEventListener('pointerleave',()=>{card.style.setProperty('--tilt-x','0deg');card.style.setProperty('--tilt-y','0deg')})})}
(async()=>{const loader=$('.loader'),bar=$('.loader-track i');let loaded=0;const images=data.projects.map(p=>new Promise(resolve=>{const im=new Image();const finish=()=>{loaded++;bar.style.transform=`scaleX(${loaded/data.projects.length})`;resolve()};im.onload=async()=>{try{await im.decode()}catch{}finish()};im.onerror=finish;im.src=p.image}));await Promise.all([Promise.race([Promise.all(images),new Promise(r=>setTimeout(r,6500))]),new Promise(r=>setTimeout(r,900))]);document.body.classList.add('ready');loader.classList.add('done');setTimeout(()=>loader.remove(),650)})();
