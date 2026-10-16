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
  async function invitation(page, roomCode) {
    await page.evaluate(()=>{
      delete navigator.clipboard;delete navigator.share;delete navigator.canShare;
      window.originalCopyCommand ||= document.execCommand;
      document.execCommand = window.originalCopyCommand;
      delete window.legacyCopied;delete window.sharedInvite;
    });
    const widget = page.locator('[data-room-share]');
    const url = await widget.locator('[data-invite-url]').inputValue();
    assert.ok(url.endsWith('/rooms/invite/'+roomCode));
    const telegram = new URL(await widget.locator('[data-share-telegram]').getAttribute('href'));
    const whatsapp = new URL(await widget.locator('[data-share-whatsapp]').getAttribute('href'));
    assert.equal(telegram.searchParams.get('url'),url);
    assert.ok(whatsapp.searchParams.get('text').includes(url));
    await page.context().grantPermissions(['clipboard-read','clipboard-write']);
    await widget.locator('[data-room-copy="link"]').tap();
    await page.waitForFunction(()=>document.querySelector('[data-share-status]').textContent==='Ссылка скопирована.');
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),url);
    await widget.locator('.share-more').evaluate(el=>el.open=true);
    await widget.locator('[data-room-copy="code"]').tap();
    await page.waitForFunction(()=>document.querySelector('[data-share-status]').textContent==='Код скопирован.');
    assert.equal(await page.evaluate(()=>navigator.clipboard.readText()),roomCode);
    await page.evaluate(()=>{
      Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});
      document.execCommand = () => {window.legacyCopied=document.activeElement.value;return true;};
    });
    await widget.locator('[data-room-copy="link"]').tap();
    await page.waitForFunction(()=>!!window.legacyCopied);
    assert.equal(await page.evaluate(()=>window.legacyCopied),url);
    await page.evaluate(()=>{document.execCommand=()=>false;});
    await widget.locator('[data-room-copy="link"]').tap();
    await page.waitForFunction(()=>document.querySelector('[data-share-status]').textContent.startsWith('Ссылка выделена.'));
    assert.equal(await widget.locator('[data-invite-url]').evaluate(el=>el.selectionEnd-el.selectionStart),url.length);
    await page.evaluate(()=>{
      Object.defineProperty(navigator,'canShare',{configurable:true,value:()=>true});
      Object.defineProperty(navigator,'share',{configurable:true,value:async data=>{window.sharedInvite=data;}});
    });
    await widget.locator('[data-room-send]').tap();
    await page.waitForFunction(()=>!!window.sharedInvite);
    assert.equal(await page.evaluate(()=>window.sharedInvite.url),url);
    await page.evaluate(()=>{Object.defineProperty(navigator,'share',{configurable:true,value:async()=>{throw new DOMException('Cancelled','AbortError');}});});
    await widget.locator('[data-room-send]').tap();
    await page.waitForFunction(()=>document.querySelector('[data-share-status]').textContent==='Отправка отменена.');
    await page.evaluate(()=>{Object.defineProperty(navigator,'share',{configurable:true,value:undefined});});
    await widget.locator('[data-room-send]').tap();
    await page.waitForFunction(()=>document.querySelector('[data-share-status]').textContent.startsWith('Выберите Telegram'));
    // The delegated handlers survive replacing lobby markup after a rematch.
    await widget.evaluate(el=>el.replaceWith(el.cloneNode(true)));
    await page.locator('[data-room-copy="link"]').tap();
    await page.waitForFunction(()=>document.querySelector('[data-share-status]').textContent.startsWith('Ссылка выделена.'));
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
    // Long timeline fixture: every card and every insertion point stays in the DOM.
    const previewState = structuredClone(state);
    const liveState = await (await player.request.get(base+'/rooms/state/'+code)).json();
    Object.assign(previewState,liveState);
    previewState.timeline = Array.from({length:12},(_,index)=>({...liveState.timeline[0],id:900000+index,title:`Событие ${index+1}`}));
    const stateRoute = '**/rooms/state/'+code;
    await player.route(stateRoute, route=>route.fulfill({json:previewState}));
    await player.reload();
    await player.waitForFunction(()=>document.querySelectorAll('.table-card').length===12);
    assert.equal(await player.locator('.drop-zone').count(),13);
    await fits(player);
    await player.locator('.hand-card .square-card-media').first().tap();
    await player.locator('#timeline').evaluate(el=>{el.scrollLeft=el.scrollWidth;});
    const savedLeft = await player.locator('#timeline').evaluate(el=>el.scrollLeft);
    assert.ok(savedLeft>0,'Long table must scroll');
    await player.waitForTimeout(1800);
    assert.equal(await player.locator('#timeline').evaluate(el=>el.scrollLeft),savedLeft,'Polling reset table scroll');
    await player.locator('.drop-zone').last().tap();
    assert.ok(await player.locator('.drop-zone').last().evaluate(el=>el.classList.contains('is-chosen')));
    assert.equal(await player.locator('#timeline').evaluate(el=>el.scrollLeft),savedLeft,'Choosing position reset scroll');
    await player.screenshot({path:path.join(folder,'mobile-long-timeline.png'),fullPage:true});
    await player.locator('#cancel-selection').tap();
    await player.unroute(stateRoute);
    await player.goto(base+'/rooms/play/'+code);
    await player.waitForSelector('.hand-card');

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
    await player.waitForSelector('#live-move:not([hidden])');
    const touchSession = await player.context().newCDPSession(player);
    await touchSession.send('Input.synthesizePinchGesture',{x:150,y:250,scaleFactor:1.5,relativeSpeed:800,gestureSourceType:'touch'});
    assert.ok(await player.evaluate(()=>visualViewport.scale<=1.01),'Two-finger gesture zoomed game');
    await touchSession.detach();
    // Reproduce a played card on a short phone: cards must never be clipped by the last move.
    for (const viewport of [{width:390,height:640},{width:320,height:568},{width:390,height:844}]) {
      await player.setViewportSize(viewport);
      await fits(player);
      const boxes = await player.evaluate(() => {
        const rect = selector => {const r=document.querySelector(selector).getBoundingClientRect();return {top:r.top,bottom:r.bottom,width:r.width};};
        return {board:rect('#timeline'),card:rect('.table-card'),move:rect('#live-move'),body:rect('.live-move-body')};
      });
      assert.ok(boxes.card.top>=boxes.move.bottom-1,'Last move overlaps cards');
      assert.ok(boxes.card.bottom<=boxes.board.bottom+1,'Timeline card is vertically clipped');
      assert.ok(boxes.body.width>150,'Last move text collapsed into image column');
      assert.equal(await player.locator('#play-root').evaluate(el=>getComputedStyle(el).touchAction),'pan-x pan-y');
    }
    await player.waitForSelector('#move-result',{state:'hidden'});
    await player.screenshot({path:path.join(folder,'mobile-game-after-move.png'),fullPage:true});
    await player.locator('#live-move-details').tap();
    assert.ok(await player.locator('#card-modal').isVisible());
    await player.locator('.modal-close').tap();
    await player.setViewportSize({width:1280,height:800});
    await fits(player);
    assert.ok((await player.locator('.live-move-body').boundingBox()).width>400,'Desktop last move collapsed');
    await player.screenshot({path:path.join(folder,'desktop-game-minimal.png'),fullPage:true});
    await player.setViewportSize({width:390,height:844});
    await player.locator('#menu-toggle').tap();
    await player.waitForSelector('#game-menu:not([hidden])');
    await invitation(player,code);
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
    assert.ok(await a.locator('.room-lobby-invite img').isHidden(),'QR is collapsed by default');
    assert.ok(await a.locator('.share-more [data-invite-url]').isHidden(),'Advanced sharing is collapsed');
    const start = await a.locator('.room-action-start').boundingBox();
    const nav = await a.locator('.mobile-bottom-nav').boundingBox();
    assert.ok(start.y+start.height<=nav.y,'Start action is behind bottom navigation');
    await a.screenshot({path:path.join(folder,'mobile-lobby-minimal.png'),fullPage:true});
    await a.locator('.invite-qr summary').tap();
    await a.locator('.room-lobby-invite img').scrollIntoViewIfNeeded();
    const qr = await a.locator('.room-lobby-invite img').boundingBox();
    assert.ok(await a.evaluate(({x,y})=>!!document.elementFromPoint(x,y)?.closest('.room-lobby-invite img'),
      {x:qr.x+qr.width/2,y:qr.y+qr.height/2}),'Invitation QR is covered by controls');
    await a.screenshot({path:path.join(folder,'mobile-lobby.png'),fullPage:true});
    const lobbyCode = a.url().split('/').pop();
    await invitation(a,lobbyCode);
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
    console.log('PASS: mobile gameplay and invitations: real clipboard, legacy/manual fallback, native share/cancel, messenger URLs and guest join');
  } finally {await browser.close();}
})().catch(error=>{console.error(error);process.exitCode=1;});
