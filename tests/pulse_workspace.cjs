const {chromium}=require('playwright');
const http=require('node:http'), fs=require('node:fs'), path=require('node:path'), assert=require('node:assert/strict');
const root=path.resolve(__dirname,'..');
const quiz=(id,title,mode='classic')=>({id,title,mode,description:'Вопросы и обсуждение после ответов.',visibility:'private',scoring:'fixed',questions:[{text:'Вопрос?',type:'quiz',options:['Один','Два','Три'],correct:0,seconds:30,points:1000,category:'Общее'}]});
let user={id:'admin-1',name:'Иван Тестовый',role:'admin'}, rejectSave=true;
const quizzes=[quiz('q1','История и культура'),quiz('q2','Общий кругозор','board'),quiz('q3','Литературный клуб','author'),quiz('q4','Наука и технологии')];
const server=http.createServer((req,res)=>{
 const u=new URL(req.url,'http://localhost');
 if(u.pathname==='/api.php'){
  const action=u.searchParams.get('action');
  let value=({bootstrap:{configured:true,user,csrf:'fixture'},quizzes:{quizzes,rooms:[]},catalog:{quizzes:[]},forms:{forms:[]},assessments:{assessments:[]},directory:{users:[]},standings:{rows:[],columns:[],tests:[],standings:[],participants:[]}})[action]||{ok:true};
  if(action==='save'&&rejectSave){res.statusCode=400;value={error:'Проверка: сохранение не удалось'};}
  res.setHeader('Content-Type','application/json');res.end(JSON.stringify(value));return;
 }
 if(u.pathname==='/'||u.pathname==='/index.php'){
  res.setHeader('Content-Type','text/html; charset=utf-8');res.end(fs.readFileSync(path.join(root,'index.php'),'utf8').split('<!doctype html>')[1].replace(/^/,'<!doctype html>'));return;
 }
 const file=path.join(root,u.pathname);
 if(!file.startsWith(root+'/assets/')||!fs.existsSync(file)){res.statusCode=404;res.end();return;}
 res.setHeader('Content-Type',u.pathname.endsWith('.css')?'text/css':u.pathname.endsWith('.js')?'application/javascript':'application/octet-stream');fs.createReadStream(file).pipe(res);
});
(async()=>{
 await new Promise(r=>server.listen(0,'127.0.0.1',r));
 const url='http://127.0.0.1:'+server.address().port;
 const browser=await chromium.launch({headless:true});
 try{
  const page=await browser.newPage({viewport:{width:1440,height:1000},colorScheme:'light',reducedMotion:'reduce'});
  const errors=[];page.on('pageerror',e=>errors.push(e.message));
  await page.route('https://telegram.org/**',r=>r.fulfill({contentType:'application/javascript',body:''}));
  await page.goto(url);await page.locator('.quiz-card').first().waitFor();
  assert.equal(await page.locator('.sidebar [aria-current=page]').count(),1);
  await page.locator('.pulse-theme-toggle').click();
  assert.equal(await page.locator('html').getAttribute('data-pulse-theme'),'dark');
  assert.equal(await page.locator('html').evaluate(e=>getComputedStyle(e).colorScheme),'dark');
  await page.reload();await page.locator('.quiz-card').first().waitFor();
  assert.equal(await page.locator('html').getAttribute('data-pulse-theme'),'dark');
  await page.locator('[data-action=new]').click();
  await page.locator('[name=title]').fill('Черновик на проверку');
  await page.locator('[name=text-0]').fill('Восстанавливаемый вопрос');
  await page.locator('[name=option-0-0]').fill('Первый ответ');
  await page.locator('[name=option-0-1]').fill('Второй ответ');
  await page.locator('[name=option-0-2]').fill('Третий ответ');
  await page.locator('[name=option-0-3]').fill('Четвёртый ответ');
  await page.locator('[data-action=add-option]').click();
  await page.locator('[name=option-0-4]').fill('Пятый ответ');
  await page.locator('[data-action=add-question]').click();
  assert.equal(await page.locator('.question-editor').count(),2);
  await page.reload();await page.locator('[data-draft-restore]').click();
  assert.equal(await page.locator('[name=title]').inputValue(),'Черновик на проверку');
  assert.equal(await page.locator('[name=option-0-4]').inputValue(),'Пятый ответ');
  assert.equal(await page.locator('.question-editor').count(),2);
  await page.locator('[data-action=remove-question][data-index="1"]').click();
  await page.locator('#editor-form button[type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('#toast').textContent.includes('сохранение не удалось'));
  await page.reload();await page.locator('[data-draft-restore]').click();
  rejectSave=false;await page.locator('#editor-form button[type=submit]').click();
  await page.locator('.library').waitFor();
  assert.equal(await page.locator('[data-draft-restore]').count(),0);
  await page.locator('[data-action=new]').click();
  await page.evaluate(()=>{
   draft.title='Удобное создание';draft.questions=[{...defaultQuestion(),text:'Первый вопрос',options:['Первый','Второй','Третий','Четвёртый'],correct:2,reference:'Источник вопроса'}];drawEditor();
  });
  assert.equal(await page.locator('[data-editor-ready]').textContent(),'Готово 1 из 1');
  await page.locator('[data-editor-action=duplicate]').click();assert.equal(await page.locator('.question-editor').count(),2);
  await page.locator('[name=text-1]').fill('Копия вопроса');
  await page.locator('[data-editor-action=move][data-index="1"][data-offset="-1"]').click();
  assert.equal(await page.inputValue('[name=text-0]'),'Копия вопроса');assert.equal(await page.inputValue('[name=text-1]'),'Первый вопрос');
  await page.locator('[data-editor-option-remove="1"][data-index="0"]').click();
  assert.equal(await page.inputValue('[name=option-0-1]'),'Третий');assert.equal(await page.locator('[name=correct-0][value="1"]').isChecked(),true);
  await page.locator('[data-editor-action=collapse]').click();assert.equal(await page.locator('.question-editor[open]').count(),0);
  await page.locator('[data-editor-go="1"]').click();assert.equal(await page.locator('.question-editor[open]').count(),1);
  await page.locator('[data-editor-action=expand]').click();assert.equal(await page.locator('.question-editor[open]').count(),2);
  await page.locator('[data-editor-action=preview]').click();await page.locator('.editor-preview-dialog').waitFor();
  assert.equal(await page.locator('.editor-preview-dialog .self-test-reference').count(),0);
  await page.locator('[data-editor-preview=review]').click();assert.ok(await page.locator('.editor-preview-dialog .self-test-reference').count()>0);
  await page.locator('[data-editor-preview-close]').click();
  await page.locator('[name=correct-0][value="1"]').uncheck();await page.locator('#editor-form [type=submit]').click();
  await page.waitForFunction(()=>document.querySelector('[data-editor-issues]')?.textContent.includes('Отметьте правильный ответ'));
  assert.ok(await page.locator('[data-editor-issues]').first().isVisible());
  await page.locator('[name=correct-0][value="1"]').check();
  await page.locator('[data-action=add-block][data-block=ordering]').click();
  for(const [index,text] of ['Начало','Середина','Конец'].entries())await page.fill(`[name=block-option-2-${index}]`,text);
  await page.locator('[data-editor-option-move="2"][data-index="2"][data-offset="-1"]').click();
  assert.equal(await page.inputValue('[name=block-option-2-1]'),'Конец');
  await page.locator('[data-editor-go="0"]').click();await page.evaluate(()=>document.querySelector('#toast').classList.remove('visible'));
  const folder=path.join(root,'dist/pulse-editor-preview');fs.mkdirSync(folder,{recursive:true});
  for(const theme of ['light','dark']){
   await page.evaluate(value=>{localStorage.setItem('pulse-theme',value);document.documentElement.setAttribute('data-pulse-theme',value);},theme);
   for(const width of [320,390,800,1440]){
    await page.setViewportSize({width,height:1000});
    assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth+1),true,'Editor overflow at '+theme+' '+width);
    if(width===1440||width===390){await page.evaluate(()=>window.scrollTo(0,0));await page.screenshot({path:path.join(folder,`editor-${theme}-${width}.png`),fullPage:true});await page.screenshot({path:path.join(folder,`editor-top-${theme}-${width}.png`)});}
   }
  }
  await page.locator('[data-editor-action=preview]').click();await page.locator('.editor-preview-dialog').waitFor();
  assert.equal(await page.locator('.editor-preview-dialog').evaluate(e=>e.scrollWidth<=e.clientWidth+1),true);
  await page.locator('[data-editor-preview-close]').click();
  await page.evaluate(()=>dashboard());await page.waitForSelector('.library');await page.locator('[data-action=new]').click();
  await page.locator('[name=title]').fill('Черновик только моего аккаунта');
  user={...user,id:'other-account'};await page.reload();await page.locator('.library').waitFor();
  assert.equal(await page.locator('[data-draft-restore]').count(),0);
  user={...user,id:'admin-1'};await page.reload();await page.locator('[data-draft-restore]').first().waitFor();
  for(const width of [320,390,800,1440]){
   await page.setViewportSize({width,height:820});
   assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth),true,'Dashboard overflow at '+width);
  }
  await page.setViewportSize({width:390,height:820});
  await page.locator('.mobile-menu-button').click();
  await page.locator('.sidebar [data-action=forms]').click();
  await page.locator('.forms-library').waitFor();
  assert.equal(await page.locator('.sidebar [aria-current=page]').getAttribute('data-action'),'forms');
  assert.equal(await page.locator('body').evaluate(e=>e.classList.contains('mobile-nav-open')),false);
  await page.locator('.mobile-menu-button').click();
  await page.locator('.sidebar [data-action=join-page]').click();
  await page.locator('#join-form').waitFor();
  await page.locator('.pulse-theme-toggle').click();
  assert.equal(await page.locator('html').getAttribute('data-pulse-theme'),'light');
  assert.deepEqual(errors,[]);
  console.log('PASS: editor navigation, collapse, copy/reorder, option removal, ordered rows, previews, validation, themes, draft recovery, failed save, account isolation and responsive layout');
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
