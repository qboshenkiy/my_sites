// Render the production scripts with API fixtures, without browser/network state.
const fs=require('node:fs'),vm=require('node:vm'),path=require('node:path'),assert=require('node:assert/strict');
const fixture=JSON.parse(fs.readFileSync(0,'utf8')),app={innerHTML:'',addEventListener(){}},added=[];
const context=vm.createContext({console,URL,Date,Intl,Math,JSON,Number,String,Object,Array,Set,Map,structuredClone,setTimeout,clearTimeout,requestAnimationFrame(){},
 document:{querySelector:s=>s==='#app'?app:s==='.reader-summary'?{after:n=>added.push(n.innerHTML)}:null,querySelectorAll:()=>[],addEventListener(){},createElement:()=>({innerHTML:''})},location:{href:'http://example.test/'},localStorage:{getItem:()=>null},navigator:{}});
for(const name of ['app.js','v2.js','v3.js','users.js','rounds.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../assets',name),'utf8'),context,{filename:name});
context.fixture=fixture;
vm.runInContext('boot={user:fixture.user,marathon:fixture.marathon,telegram:{configured:false}};profileData=fixture;drawProfile();',context);
assert(app.innerHTML.includes('Круг 3 · завершено кругов: 2'));
assert(app.innerHTML.includes('История повторов · 2'));
assert(!app.innerHTML.includes('Неделя 3'));
assert(added.some(html=>html.includes('43%')&&html.includes('3 из 7 глав')));
// A completed weekly pass offers its own repeat without waiting for 22 weeks.
vm.runInContext('profileData.stats.pace.completed=true;drawProfile();',context);
assert(app.innerHTML.includes('Прочитать этот план ещё раз'));
// A pre-start account has no future plans or rendering errors.
vm.runInContext('profileData.marathon.current=0;profileData.marathon.calendar=[];profileData.stats.pace=null;profileData.stats.reports=[];profileData.stats.entries=[];drawProfile();',context);
assert(app.innerHTML.includes('Марафон скоро начнётся'));
assert(!app.innerHTML.includes('Неделя 1'));
console.log('PASS: weekly profile rendering, repeat action, history, current-week percentage and pre-start future privacy.');
