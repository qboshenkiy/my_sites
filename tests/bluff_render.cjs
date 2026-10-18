// Exercise the production renderers with HTTP fixtures, without browser/network state.
const fs=require('node:fs'),path=require('node:path'),vm=require('node:vm'),assert=require('node:assert/strict');
const fixtures=JSON.parse(fs.readFileSync(0,'utf8')),app={innerHTML:'',addEventListener(){}};
const context=vm.createContext({console,URL,Map,Set,Math,Date,JSON,String,Number,Array,Object,structuredClone,setTimeout,clearTimeout,requestAnimationFrame(){},
 document:{querySelector:s=>s==='#app'?app:null,addEventListener(){},activeElement:null},location:{href:'http://example.test/'},localStorage:{getItem:()=>null},navigator:{}});
vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/app.js'),'utf8').replace('\ninit();','\n'),context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets/bluff.js'),'utf8'),context);
context.fixtures=fixtures;
vm.runInContext("state=fixtures.choose;page='player';renderGame();",context);assert(app.innerHTML.includes('Выберите категорию'));
vm.runInContext("state=fixtures.write;renderGame();",context);assert(app.innerHTML.includes('id="bluff-text"'));assert(!app.innerHTML.includes('Ноах'));
vm.runInContext("state=fixtures.review;page='host';renderGame();",context);assert(app.innerHTML.includes('Проверьте варианты'));assert(app.innerHTML.includes('reject'));
vm.runInContext("state=fixtures.review;page='player';renderGame();",context);assert(!app.innerHTML.includes('reject'));assert(!app.innerHTML.includes('Правильный ответ'));
vm.runInContext("state=fixtures.vote;renderGame();",context);assert(app.innerHTML.includes('Где правда?'));assert(app.innerHTML.includes('Ваша выдумка'));assert(!app.innerHTML.includes('Выдумали:'));
vm.runInContext("state.choices[0].text='<script>alert(1)</script>';renderGame();",context);assert(app.innerHTML.includes('&lt;script&gt;'));assert(!app.innerHTML.includes('<script>'));
vm.runInContext("state=fixtures.write;page='projector';projectorMode=true;renderGame();",context);assert(!app.innerHTML.includes('id="bluff-text"'));assert(!app.innerHTML.includes('data-command="reveal"'));assert(!app.innerHTML.includes('Ноах'));
vm.runInContext("state=fixtures.results;page='host';projectorMode=false;renderGame();",context);assert(app.innerHTML.includes('Правда:'));assert(app.innerHTML.includes('Выдумали:'));assert(app.innerHTML.includes('Следующий игрок'));
vm.runInContext("boot={user:null};draft=fixtures.quiz;page='editor';drawEditor();",context);assert(app.innerHTML.includes('name="truth-0"'));assert(app.innerHTML.includes('name="aliases-0"'));
console.log('PASS: category selection, mobile lie form, anonymous voting, escaping, read-only projector, reveal and bluff editor rendering.');
