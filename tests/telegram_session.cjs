const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const source=fs.readFileSync('assets/app.js','utf8');
const api=source.slice(source.indexOf('async function api('),source.indexOf('function reportSiteLog('));
async function run(action,responses){
 const calls=[];const context={boot:{csrf:'old'},AbortController,setTimeout,clearTimeout,projectorMode:false,player:null,reportSiteLog(){},fetch:async(url,options)=>{calls.push({url,options});const r=responses.shift();if(!r)throw Error('Unexpected retry');return {status:r.status,ok:r.status<400,json:async()=>r.body};}};
 vm.createContext(context);vm.runInContext(api,context);
 try{return {result:await context.api(action,{initData:'signed'}),calls};}catch(error){return {error,calls};}
}
(async()=>{
 const expired={status:403,body:{code:'csrf_expired',error:'Обновите страницу и повторите.'}};
 const fresh={status:200,body:{csrf:'fresh',user:null}},success={status:200,body:{ok:true}};
 for(const action of ['pulse_miniapp_login','pulse_telegram_request','pulse_telegram_status']){
  const r=await run(action,[expired,fresh,success]);assert.equal(r.result.ok,true);assert.equal(r.calls.length,3);
  assert.equal(r.calls[2].options.headers['X-CSRF-Token'],'fresh');assert.equal(r.calls[2].options.body,r.calls[0].options.body);
 }
 const repeated=await run('pulse_miniapp_login',[expired,fresh,expired]);assert.ok(repeated.error);assert.equal(repeated.calls.length,3);
 const denied=await run('pulse_miniapp_login',[{status:403,body:{error:'Telegram not linked'}}]);assert.ok(denied.error);assert.equal(denied.calls.length,1);
 const mutation=await run('save',[expired]);assert.ok(mutation.error);assert.equal(mutation.calls.length,1);
 console.log('PASS: Telegram CSRF recovery retries once with fresh token, preserves request, and never retries other failures or editing actions');
})().catch(error=>{console.error(error);process.exitCode=1;});
