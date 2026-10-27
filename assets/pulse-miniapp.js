(()=>{
  const app=window.Telegram?.WebApp;
  if(!app?.initData)return;
  document.documentElement.classList.add('pulse-miniapp');
  function viewport(){
    const root=document.documentElement;
    const height=Number(app.viewportStableHeight||app.viewportHeight);
    if(height>0)root.style.setProperty('--pulse-viewport-height',height+'px');
    for(const edge of ['top','right','bottom','left']){
      const inset=Math.max(Number(app.safeAreaInset?.[edge])||0,Number(app.contentSafeAreaInset?.[edge])||0);
      root.style.setProperty('--pulse-safe-'+edge,inset+'px');
    }
  }
  app.ready();app.expand();viewport();
  for(const event of ['viewportChanged','safeAreaChanged','contentSafeAreaChanged'])app.onEvent?.(event,viewport);
  window.addEventListener('resize',viewport);
})();
