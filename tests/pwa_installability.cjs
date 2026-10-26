const assert=require('node:assert/strict');
const {chromium}=require(process.env.PLAYWRIGHT_MODULE||'playwright');
(async()=>{
 const browser=await chromium.launch({headless:true,...(process.env.PLAYWRIGHT_BROWSER?{executablePath:process.env.PLAYWRIGHT_BROWSER}:{})});
 try{
  const page=await browser.newPage();const client=await page.context().newCDPSession(page);await client.send('Page.enable');
  await page.goto(process.env.PWA_TEST_URL+'/pwa-test.html');
  await page.evaluate(()=>navigator.serviceWorker.ready);
  const manifest=await client.send('Page.getAppManifest');assert.deepEqual(manifest.errors,[]);
  const errors=await client.send('Page.getInstallabilityErrors');assert.deepEqual(errors.installabilityErrors,[]);
  const registration=await page.evaluate(async()=>{const r=await navigator.serviceWorker.getRegistration('/');return {scope:r.scope,script:r.active.scriptURL};});
  assert.ok(registration.script.endsWith('/index.php?pwa=worker'));assert.equal(new URL(registration.scope).pathname,'/');
  await page.context().setOffline(true);await page.reload();await page.getByText('Нет соединения',{exact:true}).first().waitFor();
  console.log('PASS: Chromium installability, manifest icons, PHP worker scope and offline opening');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1;});
