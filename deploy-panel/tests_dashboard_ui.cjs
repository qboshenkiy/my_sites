// Start preview.py first. All deployment actions stay disabled in this browser test.
const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true});const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000}});page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.GITDECK_TEST_URL||'http://127.0.0.1:8121/');
  assert.equal(await page.locator('#deck-nav').isVisible(),false);
  await page.fill('#password','gitdeck-demo-2026');await page.click('#login-form button');
  await page.waitForSelector('#deck-overview-cpu svg');
  assert.equal(await page.locator('[role=tab][aria-selected=true]').textContent(),'◈Обзор');
  assert.match(await page.textContent('#deck-overview-metrics'),/Процессор/);
  const folder=path.resolve(__dirname,'../dist/gitdeck-preview');fs.mkdirSync(folder,{recursive:true});
  for(const width of [1440,390,320]){
   await page.setViewportSize({width,height:900});
   for(const tab of ['overview','projects','server','containers','logs']){
    await page.locator('#deck-tab-'+tab).click();
    if(tab==='logs')await page.waitForFunction(()=>document.querySelector('#deck-log-output')?.textContent.includes('Деможурнал'));
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'overflow '+width+' '+tab);
    if(width!==320)await page.screenshot({path:path.join(folder,`${tab}-${width}.png`),fullPage:true});
   }
  }
  await page.locator('#deck-tab-server').click();await page.locator('[data-period="900"]').click();
  await page.waitForFunction(()=>deckMetrics?.period===900);
  await page.locator('#deck-tab-projects').click();await page.fill('#deck-project-search','Марафон');
  assert.equal(await page.locator('#cards .card:not(.hidden)').count(),1);
  await page.locator('#cards .card:not(.hidden) [data-config]').click();
  assert.equal(await page.locator('#module-dialog').isVisible(),true);
  await page.locator('#module-dialog [data-close]').click();
  await page.fill('#deck-project-search','not-a-project');assert.equal(await page.locator('#deck-project-empty').isVisible(),true);
  await page.fill('#deck-project-search','');
  await page.locator('#deck-tab-containers').click();await page.fill('#deck-container-search','marathon');
  assert.equal(await page.locator('#deck-container-table tbody tr').count(),2);
  await page.locator('#deck-container-problems').check();assert.match(await page.textContent('#deck-container-table'),/По выбранному фильтру/);
  await page.locator('#deck-tab-logs').click();await page.locator('#deck-log-auto').uncheck();
  assert.match(await page.textContent('#deck-log-freshness'),/Пауза/);
  await page.route('**/api/runtime-log?*',route=>route.fulfill({contentType:'application/json',body:JSON.stringify({log:'INFO ready\nERROR <img src=x onerror=alert(1)>\nWARNING test\n',updated_at:Date.now()/1000})}));
  await page.locator('#deck-log-refresh').click();await page.waitForFunction(()=>document.querySelector('#deck-log-output').textContent.includes('<img'));
  assert.equal(await page.locator('#deck-log-output img').count(),0);
  await page.locator('#deck-log-errors-only').check();assert.doesNotMatch(await page.textContent('#deck-log-output'),/INFO ready/);
  await page.fill('#deck-log-search','WARNING');assert.equal((await page.textContent('#deck-log-output')).trim(),'WARNING test');
  // Navigation is keyboard-accessible and tab choice survives a browser reload.
  await page.locator('#deck-tab-logs').focus();await page.keyboard.press('Home');assert.equal(await page.locator('#deck-tab-overview').getAttribute('aria-selected'),'true');
  await page.locator('#deck-tab-server').click();await page.reload();await page.waitForSelector('#deck-server-chart-cpu svg');
  assert.equal(await page.locator('#deck-tab-server').getAttribute('aria-selected'),'true');
  assert.deepEqual(errors,[]);console.log('PASS: GitDeck tabs, charts/ranges, mobile 320/390/1440px, project forms, Docker filters, searchable text-only logs, pause and keyboard navigation');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
