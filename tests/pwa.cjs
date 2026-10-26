const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const source = fs.readFileSync('native-common/pwa-assist.js', 'utf8');
(async () => {
  const browser = await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_BROWSER?{executablePath:process.env.PLAYWRIGHT_BROWSER}:{})});
  const contexts=[];
  async function open(options={}) {
    const context=await browser.newContext({viewport:{width:390,height:800},...(options.ua?{userAgent:options.ua}:{})});contexts.push(context);
    await context.route('https://pwa.test/**',route=>route.request().url().endsWith('.png')?route.fulfill({contentType:'image/png',body:fs.readFileSync('assets/telegram-avatars/marathon.png')}):route.fulfill({contentType:'text/html; charset=utf-8',body:`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><body><h1>App</h1>${options.menu?'<aside class="sidebar"></aside>':''}<script data-pwa-app="${options.module||'marathon'}">${source}</script></body>`}));
    await context.addInitScript(({standalone,waiting,sdk})=>{
      window.matchMedia=()=>({matches:standalone});
      if(sdk)window.Telegram={WebApp:{initData:'test',platform:'android'}};
      window.promptCalls=0;window.updateCalls=0;window.reloadCalls=0;
      const registration={waiting:waiting?{postMessage(){window.updateCalls++;}}:null,addEventListener(){},update(){return Promise.resolve();}};
      Object.defineProperty(navigator,'serviceWorker',{value:{register:()=>Promise.resolve(registration),addEventListener(){}}});
    },{standalone:!!options.standalone,waiting:!!options.waiting,sdk:!!options.sdk});
    const page=await context.newPage();await page.clock.install();
    await page.goto('https://pwa.test/'+(options.suffix||''));
    return page;
  }
  async function ready(page,outcome='accepted') {
    await page.evaluate(outcome=>{const event=new Event('beforeinstallprompt',{cancelable:true});event.prompt=async()=>{window.promptCalls++;};event.userChoice=Promise.resolve({outcome});window.dispatchEvent(event);},outcome);
    await page.clock.fastForward(5100);
  }
  try {
    const plain=await open();await plain.clock.fastForward(10000);assert.equal(await plain.locator('.pwa-assist').count(),0,'unsupported browser has no misleading install button');
    for(const options of [
      {ua:'Mozilla/5.0 (Linux; Android 14; K; wv) AppleWebKit/537.36 Chrome/130.0 Mobile Safari/537.36'},
      {ua:'Mozilla/5.0 Telegram Android'}, {suffix:'?miniapp=1'}, {suffix:'#tgWebAppData=test'}, {sdk:true},
      {ua:'Mozilla/5.0 GlavaMarathon/1.0'}, {ua:'Mozilla/5.0 (iPhone) AppleWebKit/605.1.15 Mobile/15E148'}
    ]) {const page=await open(options);await ready(page);assert.equal(await page.locator('.pwa-assist').count(),0,JSON.stringify(options));}
    const menu=await open({menu:true});assert.equal(await menu.locator('[data-app-install-menu]').count(),1);await menu.click('[data-app-install-menu]');assert.equal(await menu.locator('.pwa-install-help[open]').count(),1);await menu.locator('.pwa-install-help button').click();await ready(menu);await menu.click('[data-app-install-menu]');assert.equal(await menu.evaluate(()=>window.promptCalls),1);
    const native=await open({menu:true,ua:'Mozilla/5.0 GlavaMarathon/1.0 NativeUpdates/2'});assert.equal(await native.locator('[data-app-install-menu]').getAttribute('href'),'/_app/check-updates');await ready(native);assert.equal(await native.locator('.pwa-assist').count(),0);
    const telegramMenu=await open({menu:true,suffix:'?miniapp=1'});assert.equal(await telegramMenu.locator('[data-app-install-menu]').count(),0);
    const installed=await open({standalone:true});await ready(installed);assert.equal(await installed.locator('.pwa-assist').count(),0);
    for(const [module,color] of [['marathon','rgb(49, 92, 73)'],['pulse','rgb(117, 99, 232)'],['chrono','rgb(214, 183, 122)'],['drawing','rgb(101, 82, 217)'],['gitdeck','rgb(169, 154, 255)']]){
      const page=await open({module});await ready(page);assert.equal(await page.locator('[data-pwa-install]').evaluate(el=>getComputedStyle(el).backgroundColor),color);
      if(module==='marathon')await page.screenshot({path:'storage/pwa-marathon-preview.png'});const bounds=await page.locator('.pwa-assist').boundingBox();assert.ok(bounds.x>=0&&bounds.x+bounds.width<=390.5&&bounds.height<110,'compact card fits phone: '+module+' '+JSON.stringify(bounds));
      if(module==='marathon'){await page.screenshot({path:'storage/pwa-marathon-preview.png'});}
      await page.click('[data-pwa-install]');assert.equal(await page.evaluate(()=>window.promptCalls),1);assert.equal(await page.locator('.pwa-assist').count(),0);
    }
    const dismissed=await open();await ready(dismissed);await dismissed.click('[data-pwa-dismiss]');await ready(dismissed);assert.equal(await dismissed.locator('.pwa-assist').count(),0,'dismissal persists across another browser event');
    const update=await open({standalone:true,waiting:true});assert.equal(await update.locator('[data-pwa-update]').count(),1,'installed PWA can receive an update');await update.click('[data-pwa-update]');assert.equal(await update.evaluate(()=>window.updateCalls),1);
    const tgUpdate=await open({waiting:true,suffix:'?miniapp=1'});assert.equal(await tgUpdate.locator('.pwa-assist').count(),0);
    console.log('PASS: Telegram/native suppression, real installation, all module colors, mobile layout, dismissal and installed PWA updates');
  } finally {for(const context of contexts)await context.close();await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
