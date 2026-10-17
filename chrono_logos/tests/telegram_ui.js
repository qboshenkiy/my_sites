const {chromium} = require('playwright');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');
const base = process.env.TIMELINE_TEST_URL;
function proof(id) {
  const values={auth_date:String(Math.floor(Date.now()/1000)),user:JSON.stringify({id,first_name:'Telegram Player'})};
  const secret=crypto.createHmac('sha256','WebAppData').update(process.env.TELEGRAM_BOT_TOKEN).digest();
  values.hash=crypto.createHmac('sha256',secret).update(Object.keys(values).sort().map(k=>k+'='+values[k]).join('\n')).digest('hex');
  return new URLSearchParams(values).toString();
}
(async()=>{
  const browser=await chromium.launch({headless:true});
  const errors=[];
  const folder=path.resolve(__dirname,'../build');fs.mkdirSync(folder,{recursive:true});
  async function context(id){
    const ctx=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    await ctx.route('https://telegram.org/js/telegram-web-app.js',route=>route.fulfill({contentType:'application/javascript',body:`window.Telegram={WebApp:{initData:${JSON.stringify(proof(id))},ready(){},expand(){},isVersionAtLeast(){return true},setHeaderColor(){},setBackgroundColor(){},disableVerticalSwipes(){},onEvent(){},contentSafeAreaInset:{top:12,bottom:8},BackButton:{show(){},onClick(){}}}};`}));
    const page=await ctx.newPage();page.on('pageerror',error=>errors.push(error.message));return page;
  }
  try {
    const page=await context(30303);
    await page.goto(base+'/telegram/app');
    await page.waitForSelector('#telegram-entry-actions:not([hidden])');
    await page.screenshot({path:path.join(folder,'telegram-entry.png'),fullPage:true});
    await page.locator('[data-telegram-action=create]').click();
    await page.waitForURL('**/rooms');
    await page.goto(base+'/account/settings');
    assert.ok(await page.locator('[data-telegram-action=unlink]').isVisible());
    assert.equal(await page.evaluate(()=>localStorage.length),0);
    const existing=await context(40404);
    await existing.goto(base+'/telegram/app');
    await existing.waitForSelector('#telegram-entry-actions:not([hidden])');
    await existing.locator('a[href="/auth/login-page"]').click();
    await existing.waitForURL('**/auth/login-page');
    await existing.waitForSelector('form');
    const data=await existing.evaluate(async password=>{
      const form=new FormData(document.querySelector('form'));form.set('login','reader_a');form.set('password',password);
      return(await fetch('/auth/login-page',{method:'POST',body:form,headers:{'X-Requested-With':'XMLHttpRequest'}})).json();
    },process.env.ADMIN_PASSWORD);
    assert.ok(data.success);
    await existing.goto(base+'/account/settings');
    await existing.locator('[data-telegram-action=link]').click();
    await existing.waitForSelector('[data-telegram-action=unlink]');
    assert.ok((await existing.textContent('body')).includes('reader_a'));
    assert.deepEqual(errors,[]);
    console.log('PASS: mobile Mini App entry, explicit registration and linking an existing account');
  } finally {await browser.close()}
})().catch(error=>{console.error(error);process.exitCode=1});
