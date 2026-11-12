import test from 'node:test'
import assert from 'node:assert/strict'
import {advance,buildSession,choices,counters,emptyVocabulary,localDay,matches,mergeVocabulary,parseBackup,status,topics,words} from '../src/vocabulary/model.ts'
const now=new Date(2026,10,12,12).getTime()
const begin=(state=emptyVocabulary(),kind='daily',at=now)=>({...state,session:buildSession(state,kind,at,'test-session')})
const payload=vocabulary=>JSON.stringify({format:'suilo-vocabulary',version:1,vocabulary})

test('the complete embedded deck has 1000 unique entries and 25 balanced topics',()=>{
  assert.equal(words.length,1000);assert.equal(new Set(words.map(w=>w.id)).size,1000)
  assert.equal(new Set(words.map(w=>w.kg)).size,1000);assert.equal(topics.length,25)
  for(const topic of topics)assert.equal(words.filter(w=>w.topic===topic).length,40)
  for(const word of words) {assert.ok(word.kg&&word.ru);const options=choices(word,3);assert.equal(options.length,4);assert.equal(new Set(options).size,4);assert.ok(options.includes(word.ru))}
})
test('new words are shown before either recognition or recall; planning does not alter progress',()=>{
  const state=emptyVocabulary(),s=buildSession(state,'daily',now,'test')
  assert.equal(s.newCount,5);assert.equal(s.tasks.length,15);assert.deepEqual(state.cards,{})
  for(const id of new Set(s.tasks.map(t=>t.word))){assert.deepEqual(s.tasks.filter(t=>t.word===id).map(t=>t.mode),['discover','choice','recall'])}
  assert.equal(s.tasks[0].word,81)
})
test('reading one card only introduces that word and a serialized session resumes exactly',()=>{
  const state=advance(begin(),'good',now),restored=JSON.parse(JSON.stringify(state))
  assert.equal(counters(state,now).started,1);assert.equal(counters(state,now).known,0)
  assert.equal(state.session.cursor,1);assert.equal(restored.session.tasks[1].mode,'choice')
  assert.equal(state.activity[localDay(now)].introduced,1)
})
test('successful recall is scheduled tomorrow; recognition alone does not grant mastery',()=>{
  let state=advance(begin(),'good',now)
  state=advance(state,'good',now)
  assert.equal(state.cards['81'].box,0)
  while(state.session.cursor<state.session.tasks.length)state=advance(state,'good',now)
  assert.equal(counters(state,now).started,5);assert.equal(counters(state,now).known,0)
  assert.equal(state.cards['81'].box,1);assert.equal(state.cards['81'].due,now+86400000)
  assert.equal(buildSession(state,'daily',now,'x'),undefined)
  assert.equal(buildSession(state,'extra',now,'x').newCount,5)
})
test('failure and using help keep a short interval even after a correct same-session retry',()=>{
  let state=advance(begin(),'good',now)
  state=advance(state,'again',now)
  while(state.session.cursor<state.session.tasks.length)state=advance(state,'good',now)
  assert.equal(state.cards['81'].box,0);assert.equal(state.cards['81'].due,now+600000)
  assert.equal(state.session.mistakes,1);assert.equal(state.session.tasks.filter(t=>t.word===81&&t.retry).length,1)
})
test('repeated failure cannot produce an endless session',()=>{
  let state=begin();let steps=0
  while(state.session.cursor<state.session.tasks.length&&steps<100){state=advance(state,'again',now);steps++}
  assert.ok(steps<100);assert.equal(state.session.tasks.length,20)
  assert.equal(state.session.tasks.filter(t=>t.retry).length,5)
})
test('hard recall is due earlier and never counts as a confident promotion',()=>{
  const state=emptyVocabulary();state.cards['81']={box:2,due:now,at:now-1,seen:3,lapses:0}
  const result=advance(begin(state,'review'),'hard',now)
  assert.equal(result.cards['81'].box,1);assert.equal(result.cards['81'].due,now+4*3600000)
})
test('daily limits, selected topic and overdue review operate independently',()=>{
  const state=emptyVocabulary();state.topic='Вера, чтение, музыка и внутренний мир'
  state.activity[localDay(now)]={introduced:4,answers:0};state.cards['81']={box:1,due:now-1,at:now-2,seen:1,lapses:0}
  const s=buildSession(state,'daily',now,'x');assert.equal(s.newCount,1);assert.equal(s.reviewCount,1)
  assert.equal(s.tasks[0].word,81);assert.equal(s.tasks[1].word,961)
  assert.equal(buildSession(state,'review',now,'x').newCount,0)
  assert.equal(buildSession(state,'daily',now+86400000,'x').newCount,5)
})
test('all introduced words, including partially studied ones, remain in review',()=>{
  const state=advance(begin(),'good',now)
  assert.equal(buildSession({...state,session:undefined},'review',now,'x').tasks[0].word,81)
  assert.equal(status(state.cards['81'],now),'due')
})
test('Kyrgyz letters are exact by default; optional forgiving input is limited',()=>{
  assert.ok(matches(' ҮЙРӨНҮҮ! ','үйрөнүү'));assert.ok(!matches('уйронуу','үйрөнүү'))
  assert.ok(matches('уйронуу','үйрөнүү',true));assert.ok(!matches('үйронуу','үйрөнүү',true))
  assert.ok(!matches('үйрөтүү','үйрөнүү',true))
})
test('legacy progress without a vocabulary field merges without losing vocabulary or doubling counts',()=>{
  const local=advance(begin(),'good',now),merged=mergeVocabulary(local,undefined)
  assert.equal(merged.cards['81'].box,0);assert.equal(merged.session.cursor,1)
  assert.deepEqual(mergeVocabulary(local,local),local)
  const older=structuredClone(local);older.cards['81'].at--;older.cards['81'].box=5
  assert.equal(mergeVocabulary(local,older).cards['81'].box,0)
})
test('backups round-trip and reject invalid data before changing progress',()=>{
  const state=advance(begin(),'good',now),parsed=parseBackup(payload(state))
  assert.deepEqual(parsed.cards,state.cards);assert.equal(parsed.session,undefined)
  for(const bad of ['{}','null','not-json',payload({...state,cards:{'9000':state.cards['81']}}),payload({...state,dailyNew:999}),payload({...state,cards:{'81':{...state.cards['81'],due:-1}}})])assert.throws(()=>parseBackup(bad))
})
