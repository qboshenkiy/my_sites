(() => {
  const root = document.documentElement;
  const system = matchMedia('(prefers-color-scheme: dark)');
  const key = 'pulse-color-theme';
  let preference;
  try { preference = localStorage.getItem(key); } catch {}
  const lightIcon = '<svg class="ui-icon" width="20" height="20" viewBox="0 0 24 24" aria-hidden="true"><circle cx="12" cy="12" r="4"/><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.5 1.5m11 11L19 19M19 5l-1.5 1.5m-11 11L5 19"/></svg>';
  function update() {
    const dark = (preference === 'dark') || (preference !== 'light' && system.matches);
    root.dataset.pulseTheme = dark ? 'dark' : 'light';
    document.querySelector('meta[name=theme-color]')?.setAttribute('content', dark ? '#121218' : '#f7f7fb');
    for (const button of document.querySelectorAll('.pulse-theme-toggle')) {
      const label = dark ? 'Включить светлую тему' : 'Включить тёмную тему';
      button.title = label;
      button.setAttribute('aria-label', label);
      button.setAttribute('aria-pressed', String(dark));
      if (button.dataset.theme !== root.dataset.pulseTheme) {
        button.dataset.theme = root.dataset.pulseTheme;
        button.innerHTML = dark ? lightIcon : window.AppUI?.icon('moon') || '☾';
      }
    }
  }
  function placeToggle() {
    const host = document.querySelector('.topbar-actions, .public-page > header, .self-test-page > header, .game-header');
    if (!host || host.closest('.projector-screen') || host.querySelector('.pulse-theme-toggle')) return;
    const button = document.createElement('button');
    button.className = 'icon-button pulse-theme-toggle';
    button.type = 'button';
    host.append(button);
    update();
  }
  root.dataset.pulseTheme = (preference === 'dark' || (preference !== 'light' && system.matches)) ? 'dark' : 'light';
  system.addEventListener?.('change', update);
  window.addEventListener('storage', event=>{if (event.key === key || event.key === null) { preference = event.newValue; update(); }});
  document.addEventListener('click', event=>{
    if (!event.target.closest('.pulse-theme-toggle')) return;
    preference = root.dataset.pulseTheme === 'dark' ? 'light' : 'dark';
    try { localStorage.setItem(key, preference); } catch {}
    update();
  });
  document.addEventListener('DOMContentLoaded', ()=>{
    const app = document.querySelector('#app');
    if (!app) return;
    new MutationObserver(placeToggle).observe(app,{childList:true});
    placeToggle();
    update();
  }, {once:true});
})();
