const fs=require('node:fs'),vm=require('node:vm'),assert=require('node:assert/strict');
const s=fs.readFileSync(__dirname+'/index.html','utf8'),a=s.indexOf('function deckProjectStatus('),b=s.indexOf('function render(){',a);
const context={state:{jobs:[],versions:{}},active:j=>['queued','running'].includes(j.status)};vm.createContext(context);vm.runInContext(s.slice(a,b),context);
const p={id:'pulse'};assert.equal(context.deckProjectStatus(p).key,'missing');context.state.versions.pulse={commit_sha:'abc'};assert.equal(context.deckProjectStatus(p).key,'ready');
context.state.jobs=[{project:'pulse',status:'failed'}];assert.equal(context.deckProjectStatus(p).key,'failed');context.state.jobs.unshift({project:'pulse',status:'running'});assert.equal(context.deckProjectStatus(p).key,'running');context.state.jobs.unshift({project:'pulse',status:'success'});assert.equal(context.deckProjectStatus(p).key,'ready');assert.equal(context.deckProjectStatus({id:'other'}).key,'missing');
console.log('PASS: project install status, latest failure/recovery, running state and unknown version');
