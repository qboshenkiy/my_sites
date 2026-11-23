const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE});
 try{
  const page=await browser.newPage({viewport:{width:390,height:844}}),errors=[];
  page.on('pageerror',error=>errors.push(error.message));
  await page.goto(process.env.MARATHON_COMPLETION_URL);
  await page.click('[data-action="login-mode"][data-team="1"]');
  await page.fill('#login-form [name=login]','admin');
  await page.fill('#login-form [name=password]','test-password-2026');
  await page.click('#login-form [type=submit]');await page.waitForSelector('.matrix');
  await page.evaluate(async id=>{await profile(id)},process.env.MARATHON_COMPLETION_USER);
  const openCorrection=async()=>{
   const details=page.locator('.week-detail:has([data-completion-correct="1"])');
   if(await details.getAttribute('open')===null)await details.locator('summary').first().click();
   await page.click('[data-completion-correct="1"]');
  };
  await openCorrection();
  await page.fill('#completion-correction-form [name=completed_on]','2026-10-20');
  await page.click('#completion-correction-form [type=submit]');
  await page.waitForSelector('#completion-correction-form',{state:'detached'});
  await page.waitForFunction(()=>profileData.stats.reports[0].late);
  await openCorrection();await page.click('[data-finish-on-time]');
  assert.equal(await page.inputValue('#completion-correction-form [name=completed_on]'),'2026-10-18');
  await page.click('#completion-correction-form [type=submit]');
  await page.waitForSelector('#completion-correction-form',{state:'detached'});
  await page.waitForFunction(()=>!profileData.stats.reports[0].late);
  assert.equal(await page.evaluate(()=>profileData.stats.reports[0].days),7);
  assert.equal(await page.evaluate(()=>profileData.stats.reports[0].editable),false);
  assert.equal(await page.locator('[data-cycle-delete="0"]').count(),0);
  await page.click('[data-week-repeat="2"]');
  await page.click('#weekly-repeat-form [type=submit]');
  await page.waitForSelector('[data-cycle-delete="5"]');
  await page.click('[data-cycle-delete="5"]');
  await page.click('#cycle-change-form [type=submit]');
  await page.waitForSelector('#cycle-change-form',{state:'detached'});
  await page.waitForFunction(()=>profileData.stats.pace.cycle===0);
  assert.equal(await page.locator('[data-cycle-delete="6"]').count(),0);
  await page.click('[data-week-edit="2"]');
  await page.fill('#personal-week-form [name=chapters]','2');
  await page.click('#personal-week-form [type=submit]');
  await page.waitForSelector('#personal-week-form',{state:'detached'});
  await page.waitForFunction(()=>profileData.stats.pace.cycle===6&&profileData.stats.pace.chapters===2);
  assert.deepEqual(errors,[]);
  await page.screenshot({path:process.env.MARATHON_COMPLETION_SCREENSHOT||'/tmp/marathon-completion.png',fullPage:true});
  console.log('PASS: browser date correction, on-time button, restart/delete without duplication and first reading after deletion.');
 }finally{await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
