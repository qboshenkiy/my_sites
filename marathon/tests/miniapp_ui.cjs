const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const page=await context.newPage(),errors=[];page.on('pageerror',e=>errors.push(e.message));
  const mock=`window.telegramCalls=[];window.Telegram={WebApp:{initData:${JSON.stringify(process.env.MINIAPP_PROOF)},safeAreaInset:{bottom:16},contentSafeAreaInset:{top:8},ready(){telegramCalls.push('ready')},expand(){},isVersionAtLeast(){return true},setHeaderColor(){},setBackgroundColor(){},disableVerticalSwipes(){},onEvent(){},openLink(){},openTelegramLink(){},BackButton:{onClick(fn){window.telegramBack=fn},show(){telegramCalls.push('showBack')},hide(){}}}};`;
  await context.route('https://telegram.org/js/telegram-web-app.js',route=>route.fulfill({contentType:'application/javascript',body:mock}));
  await page.goto(process.env.MINIAPP_TEST_URL+'index.php?miniapp=1');
  await page.waitForSelector('.reader-heading');
  assert.ok((await page.locator('.reader-heading').textContent()).includes('Reader'));
  assert.ok(await page.evaluate(()=>document.body.classList.contains('miniapp')));
  assert.equal(await page.evaluate(()=>getComputedStyle(document.documentElement).getPropertyValue('--miniapp-safe-top')),'8px');
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1));
  assert.ok(!(await page.content()).includes(process.env.TELEGRAM_BOT_TOKEN));
  assert.equal(await page.evaluate(()=>localStorage.length),0);
  await page.locator('.featured-week [data-v3=complete]').tap();
  await page.waitForSelector('#complete-week-form');
  await page.evaluate(()=>window.telegramBack());
  await page.waitForFunction(()=>!document.querySelector('dialog[open]'));
  await page.locator('.featured-week [data-v3=complete]').tap();
  await page.locator('#complete-week-form button[type=submit]').tap();
  await page.waitForFunction(()=>!document.querySelector('dialog[open]'));
  await page.waitForFunction(()=>document.querySelector('.featured-week .weekly-progress strong')?.textContent.includes('7'));
  const plain=await context.newPage();await plain.goto(process.env.MINIAPP_TEST_URL);
  assert.equal(await plain.locator('script[src*=telegram-web-app]').count(),0);
  const empty=await browser.newContext({viewport:{width:390,height:844}});
  await empty.route('https://telegram.org/js/telegram-web-app.js',route=>route.fulfill({body:'window.Telegram={WebApp:{initData:""}};'}));
  const outside=await empty.newPage();await outside.goto(process.env.MINIAPP_TEST_URL+'index.php?miniapp=1');
  await outside.waitForFunction(()=>document.querySelector('.loading')?.textContent.includes('Откройте марафон'));
  assert.equal(await outside.locator('.reader-heading').count(),0);
  assert.deepEqual(errors,[]);
  console.log('PASS: Mini App automatic login, safe area, phone width, Telegram BackButton, real completion, no proof/token storage and ordinary-site/missing-SDK fallbacks');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
