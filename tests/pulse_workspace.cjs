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
  await page.locator('[name=title]').fill('Черновик только моего аккаунта');
  user={...user,id:'other-account'};await page.reload();await page.locator('.library').waitFor();
  assert.equal(await page.locator('[data-draft-restore]').count(),0);
  user={...user,id:'admin-1'};await page.reload();await page.locator('[data-draft-restore]').waitFor();
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
  console.log('PASS: themes, editor draft recovery, failed save, account isolation, responsive navigation and public form');
 }finally{await browser.close();server.close();}
})().catch(e=>{console.error(e);server.close();process.exitCode=1;});
