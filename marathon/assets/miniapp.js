/* The Telegram SDK is loaded only by the dedicated Mini App entry URL. */
(() => {
 const tg=window.Telegram?.WebApp;
 const safe=()=>{
  const area=tg?.safeAreaInset||{},content=tg?.contentSafeAreaInset||{};
  for(const side of ['top','right','bottom','left'])document.documentElement.style.setProperty('--miniapp-safe-'+side,Math.max(0,Number(area[side])||0)+Math.max(0,Number(content[side])||0)+'px');
 };
 window.marathonMiniApp={
  async authenticate(api){
   document.body.classList.add('miniapp');
   if(!tg?.initData)throw Error('Откройте марафон кнопкой «📱 Открыть марафон» в Telegram-боте.');
   tg.ready();tg.expand();safe();
   if(tg.isVersionAtLeast?.('6.1')){tg.setHeaderColor('#315c49');tg.setBackgroundColor('#f8f8f1');}
   if(tg.isVersionAtLeast?.('7.7'))tg.disableVerticalSwipes();
   tg.onEvent('safeAreaChanged',safe);tg.onEvent('contentSafeAreaChanged',safe);
   // Keep initData in memory only; it must never enter URLs, storage or logs.
   await api('telegram_miniapp_login',{init_data:tg.initData});
   const back=async()=>{const dialog=document.querySelector('dialog[open]');if(dialog){dialog.close();return;}try{await home();}catch(error){toast(error.message);}};
   tg.BackButton?.onClick(back);
   const navigation=()=>{
    const ownProfile=view==='profile'&&profileData?.user?.id===boot?.user?.id;
    const atHome=boot?.user?.role==='participant'?ownProfile:view==='dashboard';
    if(document.querySelector('dialog[open]')||!atHome)tg.BackButton?.show();else tg.BackButton?.hide();
   };
   new MutationObserver(navigation).observe(document.body,{childList:true,subtree:true,attributes:true,attributeFilter:['open']});
   document.addEventListener('click',event=>{
    const link=event.target.closest('a[href]');if(!link||event.defaultPrevented)return;
    const url=new URL(link.href,location.href);
    if(url.protocol==='https:'&&(url.hostname==='t.me'||url.hostname==='telegram.me')){event.preventDefault();tg.openTelegramLink(url.href);}
    else if((url.protocol==='https:'||url.protocol==='http:')&&url.origin!==location.origin){event.preventDefault();tg.openLink(url.href);}
   });
  }
 };
})();
