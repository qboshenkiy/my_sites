// Reuse the participant's existing marathon login, including Telegram login.
const pulseRequest = new URL(location.href).searchParams;
const pulseState = pulseRequest.get('pulse_state'), pulseChallenge = pulseRequest.get('pulse_challenge');
const marathonShellWithoutPulse=shell;
shell=function(...args){
  marathonShellWithoutPulse(...args);
  const sidebar=document.querySelector('.sidebar');if(!sidebar||!boot.user)return;
  const destination=boot.pulse?.url;
  const controls=document.createElement('div');controls.className='pulse-integration-actions';
  if(destination){const link=document.createElement('a');link.className='nav';link.href=destination;link.target='_blank';link.rel='noopener noreferrer';link.textContent='ϟ Открыть Пульс';controls.append(link);}
  if(boot.user.role==='admin'){
    const button=document.createElement('button');button.className='nav';button.textContent='ϟ Передать участников в Пульс';controls.append(button);
    button.onclick=async()=>{
      if(!boot.pulse?.configured){toast('Сначала в GitDeck на карточке Пульса нажмите «Подключить марафон».');return;}
      button.disabled=true;
      try{const result=await api('pulse_export',{});toast(`В Пульс передано участников: ${result.imported}. Существующие аккаунты обновлены.`);}catch(error){toast(error.message);}finally{button.disabled=false;}
    };
  }
  sidebar.querySelector('.sidebar-person')?.before(controls);
};
if (/^[a-f0-9]{64}$/.test(pulseState||'') && /^[a-f0-9]{64}$/.test(pulseChallenge||'')) {
  const originalHome = home;
  home = async function(...args) {
    if (!boot?.user) return originalHome(...args);
    app.innerHTML = `<div class="loading"><h1>Войти в Пульс</h1><p>Продолжить как <strong>${esc(boot.user.name)}</strong>?</p><p>В Пульс будут переданы ваше имя, роль и идентификатор аккаунта.<br>Результаты чтения и пароль не передаются.</p><button class="primary" id="pulse-continue">Продолжить →</button><p><a href="./">Остаться в марафоне</a></p></div>`;
    document.querySelector('#pulse-continue').onclick=async function(){
      this.disabled=true;
      try { const data=await api('pulse_authorize',{state:pulseState,challenge:pulseChallenge});location.assign(data.url); }
      catch(error){toast(error.message);this.disabled=false;}
    };
  };
}
