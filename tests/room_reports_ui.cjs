const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true});const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.REPORT_TEST_URL);await page.click('[data-action="account"]');await page.click('[data-action="legacy-login"]');
  await page.fill('#auth-form [name=password]','testing-admin-password');await page.click('#auth-form [type=submit]');
  await page.waitForSelector('[data-action="dashboard"]');await page.evaluate(()=>dashboard('sessions'));
  await page.waitForSelector('.report-session');assert.match(await page.textContent('.report-session-grid'),/Открыть ведомость/);
  await page.click(`[data-action="link-participants"][data-id="${process.env.REPORT_ROOM_ID}"]`);
  await page.waitForSelector('#report-player-list');assert.match(await page.textContent('#report-player-list'),/75%/);
  const first=page.locator('[data-report-player]').first();await first.locator('[data-action="report-unlink"]').click();
  await first.locator('[data-action="report-choose"]').click();await page.fill('#report-account-search','Анна');
  await page.locator('[data-pick-account]').click();await page.waitForSelector('.report-picker',{state:'detached'});
  assert.match(await first.textContent(),/Анна/);
  const folder=path.join(__dirname,'../dist/community-preview');fs.mkdirSync(folder,{recursive:true});
  for(const width of [1280,390,320]){
   await page.setViewportSize({width,height:900});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'report page overflow '+width);
   await page.screenshot({path:path.join(folder,`game-report-${width}.png`),fullPage:true});
  }
  await page.locator('.report-menu-button').click();assert.equal(await page.locator('[data-action="participants"]').isVisible(),true);
  await page.locator('.report-menu-button').click();assert.equal(await page.locator('[data-action="participants"]').isVisible(),false);
  await page.click('[data-action="report-save"]');await page.waitForFunction(()=>document.querySelector('#report-save-state')?.textContent==='Ведомость сохранена');
  await page.click('[data-action="report-open-results"]');await page.waitForSelector('.assessment-list');
  assert.match(await page.textContent('.assessment-list'),/Из игры/);assert.match(await page.textContent('.assessment-list'),/75%/);
  assert.deepEqual(errors,[]);console.log('PASS: report history, account chooser, reassignment, automatic grade sheet and 320/390/1280px layouts');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
