const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('assets/forms.js','utf8');const start=source.indexOf('function formReviewQuestion('),end=source.indexOf('async function openPublicForm(',start);
const context={esc:v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])),formRight:q=>Array.isArray(q.correct)?q.correct.map(Number):[Number(q.correct)]};vm.createContext(context);vm.runInContext(source.slice(start,end),context);
const q={type:'quiz',text:'Сколько книг в задании?',options:['Одна','Две','Три'],correct:1};
const wrong=context.formReviewQuestion(q,0,0);assert(wrong.includes('incorrect')&&wrong.includes('Ваш ответ — неверно')&&wrong.includes('Правильный ответ'));
const correct=context.formReviewQuestion(q,1,1);assert(correct.includes('✓ Верно')&&!correct.includes('incorrect'));
const multi=context.formReviewQuestion({...q,correct:[0,1]},[0],2);assert(multi.includes('✕ Неверно'),'An incomplete correct set is still incorrect');
assert(context.formReviewQuestion(q,null,3).includes('Нет ответа'));
assert(!context.formReviewQuestion({...q,type:'poll'},0,4).includes('incorrect'),'Polls have no wrong answers');
assert(context.formReviewQuestion({...q,text:'<script>x</script>'},0,5).includes('&lt;script&gt;'));
if(process.env.REVIEW_FIXTURE){const html=`<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><link rel="stylesheet" href="assets/style.css"><link rel="stylesheet" href="assets/forms.css"><title>Пульс · проверка результата</title><div class="self-test-page"><header><strong>пульс.</strong><span>Результат теста · пример</span></header><main><section class="self-test-cover"><h1>Результат теста</h1><div class="self-test-score"><strong>50%</strong><span>1 из 2 баллов</span></div></section>${wrong}${correct}</main></div>`;fs.writeFileSync(process.env.REVIEW_FIXTURE,html);}
console.log('PASS: incorrect/correct choices, partial multi-answer, missing answer, neutral polls and escaping');
