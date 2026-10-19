// Reuse the participant's existing marathon login, including Telegram login.
const pulseRequest = new URL(location.href).searchParams;
const pulseState = pulseRequest.get('pulse_state'), pulseChallenge = pulseRequest.get('pulse_challenge');
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
