/* Shared install assistance; only a real browser install event enables installation. */
(()=>{
  if(!('serviceWorker' in navigator)||!window.isSecureContext)return;
  const module=document.currentScript?.dataset.pwaApp||'pulse';
  const themes={
    pulse:{name:'Пульс',accent:'#7563e8',surface:'#ffffff',text:'#252333',muted:'#757185',line:'#e5e0f4',button:'#ffffff',icon:'/assets/telegram-avatars/pulse.png'},
    marathon:{name:'Глава',accent:'#315c49',surface:'#fafbf5',text:'#24392e',muted:'#788474',line:'#dce3d3',button:'#ffffff',icon:'/assets/telegram-avatars/marathon.png'},
    chrono:{name:'Chrono Logos',accent:'#d6b77a',surface:'#191e2a',text:'#f1f3f8',muted:'#a7b2c7',line:'#333e52',button:'#211c13',icon:'/assets/img/icons/hrono.png'},
    drawing:{name:'Штрих',accent:'#6552d9',surface:'#fffdf9',text:'#28252f',muted:'#777280',line:'#e4dfed',button:'#ffffff',icon:'/assets/icon.svg'},
    gitdeck:{name:'GitDeck',accent:'#a99aff',surface:'#151c29',text:'#e4eaf5',muted:'#9aa8bd',line:'#303b50',button:'#17132a',icon:'/icon.svg'}
  };
  const theme=themes[module]||themes.pulse;
  const ua=navigator.userAgent;
  const nativeUpdates=/NativeUpdates\/2/.test(ua);
  const workerUrl=module==='gitdeck'?'/service-worker.js':'/index.php?pwa=worker';
  const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  let deferred=null,registration=null,notice=null,noticeKind=null,activatingUpdate=false,installing=false;
  let installTimer=null,updateDismissed=false;
  const dismissalKey='pwa-install-dismissed-until';
  function embedded(){
    const params=new URLSearchParams(location.search);
    const telegram=window.Telegram?.WebApp;
    let framed=false;try{framed=window.top!==window.self;}catch{framed=true;}
    return framed||params.get('miniapp')==='1'||params.has('tgWebAppData')||/tgWebApp(?:Data|Platform|Version)=/i.test(location.hash)
      ||Boolean(telegram?.initData||telegram?.platform&&telegram.platform!=='unknown')
      ||/Telegram|GlavaMarathon|ChronoLogos|;\s*wv\)|\bFBAN\b|\bFBAV\b|Instagram|Line\//i.test(ua)
      ||(/iPhone|iPad|iPod/i.test(ua)&&/AppleWebKit/i.test(ua)&&!/Safari/i.test(ua));
  }
  function removeNotice(){notice?.remove();notice=null;noticeKind=null;}
  function dismissed(){try{return Number(localStorage.getItem(dismissalKey)||localStorage.getItem('pwa-dismissed-until')||0)>Date.now();}catch{return false;}}
  function hide(){
    if(noticeKind==='install'){try{localStorage.setItem(dismissalKey,String(Date.now()+7*86400000));}catch{}}
    else updateDismissed=true;
    removeNotice();
  }
  function addStyle(){
    if(document.getElementById('pwa-assist-style'))return;
    const style=document.createElement('style');style.id='pwa-assist-style';
    style.textContent=`.pwa-menu-action{box-sizing:border-box;display:flex;align-items:center;justify-content:center;gap:8px;width:calc(100% - 24px);margin:12px;min-height:44px;padding:10px 12px;border:1px solid var(--pwa-line);border-radius:12px;background:var(--pwa-surface);color:var(--pwa-accent);font:600 13px/1.35 system-ui,sans-serif;text-decoration:none;cursor:pointer;flex-shrink:0}.pwa-menu-action.pwa-menu-inline{width:auto;margin:4px;white-space:nowrap;font-size:12px}.pwa-install-help{box-sizing:border-box;width:min(400px,calc(100vw - 32px));padding:24px;border:1px solid var(--pwa-line);border-radius:20px;background:var(--pwa-surface);color:var(--pwa-text);font:15px/1.6 system-ui,sans-serif}.pwa-install-help::backdrop{background:#0006}.pwa-install-help h2{font-size:20px;line-height:1.3;margin:0 0 12px;color:var(--pwa-text)}.pwa-install-help p{color:var(--pwa-muted);margin:0 0 20px}.pwa-install-help button{min-height:44px;width:100%;border:0;border-radius:12px;padding:12px;background:var(--pwa-accent);color:var(--pwa-button);font:600 14px system-ui,sans-serif}.pwa-assist{box-sizing:border-box;position:fixed;z-index:900;right:20px;bottom:calc(20px + env(safe-area-inset-bottom));width:min(400px,calc(100vw - 32px));display:grid;grid-template-columns:40px minmax(0,1fr) auto 32px;align-items:center;gap:10px;padding:12px;background:var(--pwa-surface);color:var(--pwa-text);border:1px solid var(--pwa-line);border-radius:18px;box-shadow:0 8px 32px #00000014;font:14px/1.4 system-ui,-apple-system,sans-serif;text-align:left}.pwa-assist img{width:40px;height:40px;border-radius:11px;object-fit:cover}.pwa-assist strong{display:block;color:var(--pwa-text);font-size:14px;font-weight:650}.pwa-assist small{display:block;color:var(--pwa-muted);font-size:11px;margin-top:2px}.pwa-assist button{box-sizing:border-box;position:static;transform:none;margin:0;min-width:44px;min-height:44px;border:0;border-radius:11px;padding:10px 12px;background:var(--pwa-accent);color:var(--pwa-button);font:600 12px/1.2 system-ui,sans-serif;letter-spacing:normal;white-space:nowrap;cursor:pointer;box-shadow:none}.pwa-assist button:focus-visible{outline:2px solid var(--pwa-accent);outline-offset:3px}.pwa-assist button[data-pwa-dismiss]{background:transparent;color:var(--pwa-muted);padding:6px;min-width:32px;font-size:21px;font-weight:400}.pwa-assist button:disabled{opacity:.6;cursor:wait}body.mobile-nav-open .pwa-assist,body:has(dialog[open]) .pwa-assist{display:none}@media(max-width:480px){.pwa-assist{right:12px;bottom:calc(12px + env(safe-area-inset-bottom));width:calc(100vw - 24px);gap:8px;padding:10px;border-radius:15px;grid-template-columns:36px minmax(0,1fr) auto 28px}.pwa-assist img{width:36px;height:36px;border-radius:9px}.pwa-assist strong{font-size:13px}.pwa-assist small{font-size:10px}.pwa-assist button{padding:10px;font-size:12px}.pwa-assist button[data-pwa-dismiss]{min-width:28px}}`;
    document.head.append(style);
  }
  function applyTheme(element){for(const key of ['accent','surface','text','muted','line','button'])element.style.setProperty('--pwa-'+key,theme[key]);}
  function mountInstallAction(){
    if(standalone||embedded()&&!nativeUpdates||document.querySelector('[data-app-install-menu]'))return;
    const host=module==='gitdeck'?document.querySelector('header'):document.querySelector('.sidebar-nav,.sidebar,header .mobile-app-actions,header > div:not(.brand)');
    if(!host)return;
    addStyle();const action=document.createElement(nativeUpdates?'a':'button');
    action.dataset.appInstallMenu='1';action.className='pwa-menu-action';
    if(host.closest('header'))action.classList.add('pwa-menu-inline');
    if(nativeUpdates){action.href='/_app/check-updates';action.textContent='↻ Обновить приложение';}
    else {action.type='button';action.textContent='↓ Установить приложение';}
    if(module==='gitdeck'||module==='drawing')action.textContent=nativeUpdates?'Обновить':'Установить';
    if(window.AppUI&&!host.matches('.mobile-app-actions')){const label=action.textContent.replace(/^[↻↓]\s*/, '');action.innerHTML=window.AppUI.icon(nativeUpdates?'refresh':'download')+'<span>'+label+'</span>';}
    if(host.matches('.mobile-app-actions')){action.title=action.textContent;action.setAttribute('aria-label',action.textContent);action.textContent=nativeUpdates?'↻':'↓';}
    applyTheme(action);host.append(action);
  }
  function installHelp(){
    if(embedded()||standalone)return;
    addStyle();const existing=document.querySelector('.pwa-install-help');if(existing){existing.showModal();return;}
    const dialog=document.createElement('dialog');dialog.className='pwa-install-help';applyTheme(dialog);
    const title=document.createElement('h2');title.textContent='Установить '+theme.name;
    const text=document.createElement('p');
    text.textContent=/iPhone|iPad|iPod/i.test(ua)?'В Safari нажмите «Поделиться» → «На экран Домой» → «Добавить».':/Android/i.test(ua)?'Откройте меню браузера ⋮ → «Установить приложение» или «Добавить на главный экран». Подтвердите установку. Если пункта нет, откройте сайт в Chrome.':'Нажмите значок установки в адресной строке или откройте меню браузера → «Установить приложение». Если пункта нет, используйте Chrome или Edge.';
    const close=document.createElement('button');close.type='button';close.textContent='Понятно';close.addEventListener('click',()=>dialog.close());
    dialog.append(title,text,close);document.body.append(dialog);dialog.addEventListener('close',()=>dialog.remove());dialog.showModal();
  }
  async function install(){
    if(embedded()||standalone||installing)return;
    if(!deferred){installHelp();return;}
    installing=true;const prompt=deferred;deferred=null;
    try{await prompt.prompt();const choice=await prompt.userChoice;if(choice.outcome==='dismissed')hide();else removeNotice();}
    catch{removeNotice();installHelp();}finally{installing=false;}
  }
  function show(kind){
    if(embedded()||kind==='install'&&(standalone||!deferred||dismissed())||kind==='update'&&updateDismissed)return;
    if(kind==='install'&&registration?.waiting)return;
    addStyle();
    if(!notice){notice=document.createElement('aside');notice.className='pwa-assist';notice.setAttribute('role','region');document.body.append(notice);}
    noticeKind=kind;
    applyTheme(notice);
    notice.setAttribute('aria-label',kind==='install'?'Установка приложения':'Обновление приложения');
    notice.innerHTML=`<img src="${theme.icon}" alt="" width="40" height="40"><span><strong>${kind==='update'?'Новая версия':theme.name}</strong><small>${kind==='update'?'Готова к обновлению':'Быстрый вход с главного экрана'}</small></span><button type="button" ${kind==='update'?'data-pwa-update':'data-pwa-install'}>${kind==='update'?'Обновить':'Установить'}</button><button type="button" data-pwa-dismiss aria-label="Отложить">×</button>`;
  }
  function updateAvailable(){if(registration?.waiting)show('update');}
  window.addEventListener('beforeinstallprompt',event=>{
    event.preventDefault();
    if(embedded()||standalone)return;
    deferred=event;mountInstallAction();
    clearTimeout(installTimer);
    installTimer=setTimeout(()=>show('install'),5000);
  });
  window.addEventListener('appinstalled',()=>{deferred=null;clearTimeout(installTimer);removeNotice();});
  document.addEventListener('click',async event=>{
    if(event.target.closest('[data-app-install-menu]')){if(!nativeUpdates){event.preventDefault();install();}return;}
    if(!notice||!notice.contains(event.target))return;
    if(event.target.closest('[data-pwa-dismiss]'))return hide();
    if(event.target.closest('[data-pwa-install]')){
      await install();
    }
    if(event.target.closest('[data-pwa-update]')&&registration?.waiting){activatingUpdate=true;registration.waiting.postMessage({type:'SKIP_WAITING'});event.target.disabled=true;}
  });
  navigator.serviceWorker.addEventListener('controllerchange',()=>{if(activatingUpdate){activatingUpdate=false;location.reload();}});
  navigator.serviceWorker.register(workerUrl,{scope:'/'}).then(reg=>{
    registration=reg;updateAvailable();
    reg.addEventListener('updatefound',()=>{const worker=reg.installing;if(!worker)return;worker.addEventListener('statechange',()=>{if(worker.state==='installed'&&navigator.serviceWorker.controller)updateAvailable();});});
    setTimeout(()=>reg.update().catch(()=>{}),60000);
  }).catch(()=>{});
  if(standalone)document.documentElement.classList.add('pwa-installed');
  mountInstallAction();
  new MutationObserver(mountInstallAction).observe(document.body,{childList:true,subtree:true});
})();
