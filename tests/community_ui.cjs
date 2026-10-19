const {chromium}=require('playwright');
const assert=require('node:assert/strict');
const fs=require('node:fs');const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true});const errors=[];
 try{
  const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.COMMUNITY_TEST_URL);
  await page.waitForSelector('[data-action="account"]');
  await page.click('[data-action="account"]');await page.click('[data-action="legacy-login"]');
  await page.fill('#auth-form input[name=password]','testing-admin-password');await page.click('#auth-form [type=submit]');
  await page.waitForSelector('[data-action="assessments"]');await page.click('[data-action="assessments"]');
  await page.waitForSelector('[data-action="new-assessment"]');await page.click('[data-action="new-assessment"]');
  await page.waitForSelector('#assessment-form');
  await page.fill('[name=title]','Проверка ведомости с телефона');
  await page.fill('[name=held_on]','2026-10-19');
  await page.fill('#max-points','1000');
  const rows=page.locator('[data-grade-user]');
  const anna=rows.filter({has:page.locator('td:first-child',{hasText:'Анна'})});
  const boris=rows.filter({has:page.locator('td:first-child',{hasText:'Борис'})});
  await anna.locator('[data-points]').fill('750');await boris.locator('[data-points]').fill('0');
  assert.equal(await anna.locator('output').textContent(),'75%');assert.equal(await boris.locator('output').textContent(),'0%');
  for(const width of [320,390,1280]){
   await page.setViewportSize({width,height:900});
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'page overflow');
   assert.equal(await page.locator('[data-action="assessments"]').first().isVisible(),true);
  }
  await page.setViewportSize({width:390,height:844});
  await page.locator('.grade-table').evaluate(table=>{table.parentElement.scrollLeft=0;});
  await page.evaluate(()=>new Promise(resolve=>requestAnimationFrame(()=>requestAnimationFrame(resolve))));
  assert.equal(await anna.isVisible(),true);
  assert.equal(await anna.locator('[data-points]').isVisible(),true);
  const folder=path.join(__dirname,'../dist/community-preview');fs.mkdirSync(folder,{recursive:true});
  await page.screenshot({path:path.join(folder,'marks-mobile.png'),fullPage:true});
  await page.click('#assessment-form [type=submit]');
  await page.waitForSelector('.assessment-list');assert.match(await page.textContent('.assessment-list'),/75%/);
  await page.click('[data-action="participants"]');await page.waitForFunction(()=>document.querySelector('.main-content h1')?.textContent.includes('Участники'));
  assert.match(await page.textContent('.community-table'),/Участник марафона/);
  // Participant results only show their own grade, and their personal library stays private.
  await page.click('[data-action="logout"]');await page.waitForSelector('[data-action="account"]');
  await page.click('[data-action="account"]');await page.fill('[name=login]','reader_a');await page.fill('#account-form [name=password]','testing-password');await page.click('#account-form [type=submit]');
  await page.waitForSelector('[data-action="results"]');assert.equal(await page.locator('[data-action="assessments"]').count(),0);
  await page.click('[data-action="results"]');await page.waitForSelector('.assessment-list');
  assert.match(await page.textContent('.assessment-list'),/75%/);assert.doesNotMatch(await page.textContent('.assessment-list'),/Борис/);
  await page.screenshot({path:path.join(folder,'my-results-mobile.png'),fullPage:true});
  await page.click('[data-action="dashboard"]');await page.waitForSelector('.quiz-card');
  await page.locator('[data-action="visibility"]').first().click();await page.locator('#confirm-dialog').click();
  await page.waitForFunction(()=>document.querySelector('.visibility-badge')?.textContent.includes('Опубликован'));
  await page.click('[data-action="catalog"]');await page.waitForSelector('[data-action="clone-quiz"]');
  await page.click('[data-action="logout"]');await page.waitForSelector('[data-action="account"]');
  await page.click('[data-action="account"]');await page.click('[data-action="marathon-login"]');
  await page.waitForURL(process.env.COMMUNITY_MARATHON_URL+'/**');
  await page.click('[data-action="login-mode"][data-team="1"]');
  await page.waitForSelector('#login-form');await page.fill('#login-form [name=login]','testadmin');
  await page.fill('#login-form [name=password]','testing-admin-password');await page.click('#login-form [type=submit]');
  await page.waitForSelector('#pulse-continue');await page.click('#pulse-continue');
  await page.waitForURL(process.env.COMMUNITY_TEST_URL+'/**');
  await page.waitForFunction(()=>document.querySelector('.account')?.textContent.includes('Команда'));
  const signed=await page.evaluate(async()=> (await (await fetch('api.php?action=bootstrap')).json()).user);
  assert.equal(signed.role,'admin');assert.ok(signed.issuer);
  assert.deepEqual(errors,[]);console.log('PASS: responsive grade editor, percentage preview, save, account login, private results, publication/catalog (320/390/1280px)');
  console.log('PASS: complete browser SSO through marathon login, consent and return to the matching Pulse profile');
 }finally{await browser.close()}
})().catch(e=>{console.error(e);process.exitCode=1;});
