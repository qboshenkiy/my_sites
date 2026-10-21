const {chromium}=require('playwright');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');
(async()=>{
 const browser=await chromium.launch({headless:true}),errors=[];
 try{
  const admin=await browser.newPage({viewport:{width:1440,height:1000}});admin.on('pageerror',e=>errors.push(e.message));
  await admin.goto(process.env.FORMS_TEST_URL);await admin.click('[data-action="account"]');await admin.click('[data-action="legacy-login"]');
  await admin.fill('#auth-form [name=password]','testing-admin-password');await admin.click('#auth-form [type=submit]');
  await admin.waitForSelector('.welcome [data-action="new"]');await admin.click('.welcome [data-action="new"]');
  await admin.fill('#editor-form [name=title]','Проверка расширенных вариантов');await admin.fill('#editor-form [name=text-0]','Отметьте два правильных ответа');
  await admin.click('[data-action="add-option"]');await admin.click('[data-action="add-option"]');
  for(const [i,value] of ['Первый','Второй','Третий','Четвёртый','Пятый','Шестой'].entries())await admin.fill(`[name="option-0-${i}"]`,value);
  await admin.check('[name="correct-0"][value="0"]');await admin.check('[name="correct-0"][value="4"]');
  await admin.click('#editor-form [type=submit]');await admin.waitForSelector('.welcome [data-action="new"]');
  const uiQuiz=await admin.evaluate(()=>library.find(q=>q.title==='Проверка расширенных вариантов'));
  assert.equal(uiQuiz.questions[0].options.length,6);assert.deepEqual(uiQuiz.questions[0].correct,[0,4]);
  await admin.click('[data-action="forms"]');await admin.click('[data-form-action="new"]');
  await admin.selectOption('#new-self-test [name=quiz_id]',process.env.FORMS_QUIZ_ID);await admin.fill('#new-self-test [name=title]','Бытие · проверка знаний');await admin.click('#new-self-test [type=submit]');
  await admin.waitForSelector('.forms-copy-row input');const url=await admin.inputValue('.forms-copy-row input');
  const context=await browser.newContext({viewport:{width:390,height:844},isMobile:true,hasTouch:true});const guest=await context.newPage();guest.on('pageerror',e=>errors.push(e.message));
  await guest.goto(url);await guest.fill('[name=participant_name]','Тестовая работа Анны');await guest.check('[name=self-q-0][value="0"]');await guest.check('[name=self-q-0][value="4"]');await guest.check('[name=self-q-1][value="0"]');
  await guest.reload();await guest.waitForSelector('#public-self-test');assert.equal(await guest.inputValue('[name=participant_name]'),'Тестовая работа Анны');assert.equal(await guest.locator('[name=self-q-0][value="0"]').isChecked(),true);assert.equal(await guest.locator('[name=self-q-0][value="4"]').isChecked(),true);
  const folder=path.resolve(__dirname,'../dist/pulse-forms-preview');fs.mkdirSync(folder,{recursive:true});
  await guest.screenshot({path:path.join(folder,'test-mobile.png'),fullPage:true});
  await guest.click('#public-self-test [type=submit]');await guest.locator('dialog #confirm-dialog').click();await guest.waitForSelector('.self-test-wait');
  assert.equal(await guest.locator('.self-test-score').count(),0);assert.equal(await guest.locator('.self-test-review').count(),0);
  await admin.click('[data-form-action="refresh"]');await admin.waitForFunction(()=>document.querySelector('.forms-stats strong')?.textContent==='1');
  await admin.click('[data-form-action="toggle-published"]');await admin.locator('dialog #confirm-dialog').click();await admin.waitForFunction(()=>currentForm.form.published===1);
  await guest.reload();await guest.waitForSelector('.self-test-score');assert.match(await guest.textContent('.self-test-score'),/100%/);
  await admin.click('[data-form-action="link"]');await admin.locator('dialog select').selectOption(process.env.FORMS_USER_A);await admin.locator('dialog .primary').click();
  await admin.waitForSelector('[data-form-action="edit-grades"]');
  for(const width of [1440,390,320]){
   await admin.setViewportSize({width,height:900});assert.ok(await admin.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'manager overflow '+width);
   if(width!==320)await admin.screenshot({path:path.join(folder,'responses-'+width+'.png'),fullPage:true});
  }
  await admin.click('[data-form-action="edit-grades"]');await admin.waitForSelector('#assessment-form');
  await admin.fill(`[data-grade-user="${process.env.FORMS_USER_A}"] [data-points]`,'650');
  await admin.click('[data-grade-add]');await admin.locator('.grade-picker input[type=search]').fill('Борис');await admin.locator(`.grade-picker input[value="${process.env.FORMS_USER_B}"]`).check();await admin.locator('[data-add-selected]').click();
  await admin.fill(`[data-grade-user="${process.env.FORMS_USER_B}"] [data-points]`,'0');
  assert.equal(await admin.locator(`[data-grade-user="${process.env.FORMS_USER_A}"] output`).textContent(),'65%');
  for(const width of [320,390,1440]){
   await admin.setViewportSize({width,height:900});assert.ok(await admin.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),'grade editor overflow '+width);
   if(width!==320)await admin.screenshot({path:path.join(folder,'edit-grades-'+width+'.png'),fullPage:true});
  }
  await admin.click('#assessment-form [type=submit]');await admin.waitForSelector('.assessment-list');assert.match(await admin.textContent('.assessment-list'),/65%/);
  await guest.reload();await guest.waitForSelector('.self-test-score');assert.match(await guest.textContent('.self-test-score'),/65%/);
  // Real host and two players: DOM polling cannot swallow pointer gestures or strand buttons.
  const room=await admin.evaluate(async()=>{
   const saved=await api('save',{title:'Проверка управления',questions:[0,1,2].map(i=>({text:'Вопрос '+(i+1),type:'quiz',seconds:90,points:500,correct:0,options:['Правильно','Неверно']}))});
   const room=await api('create_room',{id:saved.id});await hostRoom(room.id);return room;
  });
  const clients=[];
  for(const name of ['Первый','Второй']){
   const cx=await browser.newContext();const p=await cx.newPage();p.on('pageerror',e=>errors.push(e.message));
   await p.goto(process.env.FORMS_TEST_URL+'/?code='+room.code);await p.fill('#join-form [name=name]',name);await p.click('#join-form [type=submit]');await p.waitForSelector('.player-list');clients.push([cx,p]);
  }
  await admin.waitForFunction(()=>state?.players.length===2);await admin.locator('[data-command="next"]').click();await admin.waitForFunction(()=>state?.status==='question');
  const reveal=admin.locator('[data-command="reveal"]');await reveal.scrollIntoViewIfNeeded();const box=await reveal.boundingBox();await admin.mouse.move(box.x+box.width/2,box.y+box.height/2);await admin.mouse.down();await admin.waitForTimeout(1400);await admin.mouse.up();
  await admin.waitForFunction(()=>state?.status==='results');assert.equal(await admin.evaluate(()=>state.index),0);
  await admin.locator('[data-command="next"]').click();await admin.waitForFunction(()=>state?.index===1&&state?.status==='question');
  await clients[0][1].waitForFunction(()=>state?.index===1);await clients[0][1].locator('[data-action="answer"][data-choice="0"]').click();
  const projector=await admin.evaluate(async()=>{const s=await api('state');return {token:s.projectorToken};});
  const screen=await browser.newPage();await screen.goto(process.env.FORMS_TEST_URL+'/?projector='+projector.token);await screen.waitForFunction(()=>state?.status==='question');
  assert.deepEqual(await screen.evaluate(()=>state.counts),[]);assert.ok((await screen.evaluate(()=>state.players)).every(p=>p.score===0));
  await clients[1][1].waitForFunction(()=>state?.index===1);await clients[1][1].locator('[data-action="answer"][data-choice="1"]').click();
  await admin.waitForFunction(()=>state?.status==='results');assert.equal(await admin.evaluate(()=>state.question.correct),0);
  const race=await admin.evaluate(async()=>{const payload={room:activeRoom,version:state.version,command:'next'};return Promise.all([api('control',payload).then(()=>true,()=>false),api('control',payload).then(()=>true,()=>false)]);});
  assert.equal(race.filter(Boolean).length,1);await admin.waitForFunction(()=>state?.index===2&&state?.status==='question');
  await admin.route('**/api.php?action=control',route=>route.fulfill({status:503,contentType:'application/json',body:JSON.stringify({error:'Проверка сбоя соединения'})}),{times:1});
  await admin.locator('[data-command="reveal"]').click();await admin.waitForFunction(()=>!busy&&document.querySelector('[data-command="reveal"]')?.disabled===false);
  await admin.locator('[data-command="reveal"]').click();await admin.waitForFunction(()=>state?.status==='results');
  await screen.close();for(const [cx] of clients)await cx.close();
  assert.deepEqual(errors,[]);await context.close();console.log('PASS: form creation, mobile autosave/submit, hidden then released answers, guest linking, manual correction/add participant, 320/390/1440px and preserved result');
  console.log('PASS: long pointer hold across polling, anonymous projector, automatic reveal for all answers, stale double command protection and retry after network failure');
 }finally{await browser.close();}
})().catch(e=>{console.error(e);process.exit(1);});
