import data from './words.json' with {type:'json'}

export type Entry = {id:number; kg:string; ru:string; topic:string}
export const words:Entry[] = data
export const topics = [...new Set(words.map(w=>w.topic))]
export const wordById = new Map(words.map(w=>[w.id,w]))
export type Rating = 'again'|'hard'|'good'
export type Memory = {box:number; due:number; at:number; seen:number; lapses:number}
export type Task = {word:number; mode:'discover'|'choice'|'recall'; retry?:boolean}
export type Session = {id:string; tasks:Task[]; cursor:number; answers:number; mistakes:number; failed:number[]; started:number; topic:string; newCount:number; reviewCount:number}
export type VocabState = {
  cards:Record<string,Memory>; dailyNew:number; topic:string;
  activity:Record<string,{introduced:number;answers:number}>;
  session?:Session; settingsAt:number;
}
export const emptyVocabulary = ():VocabState => ({cards:{},dailyNew:5,topic:'',activity:{},settingsAt:0})
export function localDay(at=Date.now()) {
  const d=new Date(at)
  return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`
}
export function clean(text:string) {
  return text.normalize('NFC').toLocaleLowerCase('ru').replace(/ё/g,'е').replace(/[\p{P}\p{S}]/gu,' ').replace(/\s+/g,' ').trim()
}
export function matches(input:string, answer:string, forgiving=false) {
  const actual=clean(input), expected=clean(answer)
  return actual===expected || (forgiving&&!/[ңөү]/iu.test(input)&&actual===expected.replace(/ң/g,'н').replace(/ө/g,'о').replace(/ү/g,'у'))
}
export function status(card:Memory|undefined,now=Date.now()) {
  return !card?'new':card.due<=now?'due':card.box>=3?'known':'learning'
}
export function counters(state:VocabState,now=Date.now()) {
  const cards=words.flatMap(w=>state.cards[w.id]?[state.cards[w.id]]:[])
  return {started:cards.length,known:cards.filter(c=>c.box>=3).length,due:cards.filter(c=>c.due<=now).length,
    today:state.activity[localDay(now)]??{introduced:0,answers:0}}
}
const topicPriority=['Главные глаголы','Действия каждый день','Основа общения','Кухня и еда','Люди и семья','Связки и обстоятельства']
const learningOrder=[...words].sort((a,b)=>{
  const rank=(t:string)=>{const n=topicPriority.indexOf(t);return n<0?100+topics.indexOf(t):n}
  return rank(a.topic)-rank(b.topic)||a.id-b.id
})
export function buildSession(state:VocabState,kind:'daily'|'review'|'extra'='daily',now=Date.now(),id:string=crypto.randomUUID()):Session|undefined {
  const due=words.filter(w=>state.cards[w.id]?.due<=now).sort((a,b)=>state.cards[a.id].due-state.cards[b.id].due).slice(0,10)
  const quota=kind==='review'?0:kind==='extra'?state.dailyNew:Math.max(0,state.dailyNew-(state.activity[localDay(now)]?.introduced??0))
  const added=learningOrder.filter(w=>!state.cards[w.id]&&(!state.topic||w.topic===state.topic)).slice(0,quota)
  const reviewing=kind==='extra'?[]:due
  const tasks:Task[]=[...reviewing.map(w=>({word:w.id,mode:'recall' as const})),
    ...added.flatMap(w=>[{word:w.id,mode:'discover' as const},{word:w.id,mode:'choice' as const}]),
    ...added.map(w=>({word:w.id,mode:'recall' as const}))]
  return tasks.length?{id,tasks,cursor:0,answers:0,mistakes:0,failed:[],started:now,topic:state.topic,newCount:added.length,reviewCount:reviewing.length}:undefined
}
// Every completed step is saved together with the cursor: reopening never marks unseen words as learned.
export function advance(state:VocabState,rating:Rating='good',now=Date.now()):VocabState {
  const s=state.session
  if (!s||s.cursor>=s.tasks.length) return state
  const task=s.tasks[s.cursor],key=String(task.word),previous=state.cards[key]
  const cards={...state.cards},activity={...state.activity}
  const today={...(activity[localDay(now)]??{introduced:0,answers:0})}
  const next:Session={...s,cursor:s.cursor+1,failed:[...s.failed],tasks:[...s.tasks]}
  if(task.mode==='discover') {
    if(!previous) {cards[key]={box:0,due:now,at:now,seen:0,lapses:0};today.introduced++}
  } else {
    today.answers++;next.answers++
    if(rating==='again') {next.mistakes++;if(!next.failed.includes(task.word)) next.failed.push(task.word)}
    const old=previous??{box:0,due:now,at:now,seen:0,lapses:0}
    // Recognition does not advance intervals. Failure caps a later same-session recall to a short retry.
    if(task.mode==='recall'||rating==='again') {
      const failed=next.failed.includes(task.word)
      const box=rating==='again'||failed?0:rating==='hard'?Math.min(old.box,1):Math.min(old.box+1,5)
      const delay=rating==='again'||failed?10*60000:rating==='hard'?4*3600000:[0,1,3,7,14,30][box]*86400000
      cards[key]={box,due:now+delay,at:now,seen:old.seen+1,lapses:old.lapses+Number(rating==='again')}
    }
    if(rating==='again'&&!task.retry&&!next.tasks.some(t=>t.word===task.word&&t.retry)) next.tasks.push({word:task.word,mode:'recall',retry:true})
  }
  activity[localDay(now)]=today
  return {...state,cards,activity,session:next}
}
export function choices(word:Entry,seed=0) {
  const result=[word.ru], pool=words.filter(w=>w.id!==word.id)
  let cursor=(word.id*17+seed*7)%pool.length
  for(let i=0;result.length<4&&i<pool.length;i++,cursor=(cursor+37)%pool.length) {
    const ru=pool[cursor].ru
    if(!result.includes(ru))result.push(ru)
  }
  return result.sort((a,b)=>hash(a+seed)-hash(b+seed))
}
function hash(s:string){let n=0;for(const c of s)n=(n*31+c.charCodeAt(0))|0;return n>>>0}
export function mergeVocabulary(local:VocabState|undefined,remote:VocabState|undefined):VocabState {
  const a=local??emptyVocabulary(),b=remote??emptyVocabulary(),cards={...b.cards}
  for(const [id,c] of Object.entries(a.cards)) if(!cards[id]||c.at>=cards[id].at)cards[id]=c
  const activity={...b.activity}
  for(const [day,v] of Object.entries(a.activity)) {
    const other=activity[day]??{introduced:0,answers:0}
    // A conservative merge avoids duplicating the same offline practice on repeated syncs.
    activity[day]={introduced:Math.max(other.introduced,v.introduced),answers:Math.max(other.answers,v.answers)}
  }
  const settings=a.settingsAt>=b.settingsAt?a:b
  return {...settings,cards,activity,session:a.session}
}
export function parseBackup(text:string):VocabState {
  if(text.length>2_000_000)throw new Error('Файл слишком большой.')
  const payload=JSON.parse(text)
  if(payload?.format!=='suilo-vocabulary'||payload.version!==1||!payload.vocabulary)throw new Error('Нужна резервная копия словаря Сүйлө.')
  const source=payload.vocabulary
  const integer=(v:unknown,max:number):v is number=>typeof v==='number'&&Number.isSafeInteger(v)&&v>=0&&v<=max
  const state=emptyVocabulary()
  if(!source.cards||typeof source.cards!=='object'||Array.isArray(source.cards)||Object.keys(source.cards).length>words.length)throw new Error('Повреждены карточки.')
  for(const [id,value] of Object.entries(source.cards)) {
    const c=value as Memory
    if(!wordById.has(Number(id))||String(Number(id))!==id||!c||!integer(c.box,5)||!integer(c.due,1e14)||!integer(c.at,1e14)||!integer(c.seen,1e7)||!integer(c.lapses,1e7))throw new Error('Повреждена карточка '+id+'.')
    state.cards[id]={box:c.box,due:c.due,at:c.at,seen:c.seen,lapses:c.lapses}
  }
  if(![3,5,10,15].includes(source.dailyNew)||typeof source.topic!=='string'||(source.topic&&!topics.includes(source.topic)))throw new Error('Повреждены настройки.')
  if(!source.activity||typeof source.activity!=='object'||Array.isArray(source.activity)||Object.keys(source.activity).length>36500)throw new Error('Повреждена история.')
  for(const [date,value] of Object.entries(source.activity)) {
    const v=value as {introduced:number;answers:number}
    if(!/^\d{4}-\d{2}-\d{2}$/.test(date)||!v||!integer(v.introduced,1000)||!integer(v.answers,1e7))throw new Error('Повреждена история занятий.')
    state.activity[date]={introduced:v.introduced,answers:v.answers}
  }
  return {...state,dailyNew:source.dailyNew,topic:source.topic,settingsAt:Date.now()}
}
