const {chromium} = require('playwright');
const assert = require('node:assert/strict');
const path = require('node:path');
const fs = require('node:fs');

(async () => {
  const browser = await chromium.launch({headless:true});
  const base = process.env.TIMELINE_TEST_URL;
  const code = process.env.MOBILE_ROOM_CODE;
  const folder = path.join(__dirname,'../build'); fs.mkdirSync(folder,{recursive:true});
  const errors = [];
  async function login(name, width) {
    const context = await browser.newContext({viewport:{width,height:844},isMobile:true,hasTouch:true,
      userAgent:'Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 Version/17.0 Mobile/15E148 Safari/604.1'});
    const page = await context.newPage();
    page.on('pageerror',error=>errors.push(error.message));
    await page.goto(base+'/auth/login-page');
    const result = await page.evaluate(async ({name,password}) => {
      const form = new FormData(document.querySelector('form'));
      form.set('login',name); form.set('password',password);
      return (await fetch('/auth/login-page',{method:'POST',body:form,headers:{'X-Requested-With':'XMLHttpRequest'}})).json();
    },{name,password:process.env.ADMIN_PASSWORD});
    assert.ok(result.success);
    return page;
  }
  async function fits(page) {
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'Page overflows horizontally');
  }
  try {
    const a = await login('reader_a',390), b = await login('reader_b',320);
    for (const page of [a,b]) {
      await page.goto(base+'/rooms/play/'+code);
      await page.waitForSelector('.hand-card');
      await fits(page);
      await page.locator('.hand-card-details').first().tap();
      await page.waitForSelector('#card-modal:not([hidden])');
      assert.equal(await page.textContent('#modal-value'),'');
      const modal = await page.locator('.card-modal-card').boundingBox();
      assert.ok(modal.width<=page.viewportSize().width-20);
      await page.locator('.modal-close').tap();
    }
    const state = await (await a.request.get(base+'/rooms/state/'+code)).json();
    const player = state.isMyTurn ? a : b;
    const before = await (await player.request.get(base+'/rooms/state/'+code)).json();
    await player.locator('.hand-card .square-card-media').first().tap();
    await player.waitForSelector('.hand-card.is-selected');
    assert.ok(await player.locator('#card-modal').isHidden());
    await player.locator('.drop-zone:not([disabled])').first().tap();
    await player.waitForFunction(()=>!document.getElementById('confirm-placement').disabled);
    const unchanged = await (await player.request.get(base+'/rooms/state/'+code)).json();
    assert.equal(unchanged.room.stateVersion,before.room.stateVersion,'Selecting a position must not send a move');
    for (const zone of await player.locator('.drop-zone').all()) {
      const box = await zone.boundingBox(); assert.ok(box.width>=43);
      assert.ok(box.x>=0 && box.x+box.width<=player.viewportSize().width+1);
    }
    const confirm = await player.locator('#confirm-placement').boundingBox();
    assert.ok(confirm.height>=44 && confirm.y+confirm.height<=844,'Confirmation is outside viewport');
    await player.screenshot({path:path.join(folder,'mobile-game-selected.png'),fullPage:true});
    await player.locator('#confirm-placement').tap();
    await player.waitForFunction(async ({base,code,version})=>(await (await fetch(base+'/rooms/state/'+code)).json()).room.stateVersion>version,
      {base,code,version:before.room.stateVersion});
    const after = await (await player.request.get(base+'/rooms/state/'+code)).json();
    assert.equal(after.timeline.length,before.timeline.length+1);
    await player.locator('#menu-toggle').tap();
    await player.waitForSelector('#game-menu:not([hidden])');
    await player.locator('#menu-close').tap();
    await player.setViewportSize({width:844,height:390}); await fits(player);
    await a.setViewportSize({width:390,height:844});
    await a.goto(base+'/rooms');
    assert.ok(await a.locator('.mobile-bottom-nav').isVisible());
    await fits(a);
    await a.screenshot({path:path.join(folder,'mobile-rooms.png'),fullPage:true});
    // Create a waiting lobby and follow its public guest invitation on a phone.
    await a.selectOption('#game-mode','BLIND');
    await a.locator('#create-room-form button[type=submit]').tap();
    await a.waitForURL(/\/rooms\/show\//);
    await fits(a);
    const qr = await a.locator('.room-lobby-invite img').boundingBox();
    assert.ok(await a.evaluate(({x,y})=>!!document.elementFromPoint(x,y)?.closest('.room-lobby-invite img'),
      {x:qr.x+qr.width/2,y:qr.y+qr.height/2}),'Invitation QR is covered by controls');
    await a.screenshot({path:path.join(folder,'mobile-lobby.png'),fullPage:true});
    const lobbyCode = a.url().split('/').pop();
    const guestContext = await browser.newContext({viewport:{width:320,height:740},isMobile:true,hasTouch:true});
    const guest = await guestContext.newPage(); guest.on('pageerror',error=>errors.push(error.message));
    await guest.goto(base+'/rooms/invite/'+lobbyCode);
    await fits(guest);
    await guest.fill('#guest-name','Игрок с телефона');
    await guest.tap('.submit-btn');
    await guest.waitForURL(/\/rooms\/show\//);
    await fits(guest);
    assert.ok((await guest.textContent('#lobby-players')).includes('Игрок с телефона'));
    await a.locator('.room-action-start').tap();
    await a.waitForURL(/\/rooms\/play\//);
    await guest.waitForURL(/\/rooms\/play\//);
    const blindState = await (await a.request.get(base+'/rooms/state/'+lobbyCode)).json();
    const blindPlayer = blindState.isMyTurn ? a : guest;
    await blindPlayer.locator('#draw-button').tap();
    await blindPlayer.waitForSelector('.hand-card');
    await blindPlayer.locator('.hand-card .square-card-media').first().tap();
    await blindPlayer.locator('.drop-zone:not([disabled])').first().tap();
    await blindPlayer.waitForFunction(()=>!document.getElementById('confirm-placement').disabled);
    await blindPlayer.locator('#confirm-placement').tap();
    await blindPlayer.waitForFunction(()=>!document.getElementById('move-result').hidden);
    assert.deepEqual(errors,[]);
    console.log('PASS: mobile 320/390px normal/blind gameplay, details, confirmation, real moves, landscape, QR lobby and guest join');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
