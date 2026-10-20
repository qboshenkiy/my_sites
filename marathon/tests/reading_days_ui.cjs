const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844},isMobile:true,hasTouch:true});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.MARATHON_DAYS_URL);
  await page.click('[data-action="login-mode"][data-team="1"]');
  await page.fill('#login-form [name=login]','admin');await page.fill('#login-form [name=password]','test-password-2026');
  await page.click('#login-form [type=submit]');await page.waitForSelector('.matrix');
  await page.evaluate(async id=>{await profile(id);editWeekResult(id,2);},process.env.MARATHON_DAYS_USER);
  await page.waitForSelector('#personal-week-form');
  assert.equal(await page.locator('#personal-week-form [name=days]').isVisible(),true);
  await page.locator('dialog').evaluate(d=>d.close());
  for(const role of ['participant','moderator']){
   await page.evaluate(({role,id})=>{boot.user.role=role;editWeekResult(id,2);},{role,id:process.env.MARATHON_DAYS_USER});
   assert.equal(await page.locator('#personal-week-form [name=days]').isVisible(),false);
   assert.equal(await page.locator('#personal-week-form [name=days]').isDisabled(),true);
   assert.equal(await page.locator('#personal-week-form [name=auto]').isVisible(),false);
   assert.match(await page.locator('#personal-week-form').textContent(),/от начала этой недели/);
   assert.doesNotMatch(await page.locator('#personal-week-form').textContent(),/разнице дат завершения/);
   await page.locator('dialog').evaluate(d=>d.close());
   await page.evaluate(id=>completeDialog(id,2),process.env.MARATHON_DAYS_USER);
   assert.equal(await page.locator('#complete-week-form input[name=days]').count(),0);
   await page.locator('dialog').evaluate(d=>d.close());
  }
  assert.deepEqual(errors,[]);
  console.log('PASS: mobile forms expose manual duration only to admin; participant/moderator use saved-week-date calculation');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
