(()=>{
  if(!('serviceWorker'in navigator)||location.protocol!=='https:'&&location.hostname!=='localhost'&&location.hostname!=='127.0.0.1')return;
  const standalone=matchMedia('(display-mode: standalone)').matches||navigator.standalone===true;
  if(standalone){document.documentElement.classList.add('pwa-installed');}
  let deferred=null,registration=null,notice=null,refreshing=false;
  const mobile=/Android|iPhone|iPad|iPod/i.test(navigator.userAgent);
  function hide(){if(notice)notice.remove();notice=null;try{localStorage.setItem('pwa-dismissed-until',String(Date.now()+7*86400000));}catch{}}
  function show(kind='install'){
    if(standalone)return;
    if(!document.getElementById('pwa-assist-style')){const style=document.createElement('style');style.id='pwa-assist-style';style.textContent='.pwa-assist{position:fixed;z-index:2147483000;left:50%;bottom:calc(14px + env(safe-area-inset-bottom));transform:translateX(-50%);width:min(440px,calc(100vw - 24px));display:flex;align-items:center;gap:10px;padding:12px 14px;background:#1c2433;color:#fff;border:1px solid #7f71c8;border-radius:14px;box-shadow:0 12px 36px #0005;font:14px/1.35 system-ui,sans-serif}.pwa-assist>span{flex:1;min-width:0}.pwa-assist strong,.pwa-assist small{display:block}.pwa-assist small{color:#c1c5d0;font-size:11px;margin-top:3px}.pwa-assist button{border:0;border-radius:9px;padding:10px 12px;background:#a99aff;color:#17132a;font-weight:700;white-space:nowrap;cursor:pointer}.pwa-assist button[data-pwa-dismiss]{background:transparent;color:#fff;padding:6px 8px;font-size:18px}';document.head.append(style);}
    if(!notice){notice=document.createElement('aside');notice.className='pwa-assist';notice.setAttribute('role','status');document.body.append(notice);}
    notice.innerHTML=kind==='update'?'<span><strong>Доступно обновление</strong><small>Установите свежую версию приложения.</small></span><button type="button" data-pwa-update>Обновить</button><button type="button" data-pwa-dismiss aria-label="Закрыть">×</button>':'<span><strong>Установить приложение</strong><small>Открывайте с главного экрана.</small></span><button type="button" data-pwa-install>Установить</button><button type="button" data-pwa-dismiss aria-label="Закрыть">×</button>';
  }
  function updateAvailable(){if(registration?.waiting)show('update');}
  function maybeInstall(){if(deferred||mobile)show('install');}
  window.addEventListener('beforeinstallprompt',event=>{event.preventDefault();deferred=event;maybeInstall();});
  window.addEventListener('appinstalled',()=>{deferred=null;if(notice)notice.remove();notice=null;});
  document.addEventListener('click',async event=>{
    if(event.target.closest('[data-pwa-dismiss]'))return hide();
    if(event.target.closest('[data-pwa-install]')){
      if(deferred){deferred.prompt();await deferred.userChoice;deferred=null;if(notice)notice.remove();notice=null;}
      else if(mobile)alert(/iPhone|iPad|iPod/i.test(navigator.userAgent)?'Нажмите «Поделиться», затем «На экран Домой».':'Откройте меню браузера и выберите «Установить приложение» или «Добавить на главный экран».');
    }
    if(event.target.closest('[data-pwa-update]')&&registration?.waiting){registration.waiting.postMessage({type:'SKIP_WAITING'});}
  });
  navigator.serviceWorker.addEventListener('controllerchange',()=>{if(refreshing)return;refreshing=true;location.reload();});
  navigator.serviceWorker.register('/service-worker.js',{scope:'/'}).then(reg=>{
    registration=reg;updateAvailable();
    reg.addEventListener('updatefound',()=>{const worker=reg.installing;if(!worker)return;worker.addEventListener('statechange',()=>{if(worker.state==='installed'&&navigator.serviceWorker.controller)updateAvailable();});});
    setTimeout(()=>reg.update().catch(()=>{}),60000);
  }).catch(()=>{});
  if(!standalone&&mobile){let dismissed=0;try{dismissed=Number(localStorage.getItem('pwa-dismissed-until')||0);}catch{}if(dismissed<Date.now())setTimeout(maybeInstall,3500);}
})();
