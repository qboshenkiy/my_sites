const {chromium}=require('playwright');
const assert=require('node:assert/strict');
(async()=>{
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1280,height:900}});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.goto(process.env.AUDIT_TEST_URL);
  await page.evaluate(async()=>{
   const b=await (await fetch('api.php?action=bootstrap')).json();
   const response=await fetch('api.php?action=login',{method:'POST',headers:{'Content-Type':'application/json','X-CSRF-Token':b.csrf},body:JSON.stringify({login:'auditadmin',password:'audit-test-password'})});
   if(!response.ok)throw Error('Login failed');
  });
  await page.reload();
  await page.locator('[data-action="audit"]').first().click();
  await page.waitForSelector('#audit-filters');
  await page.selectOption('#audit-filters [name=target]','reader');
  await page.selectOption('#audit-filters [name=week]','2');
  await page.locator('#audit-filters button').click();
  await page.waitForFunction(()=>document.querySelector('#audit-filters [name=target]').value==='reader'&&document.querySelector('.audit-row')?.textContent.includes('New concurrent event'));
  const event=page.locator('.audit-row').filter({hasText:'ручной итог'});
  await event.locator('summary').click();
  assert.ok((await event.textContent()).includes('Главы: 2 → 5'));
  assert.ok(!(await page.textContent('body')).includes('PRIVATE_PASSWORD_HASH'));
  await page.setViewportSize({width:390,height:844});
  assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Audit page overflows phone');
  assert.deepEqual(errors,[]);
  console.log('PASS: journal web filters, expanded before/after, credential exclusion and phone layout');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
