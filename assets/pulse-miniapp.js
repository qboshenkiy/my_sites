(()=>{
  const app=window.Telegram?.WebApp;
  if(!app?.initData)return;
  app.ready();app.expand();
})();
