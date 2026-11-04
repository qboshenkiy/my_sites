'use strict';
window.TelegramNotes=(()=>{
 const params=new URLSearchParams(location.hash.slice(1)),raw=params.get('tgWebAppData')||new URLSearchParams(location.search).get('tgWebAppData')||'';
 let setup=false;
 async function sdk(){if(window.Telegram?.WebApp)return window.Telegram.WebApp;if(!raw)return null;return new Promise(resolve=>{const s=document.createElement('script');s.src='https://telegram.org/js/telegram-web-app.js';s.onload=()=>resolve(window.Telegram?.WebApp||null);s.onerror=()=>resolve(null);document.head.append(s)})}
 async function autoLogin(api){const tg=await sdk();if(tg&&!setup){setup=true;tg.ready();tg.expand();try{tg.setHeaderColor?.('#fbfaf7');tg.setBackgroundColor?.('#fbfaf7');if(tg.isVersionAtLeast?.('7.7'))tg.disableVerticalSwipes?.()}catch{}tg.BackButton?.onClick(()=>document.getElementById('back')?.click());window.addEventListener('notes-editor-state',e=>{if(e.detail.editing)tg.BackButton?.show();else tg.BackButton?.hide()});const resize=()=>{if(tg.viewportStableHeight)document.documentElement.style.setProperty('--app-height',tg.viewportStableHeight+'px')};tg.onEvent('viewportChanged',resize);resize();}
  const data=tg?.initData||raw;if(!data)return false;try{await api('/api/telegram/login',{init_data:data});return true}catch(error){const el=document.getElementById('toast');if(el){el.textContent=error.message;el.hidden=false}return false}}
 return {autoLogin,isMini:()=>!!raw||!!window.Telegram?.WebApp?.initData};
})();
