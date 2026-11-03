'use strict';
// Execute the browser script with window === global, as it is in a classic script.
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const elements=new Map(),tabs=['security','traffic','bots','alerts','protection','audit'].map(name=>({dataset:{tab:name},textContent:name,listeners:{},classList:{toggle(){}},parentElement:{},addEventListener(type,fn){this.listeners[type]=fn;}}));
function element(id){if(!elements.has(id))elements.set(id,{id,hidden:false,textContent:'',innerHTML:'',value:id==='period'?'3600':'',classList:{toggle(){}},addEventListener(){}});return elements.get(id);}
const responses={
 '/api/session':{csrf:'test'},
 '/api/security?period=3600':{ssh:[],http:{ips:[],events:[]},errors:{}},
 '/api/bots':{bots:[]},'/api/people?bot=marathon':{people:[]},
 '/api/protection':{ready:true,blocked:[],client_ip:'8.8.8.8'},'/api/audit':{events:[]},'/api/alerts':{alerts:[],unread:0,config:{http_limit:240,bot_limit:60,cooldown:600,scan_errors:{}}}
};
const requested=[],listeners={};
const nativeHistory={replaceState(state,title,url){context.location.hash=url;}};
const context={console,URL,Date,Number,String,Math,setInterval(){},innerWidth:1200,location:{hash:'#alerts'},history:nativeHistory,
 document:{getElementById:element,querySelectorAll(){return tabs;},querySelector(selector){return tabs.find(tab=>selector.includes('"'+tab.dataset.tab+'"'));}},
 addEventListener(type,fn){listeners[type]=fn;},fetch:async url=>{requested.push(url);return {ok:true,json:async()=>responses[url]||{}};}
};
context.window=context;vm.createContext(context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),context);
vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/network.js'),'utf8'),context);
listeners.DOMContentLoaded();
const settle=()=>new Promise(resolve=>setImmediate(resolve));
(async()=>{
 await settle();await settle();
 assert.equal(context.history,nativeHistory,'The app must preserve native window.history');
 for(const tab of tabs){
  tab.listeners.click();await settle();await settle();
  assert.equal(context.location.hash,'#'+tab.dataset.tab);
  assert.equal(element('title').textContent,tab.textContent);
  assert.ok(!element('notice').textContent.startsWith('Загрузка'),'Navigation must finish rendering');
 }
 for(const url of ['/api/security?period=3600','/api/bots','/api/alerts','/api/audit'])assert.ok(requested.includes(url),url);
 console.log('PASS: all six tabs render and native browser history stays intact');
})().catch(error=>{console.error(error);process.exitCode=1;});
