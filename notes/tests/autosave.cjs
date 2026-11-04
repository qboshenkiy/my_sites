'use strict';
const vm=require('node:vm'),fs=require('node:fs'),path=require('node:path'),assert=require('node:assert/strict');
const elements=new Map(),saves=[];
function element(selector){if(!elements.has(selector))elements.set(selector,{value:'',textContent:'',innerHTML:'',hidden:false,dataset:{},classList:{add(){},remove(){},toggle(){}},addEventListener(){},setAttribute(){},showModal(){},close(){},focus(){}});return elements.get(selector)}
const state={notes:[],folders:[],counts:{all:0,pinned:0,trash:0},total:0,csrf:'test-csrf'};
const context={console,Intl,URLSearchParams,URL,Blob,Date,Error,Promise,Number,String,Math,confirm:()=>true,setTimeout:()=>1,clearTimeout(){},navigator:{},location:{reload(){}},
 document:{body:{dataset:{}},querySelector:element,querySelectorAll:()=>[],addEventListener(){},createElement(){return {click(){}}}},
 window:{addEventListener(){}},fetch:async(url,options)=>{
  if(url==='/api/note/save')return new Promise(resolve=>saves.push({data:JSON.parse(options.body),resolve}));
  return {ok:true,json:async()=>state};
 }};
vm.createContext(context);vm.runInContext(fs.readFileSync(path.join(__dirname,'../web/app.js'),'utf8'),context);
const run=code=>vm.runInContext(code,context),settle=()=>new Promise(resolve=>setImmediate(resolve));
function resolveSave(index,status=200){const request=saves[index];request.resolve({ok:status===200,status,json:async()=>status===200?{...request.data,revision:request.data.revision+1}:{error:'conflict'}})}
(async()=>{
 await settle();run("renderEditor({id:'note',revision:1,title:'',body:'',folder_id:null,pinned:false,deleted:null})");
 element('#noteBody').value='Первая правка';run('markDirty()');const first=run('flush()');await settle();assert.equal(saves.length,1);
 element('#noteBody').value='Новая правка во время сохранения';run('current.pinned=true;markDirty()');const concurrent=run('flush()');await settle();assert.equal(saves.length,1,'Concurrent saves must be serialized');
 resolveSave(0);await settle();assert.equal(saves.length,2);assert.equal(saves[1].data.revision,2);assert.equal(saves[1].data.body,'Новая правка во время сохранения');assert.equal(saves[1].data.pinned,true,'A pin change during an in-flight save must not be lost');
 resolveSave(1);assert.equal(await first,true);assert.equal(await concurrent,true);assert.equal(run('dirty()'),false);assert.equal(context.document.body.dataset.unsaved,'false');
 element('#noteBody').value='Черновик при конфликте';run('markDirty()');const conflict=run('flush()');await settle();resolveSave(2,409);assert.equal(await conflict,false);assert.equal(run('dirty()'),true);assert.equal(element('#noteBody').value,'Черновик при конфликте');assert.equal(element('#conflict').hidden,false);
 assert.equal(await run('flush()'),false);assert.equal(saves.length,3,'Conflict must not cause an automatic overwrite retry');
 console.log('Autosave serialization, concurrent edits, pin intent and conflict recovery: OK');
})().catch(e=>{console.error(e);process.exitCode=1});
