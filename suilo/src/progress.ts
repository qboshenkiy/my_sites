import { openDB } from 'idb'
import type { Exercise, Word } from './course'

export type Attempt = { id: string; day: string; xp: number; at: number }
export type Completion = { mistakes: number; xp: number; day: string; at: number }
export type Card = { box: number; due: number; at: number }
export type Mistake = { id: string; prompt: string; given: string; expected: string; at: number }
export type Draft = { id: string; index: number; mistakes: number }
export type PersonalWord = {id:string; ru:string; ky:string; at:number; deleted?:boolean}
export type Progress = {
  personalWords: Record<string, PersonalWord>
  name: string; level: string; goal: number; theme: 'light' | 'dark' | 'system'; forgiving: boolean;
  completed: Record<string, Completion>; activity: Attempt[]; cards: Record<string, Card>; errors: Mistake[]; draft?: Draft;
}
export const fresh: Progress = {name:'',level:'A0',goal:30,theme:'system',forgiving:false,personalWords:{},completed:{},activity:[],cards:{},errors:[]}
let connection: ReturnType<typeof openDB> | undefined
const database = () => connection ??= openDB('suilo', 1, {upgrade(db) {db.createObjectStore('progress')}}).catch(error=>{connection=undefined;throw error})
export async function load() { return {...fresh, ...(await (await database()).get('progress','local'))} as Progress }
export async function persist(p: Progress) { await (await database()).put('progress',p,'local') }
export function day(date = new Date()) {
  return [date.getFullYear(),date.getMonth()+1,date.getDate()].map(v=>String(v).padStart(2,'0')).join('-')
}
export function streak(activity: Attempt[]) {
  const days = new Set(activity.map(a=>a.day))
  const date = new Date()
  if (!days.has(day(date))) date.setDate(date.getDate()-1)
  let n = 0
  while (days.has(day(date))) { n++; date.setDate(date.getDate()-1) }
  return n
}
export const daily = (p:Progress) => p.activity.filter(a=>a.day===day()).reduce((sum,a)=>sum+a.xp,0)
export const total = (p:Progress) => p.activity.reduce((sum,a)=>sum+a.xp,0)
const intervals = [0, 1, 3, 7, 14, 30]
export function schedule(card:Card | undefined, known:boolean, now=Date.now()):Card {
  const box = known ? Math.min((card?.box ?? 0)+1,intervals.length-1) : 0
  return {box,at:now,due:now+(box ? intervals[box]*86400000 : 10*60000)}
}
export function addWords(p:Progress, words:Word[]) {
  const cards = {...p.cards}
  for (const word of words) cards[word.ky] ??= {box:0,due:Date.now(),at:Date.now()}
  return cards
}
export function normalize(value:string, forgive=false) {
  const cleaned = value.normalize('NFC').toLocaleLowerCase('ru').replace(/ё/g,'е')
    .replace(/[\p{P}\p{S}]/gu,' ').replace(/\s+/g,' ').trim()
  return forgive ? cleaned.replace(/ң/g,'н').replace(/ө/g,'о').replace(/ү/g,'у') : cleaned
}
export const accepts = (input:string, answers:string[], forgiving=false) =>
  answers.some(a=>normalize(input)===normalize(a) ||
    (forgiving && !/[ңөү]/iu.test(input) && normalize(input,true)===normalize(a,true)))
export const review = (word:Word): Exercise => ({
  kind:'review', prompt:word.ru, answers:word.ky.split(' / '), why:word.example,
})
export function parsePersonalWords(input:string) {
  const words: Pick<PersonalWord,'ru'|'ky'>[] = []
  const invalid: number[] = []
  for (const [index, line] of input.split(/\r?\n/).entries()) {
    if (!line.trim()) continue
    const parts=line.trim().split(/\t+|;|[–—]|\s+-\s+/u)
    const [ru, raw] = parts.map(part=>part.trim())
    const variants=raw?.split('/').map(part=>part.trim()) ?? []
    if (parts.length!==2 || !normalize(ru) || ru.length>160 ||
        !variants.length || variants.some(variant=>!normalize(variant)) || raw.length>160) {
      invalid.push(index+1)
      continue
    }
    words.push({ru,ky:variants.join(' / ')})
  }
  return {words,invalid}
}
export function mergeProgress(local:Progress, cloud:Progress):Progress {
  const cards = {...cloud.cards}
  for (const [key, card] of Object.entries(local.cards)) if (!cards[key] || cards[key].at <= card.at) cards[key]=card
  const completed = {...cloud.completed}
  for (const [key, value] of Object.entries(local.completed)) {
    const other = completed[key]
    if (!other || value.at < other.at) completed[key] = value
  }
  const activity = new Map([...cloud.activity,...local.activity].map(a=>[a.id,a]))
  for (const [id,c] of Object.entries(completed)) activity.set(id,{id,day:c.day,xp:c.xp,at:c.at})
  const errors = new Map([...cloud.errors,...local.errors].map(a=>[a.id,a]))
  const personalWords = {...cloud.personalWords}
  for (const [key, word] of Object.entries(local.personalWords)) {
    if (!personalWords[key] || personalWords[key].at <= word.at) personalWords[key]=word
  }
  return {...local, personalWords,cards,completed,activity:[...activity.values()],errors:[...errors.values()].sort((a,b)=>b.at-a.at).slice(0,100)}
}
