const { chromium } = require('playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

(async () => {
  const browser = await chromium.launch({headless:true});
  try {
    const page = await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
    const errors = [];
    page.on('pageerror', error => errors.push(error.message));
    await page.goto(process.env.TIMELINE_TEST_URL + '/auth/login-page');
    const login = await page.evaluate(async ({name,password}) => {
      const form = new FormData(document.querySelector('form'));
      form.set('login',name); form.set('password',password);
      return (await fetch('/auth/login-page',{method:'POST',body:form,headers:{'X-Requested-With':'XMLHttpRequest'}})).json();
    },{name:process.env.COMPLETION_USER,password:process.env.ADMIN_PASSWORD});
    assert.ok(login.success);
    await page.goto(process.env.TIMELINE_TEST_URL + '/rooms/play/' + process.env.COMPLETION_ROOM);
    await page.waitForFunction(() => document.querySelector('#turn-message').textContent.includes('Рука завершена'));
    for (const width of [320,390,1280]) {
      await page.setViewportSize({width,height:844});
      assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Page overflows');
      assert.match(await page.textContent('#selection-hint'),/равные результаты делят место/);
      assert.match(await page.textContent('#table-players'),/Место 1 · ходов 1 · ошибок 0/);
      assert.equal(await page.locator('#confirm-placement').isVisible(),false);
      assert.equal(await page.locator('.hand-card').count(),0);
      if (width===390) {
        const folder=path.join(__dirname,'../build'); fs.mkdirSync(folder,{recursive:true});
        await page.screenshot({path:path.join(folder,'completion-mobile.png'),fullPage:true});
      }
    }
    assert.deepEqual(errors,[]);
    console.log('PASS: completed player mobile/desktop spectator UI, ranking and no play controls');
  } finally { await browser.close(); }
})().catch(error=>{console.error(error);process.exitCode=1;});
