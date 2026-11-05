'use strict';
const assert=require('node:assert/strict'),vm=require('node:vm'),fs=require('node:fs'),path=require('node:path');
const {indexedDB}=require(process.env.FAKE_INDEXEDDB_MODULE||'fake-indexeddb');
const source=fs.readFileSync(path.join(__dirname,'../web/offline.js'),'utf8');
let offline=false,loseResponse=false,copyCounter=0,serverNotes=new Map(),applied=new Map(),lockChain=Promise.resolve();
const original='1'.repeat(24);serverNotes.set(original,{id:original,title:'Общая заметка',body:'Исходная',folder_id:null,pinned:0,revision:1,created:1,updated:1,deleted:null});
const response=value=>({ok:true,status:200,headers:{get:()=>null},json:async()=>structuredClone(value)});
async function fetch(url,options={}){
 if(offline)throw new TypeError('Network offline');
 if(url==='/api/offline')return response({notes:[...serverNotes.values()],folders:[],csrf:'valid'});
 if(url==='/api/sync'){
  const op=JSON.parse(options.body);if(applied.has(op.mutation_id))return response(applied.get(op.mutation_id));
  const previous=op.after?applied.get(op.after):null;let id=previous?.id||op.entity.id,base=previous?.revision??op.base_revision,old=serverNotes.get(id),conflict=!!old&&old.revision!==base;
  if(conflict){id='9'.repeat(22)+(++copyCounter).toString(16).padStart(2,'0');old=null;}
  const n={...op.entity,id,title:op.entity.title+(conflict?' (конфликт)':''),revision:(old?.revision||0)+1,created:old?.created||Date.now()/1000,updated:Date.now()/1000};serverNotes.set(id,n);
  const result={id,revision:n.revision,conflict};applied.set(op.mutation_id,result);
  if(loseResponse){loseResponse=false;throw new TypeError('Response lost after server commit')}
  return response(result);
 }
 throw Error('Unexpected request: '+url);
}
function instance(){const events=new EventTarget(),doc=new EventTarget();doc.hidden=false;const navigator={locks:{request:(name,fn)=>{const job=lockChain.then(fn);lockChain=job.catch(()=>{});return job;}}};Object.defineProperty(navigator,'onLine',{get:()=>!offline});
 const context={console,window:events,document:doc,navigator,indexedDB,crypto:require('node:crypto').webcrypto,CustomEvent,URL,location:{origin:'https://notes.test'},fetch,setTimeout:()=>1,clearTimeout(){},setInterval(){},Date,Error,Promise,Uint8Array,Array,Object,Set,Number,String,JSON};vm.createContext(context);vm.runInContext(source,context);return events.NotesOffline;}
(async()=>{
 const first=instance();assert.equal((await first.request('/api/notes')).total,1);
 offline=true;
 let n=await first.request('/api/note/create',{});n=await first.request('/api/note/save',{...n,title:'Новая без интернета',body:'Сохранить после перезапуска',photos:[{name:'Фото',data:'data:image/jpeg;base64,/9j/dGVzdP/Z'}]});
 assert.equal((await first.state()).pending,2);
 const restarted=instance();assert.equal((await restarted.request('/api/note/'+n.id)).body,'Сохранить после перезапуска');assert.equal((await restarted.request('/api/notes')).total,2);assert.equal((await restarted.request('/api/note/'+n.id)).photos[0].name,'Фото');
 await assert.rejects(()=>restarted.sync());assert.equal((await restarted.state()).pending,2,'Network error must preserve queue');
 offline=false;await restarted.sync();assert.equal(serverNotes.get(n.id).body,'Сохранить после перезапуска');assert.equal((await restarted.state()).pending,0);
 offline=true;const old=await restarted.request('/api/note/'+original);await restarted.request('/api/note/save',{...old,body:'Моя офлайн-правка'});serverNotes.set(original,{...serverNotes.get(original),revision:2,body:'Другой компьютер'});
 offline=false;await restarted.sync();assert.equal(serverNotes.get(original).body,'Другой компьютер');assert.equal(copyCounter,1);
 const copy=[...serverNotes.values()].find(n=>n.body==='Моя офлайн-правка');assert.ok(copy);assert.ok(copy.title.includes('конфликт'));
 assert.equal((await restarted.request('/api/note/'+original)).body,'Другой компьютер','Original and conflict copy must remain separately selectable');
 let localCopy=await restarted.request('/api/note/'+copy.id);await restarted.request('/api/note/save',{...localCopy,body:'Ответ потеряется, запись останется'});
 loseResponse=true;await assert.rejects(()=>restarted.sync());assert.equal((await restarted.state()).pending,1);
 await restarted.sync();assert.equal((await restarted.state()).pending,0);assert.equal(serverNotes.get(copy.id).body,'Ответ потеряется, запись останется');assert.equal(copyCounter,1,'A lost response must not create a second conflict copy');
 offline=true;localCopy=await restarted.request('/api/note/'+copy.id);await restarted.request('/api/note/save',{...localCopy,body:'Не удалять при выходе'});
 await assert.rejects(()=>restarted.request('/api/logout',{}));assert.equal((await restarted.state()).pending,1);
 assert.equal((await instance().request('/api/note/'+copy.id)).body,'Не удалять при выходе');
 const stale=await restarted.request('/api/note/'+copy.id);const other=instance();await other.request('/api/note/save',{...stale,body:'Другое локальное окно'});const localConflict=await restarted.request('/api/note/save',{...stale,body:'Черновик из старого окна'});assert.notEqual(localConflict.id,copy.id);assert.equal((await other.request('/api/note/'+copy.id)).body,'Другое локальное окно');assert.equal((await instance().request('/api/note/'+localConflict.id)).body,'Черновик из старого окна');
 console.log('Offline restart, durable queue, reconnect sync, conflict copies, lost responses and safe logout: OK');
})().catch(e=>{console.error(e);process.exitCode=1});
