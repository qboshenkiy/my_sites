import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, BookOpen, Check, CheckCheck, ChevronRight, Download, Eye, Flame, Layers, RotateCcw, Search, Settings2, Sparkles, Upload, Volume2, X } from 'lucide-react'
import { advance, buildSession, choices, counters, localDay, matches, mergeVocabulary, parseBackup, status, topics, wordById, words, type Entry, type Rating, type VocabState } from './vocabulary/model'
import { examples } from './vocabulary/examples'
import { isNative, speak, telegramBack } from './platform'
import { registerPlugin } from '@capacitor/core'
import './vocabulary.css'

const NativeBackup=registerPlugin<{save(options:{text:string;filename:string}):Promise<{cancelled:boolean}>}>('StudyBackup')
const plural=(n:number)=>`${n} ${n%100>=11&&n%100<=14?'слов':n%10===1?'слово':n%10>=2&&n%10<=4?'слова':'слов'}`

type Props={state:VocabState;save:(next:VocabState)=>Promise<void>;view:'home'|'dictionary'|'settings'|'stats';forgiving:boolean}
const labels={new:'Новое',due:'Пора повторить',learning:'Учу',known:'Закреплено'}
const formatDate=(at:number)=>new Date(at).toLocaleString('ru',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})

function Example({word,expanded=false}:{word:Entry;expanded?:boolean}) {
  const e=examples[word.kg]
  if(!e)return <p className="vocab-note">{word.kg.includes(' ')?'Запоминайте это выражение целиком.':'Запомните основное значение. Остальные значения зависят от контекста.'}</p>
  return <div className="vocab-example"><span>В ЖИВОЙ ФРАЗЕ</span><p lang="ky">{e.ky}</p><small>{e.ru}</small>
    {e.forms&&<details open={expanded||undefined}><summary>Как меняется слово <ChevronRight size={14}/></summary><div className="vocab-forms">{e.forms.map(([ky,ru])=><div key={ky}><b lang="ky">{ky}</b><small>{ru}</small></div>)}</div><small>Это готовые примеры, а не универсальные окончания для всех глаголов.</small></details>}
  </div>
}
function Sound({word}:{word:Entry}) {
  const [unavailable,setUnavailable]=useState(false)
  return <div className="vocab-sound"><button className="icon-button" aria-label={'Послушать '+word.kg} onClick={()=>{setUnavailable(false);speak(word.kg,()=>setUnavailable(true))}}><Volume2 size={20}/></button>{unavailable&&<small role="status">На устройстве нет кыргызского голоса.</small>}</div>
}
export function Vocabulary({state,save,view,forgiving}:Props) {
  const [active,setActive]=useState(false),[search,setSearch]=useState(''),[topic,setTopic]=useState(''),[filter,setFilter]=useState('all')
  const [selected,setSelected]=useState<Entry>(),[message,setMessage]=useState(''),[busy,setBusy]=useState(false)
  const lock=useRef(false),file=useRef<HTMLInputElement>(null)
  const [now,setNow]=useState(Date.now())
  useEffect(()=>{const t=setInterval(()=>setNow(Date.now()),30000);const wake=()=>setNow(Date.now());window.addEventListener('focus',wake);return()=>{clearInterval(t);window.removeEventListener('focus',wake)}},[])
  useEffect(()=>active&&view==='home'?telegramBack(()=>setActive(false)):undefined,[active,view])
  const count=counters(state,now),s=state.session
  async function write(next:VocabState) {
    if(lock.current)return false
    lock.current=true;setBusy(true);setMessage('')
    try {await save(next);setNow(Date.now());return true}
    catch {setMessage('Не удалось сохранить. Попробуйте ещё раз; текущий шаг не потерян.');return false}
    finally {lock.current=false;setBusy(false)}
  }
  async function start(kind:'daily'|'review'|'extra') {
    const session=buildSession(state,kind)
    if(!session){setMessage(kind==='review'?'Сейчас нет слов для повторения.':state.topic?'Новых слов в этой теме больше нет. Выберите другую тему.':'Все слова уже добавлены в обучение. Возвращайтесь к повторению.');return}
    if(await write({...state,session})){setActive(true);window.scrollTo(0,0)}
  }
  async function step(rating:Rating) {return write(advance(state,rating))}
  async function finish() {if(await write({...state,session:undefined}))setActive(false)}
  async function backup() {
    const {session:_,...vocabulary}=state
    const text=JSON.stringify({format:'suilo-vocabulary',version:1,vocabulary},null,2)
    const filename=`suilo-words-${localDay()}.json`
    setMessage('')
    if(isNative()) {
      setBusy(true)
      try {const result=await NativeBackup.save({text,filename});if(!result.cancelled)setMessage('Резервная копия сохранена.')}
      catch {setMessage('Не удалось сохранить копию. Попробуйте выбрать другую папку.')}
      finally {setBusy(false)}
      return
    }
    const url=URL.createObjectURL(new Blob([text],{type:'application/json'})),link=document.createElement('a')
    link.href=url;link.download=filename;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)
  }
  async function restore(input:File|undefined) {
    if(!input)return
    try {
      if(input.size>2_000_000)throw new Error('Файл слишком большой.')
      const restored=parseBackup(await input.text())
      if(await write(mergeVocabulary({...state,session:undefined},restored))) {setActive(false);setMessage('Прогресс объединён с резервной копией. Более новые результаты сохранены.')}
    }catch(error){setMessage(error instanceof Error?error.message:'Не удалось прочитать файл.')}
    finally {if(file.current)file.current.value=''}
  }
  if(view==='home'&&active&&s) {
    if(s.cursor>=s.tasks.length) return <section className="vocab-finish surface"><span className="vocab-emblem"><CheckCheck size={34}/></span><span className="eyebrow">ЕЩЁ ОДИН ШАГ К РАЗГОВОРУ</span><h1>На сегодня — больше слов.</h1><p>Ошибки не обнуляют занятие. Сложные слова вернутся раньше остальных.</p><div className="vocab-finish-grid"><div><b>{s.newCount}</b><span>новых слов в занятии</span></div><div><b>{s.answers}</b><span>ответов</span></div><div><b>{s.mistakes}</b><span>сложных ответов</span></div></div><button className="primary" disabled={busy} onClick={()=>void finish()}>К моему словарю <ArrowRight size={18}/></button>{message&&<p role="alert">{message}</p>}</section>
    const task=s.tasks[s.cursor],word=wordById.get(task.word)
    if(!word)return <p role="alert">Не удалось найти карточку. <button onClick={()=>void finish()}>Завершить занятие</button></p>
    return <div className="vocab-session"><header className="vocab-session-header"><button className="icon-button" aria-label="Отложить занятие" onClick={()=>setActive(false)}><X size={23}/></button><div><span>{task.mode==='discover'?'ЗНАКОМСТВО':task.mode==='choice'?'УЗНАВАНИЕ':'ВСПОМИНАНИЕ'}</span><b>{s.cursor+1} <small>/ {s.tasks.length}</small></b></div><span className="vocab-session-count"><Layers size={17}/> {s.newCount+s.reviewCount}</span></header><div className="vocab-progress" role="progressbar" aria-label="Пройдено шагов" aria-valuemin={0} aria-valuemax={s.tasks.length} aria-valuenow={s.cursor}><i style={{width:`${100*s.cursor/s.tasks.length}%`}}/></div>
      <StudyStep key={`${s.id}:${s.cursor}`} word={word} mode={task.mode} seed={s.cursor} forgiving={forgiving} busy={busy} next={step}/>
      {message&&<p className="notice" role="alert">{message}</p>}
    </div>
  }
  const filtered=words.filter(w=>(!topic||w.topic===topic)&&(filter==='all'||status(state.cards[w.id],now)===filter)&&`${w.kg} ${w.ru}`.toLocaleLowerCase('ru').includes(search.trim().toLocaleLowerCase('ru')))
  const resume=!!s&&s.cursor<s.tasks.length
  const next=buildSession(state,'daily',now,'preview')
  if(view==='settings')return <section className="surface vocab-settings"><header><Settings2 size={22}/><h2>Мой темп обучения</h2></header><label>Новых слов в день<select value={state.dailyNew} disabled={busy} onChange={e=>void write({...state,dailyNew:Number(e.target.value),settingsAt:Date.now()})}>{[3,5,10,15].map(n=><option key={n} value={n}>{n} слов</option>)}</select></label><p className="muted">Повторение уже изученных слов не расходует эту цель. Новые слова открываются постепенно.</p><h3>Резервная копия словаря</h3><p>Прогресс хранится на этом устройстве. Сохраните копию перед переустановкой или очисткой данных.</p><div className="actions"><button className="secondary" disabled={busy} onClick={()=>void backup()}><Download size={17}/> Сохранить копию</button><button className="secondary" disabled={busy} onClick={()=>file.current?.click()}><Upload size={17}/> Восстановить</button><input ref={file} type="file" accept="application/json,.json" hidden onChange={e=>void restore(e.target.files?.[0])}/></div><small>Копия содержит только обучение по готовым 1000 словам. Личные карточки и старые уроки в неё не входят.</small>{message&&<p className="feedback" role="status">{message}</p>}</section>
  if(view==='stats')return <section className="surface vocab-stat-section"><span className="eyebrow">СЛОВАРНЫЙ ЗАПАС</span><h2>От знакомства к памяти</h2><div className="vocab-stat-grid"><div><b>{count.started}</b><span>начато из 1000</span></div><div><b>{count.known}</b><span>закреплено</span></div><div><b>{count.due}</b><span>пора повторить</span></div></div><div className="vocab-progress"><i style={{width:`${count.known/10}%`}}/></div><p className="muted">«Закреплено» — не меньше трёх успешных повторений с интервалами. Это показатель практики, а не гарантия знания слова.</p><div className="vocab-week">{Array.from({length:7},(_,i)=>{const d=new Date();d.setDate(d.getDate()-6+i);const n=state.activity[localDay(d.getTime())]?.answers??0;return <div key={i}><b>{n}</b><i style={{height:`${Math.max(3,Math.min(70,n*3))}px`}}/><span>{d.toLocaleDateString('ru',{weekday:'short'})}</span></div>})}</div><small>Количество ответов за последние 7 дней</small></section>
  return <div className="vocabulary page-entrance">
    {view==='home'?<>
      <div className="vocab-heading"><span className="eyebrow">АЗ-АЗДАН — КӨП БОЛОТ · ПОНЕМНОГУ — ПОЛУЧИТСЯ МНОГО</span><h1>Слова, которые<br/>станут <em>твоими.</em></h1><p>Сначала узнаём. Затем пробуем вспомнить.<br className="desktop-break"/> Возвращаемся, пока не станет легче.</p></div>
      <section className="vocab-today"><div className="vocab-today-copy"><span className="vocab-tag"><Sparkles size={15}/> ТВОЁ ЗАНЯТИЕ</span><h2>{resume?'Продолжим с того же слова?':count.today.introduced>=state.dailyNew?'Хороший темп. Продолжим?':'Немного слов. Каждый день.'}</h2><p>{resume?`Шаг ${s!.cursor+1} из ${s!.tasks.length}. Всё пройденное уже сохранено.`:next?`${next.newCount} новых слов · ${next.reviewCount} на повторение`:'План выполнен. Можно взять ещё слова или вернуться позже.'}</p><button className="vocab-start" disabled={busy} onClick={()=>resume?setActive(true):void start(next?'daily':'extra')}>{resume?'Продолжить занятие':next?'Начать занятие':'Ещё немного новых слов'} <ArrowRight size={20}/></button><small><Check size={14}/> Без интернета · в своём темпе</small></div><div className="vocab-stack" aria-hidden="true"><div/><div/><div><span>БҮГҮН</span><b>үйрөнүү</b><p>учить, осваивать</p><span className="vocab-stack-line"/><small>Одно слово ближе.</small></div></div></section>
      <div className="vocab-stat-grid vocab-home-stats"><div><BookOpen size={19}/><b>{count.started}<small> / 1000</small></b><span>слов в обучении</span></div><div><RotateCcw size={19}/><b>{count.due}</b><span>ждут повторения</span></div><div><CheckCheck size={19}/><b>{count.known}</b><span>уже закреплено</span></div></div>
      <section className="surface vocab-route"><div><span className="eyebrow">УЧИ ТО, ЧТО ПРИГОДИТСЯ</span><h2>Твоя тема</h2></div><label className="vocab-topic-select"><span className="sr-only">Тема новых слов</span><select value={state.topic} disabled={busy} onChange={e=>void write({...state,topic:e.target.value,settingsAt:Date.now()})}><option value="">Полезное сначала — мой маршрут</option>{topics.map(t=><option key={t}>{t}</option>)}</select></label><p>Начинаем с глаголов и повседневных действий. Выбранная тема меняет новые слова; повторение охватывает весь изученный словарь.</p></section>
      <button className="vocab-review-link" disabled={!count.due||busy} onClick={()=>void start('review')}><span className="vocab-emblem"><RotateCcw size={22}/></span><span><b>Только повторение</b><small>{count.due?`${plural(count.due)} на повторение`:'Пока всё свежее в памяти'}</small></span><ArrowRight size={20}/></button>
      <div className="vocab-how"><span>01 <b>Узнай слово</b></span><ChevronRight size={14}/><span>02 <b>Узнай перевод</b></span><ChevronRight size={14}/><span>03 <b>Вспомни сам</b></span></div>
    </>:<>
      <div className="vocab-heading compact"><span className="eyebrow">ТВОЯ ТЫСЯЧА СЛОВ</span><h1>Понятнее с каждым словом.</h1><p>25 тем · слова и полезные выражения · без ручного импорта</p></div>
      <div className="vocab-tools"><label className="vocab-search"><Search size={19}/><input value={search} onChange={e=>setSearch(e.target.value)} placeholder="Кыргызча или по-русски" aria-label="Поиск по 1000 словам"/></label><select value={topic} onChange={e=>setTopic(e.target.value)} aria-label="Тема словаря"><option value="">Все 25 тем</option>{topics.map(t=><option key={t}>{t}</option>)}</select><select value={filter} onChange={e=>setFilter(e.target.value)} aria-label="Статус слова"><option value="all">Все статусы</option>{Object.entries(labels).map(([id,label])=><option key={id} value={id}>{label}</option>)}</select></div>
      <div className="vocab-list-heading"><b>{filtered.length} записей</b><span>Нажми на слово, чтобы разобрать его</span></div><div className="vocab-list">{filtered.slice(0,100).map(w=><button className="vocab-list-row" key={w.id} onClick={()=>setSelected(w)}><span className="vocab-word-number">{String(w.id).padStart(3,'0')}</span><span><b lang="ky">{w.kg}</b><small>{w.ru}</small></span><span className={`vocab-status ${status(state.cards[w.id],now)}`}>{labels[status(state.cards[w.id],now)]}</span><ChevronRight size={16}/></button>)}</div>{filtered.length>100&&<p className="vocab-note">Показаны первые 100 из {filtered.length}. Выбери тему или введи слово в поиске.</p>}{!filtered.length&&<div className="surface empty"><Search size={30}/><h2>Здесь пока пусто</h2><p>Попробуй другой поиск или статус.</p><button className="secondary" onClick={()=>{setSearch('');setTopic('');setFilter('all')}}>Сбросить фильтры</button></div>}
    </>}
    {message&&<p className="notice" role="status">{message}</p>}
    {selected&&<WordDialog word={selected} card={state.cards[selected.id]} close={()=>setSelected(undefined)}/>}
  </div>
}
function WordDialog({word,card,close}:{word:Entry;card:VocabState['cards'][string]|undefined;close:()=>void}) {
  const ref=useRef<HTMLDialogElement>(null)
  useEffect(()=>{const previous=document.activeElement as HTMLElement|null;ref.current?.showModal();return()=>{previous?.focus()}},[])
  return <dialog ref={ref} className="vocab-dialog" aria-labelledby="word-dialog-title" onCancel={close} onClick={e=>{if(e.target===e.currentTarget)close()}}><button className="icon-button vocab-dialog-close" onClick={close} aria-label="Закрыть слово"><X size={21}/></button><span className="eyebrow">{word.topic}</span><div className="vocab-word-heading"><h2 id="word-dialog-title" lang="ky">{word.kg}</h2><Sound word={word}/></div><p className="vocab-translation">{word.ru}</p><Example word={word} expanded/>{card?<p className="vocab-note">Следующее повторение: {formatDate(card.due)}</p>:<p className="vocab-note">Это слово ещё не было в занятиях. Просмотр карточки не отмечает его изученным.</p>}</dialog>
}
function StudyStep({word,mode,seed,forgiving,busy,next}:{word:Entry;mode:'discover'|'choice'|'recall';seed:number;forgiving:boolean;busy:boolean;next:(rating:Rating)=>Promise<boolean>}) {
  const [input,setInput]=useState(''),[answer,setAnswer]=useState<{correct:boolean;helped:boolean}>(),[hint,setHint]=useState(false)
  const inputRef=useRef<HTMLInputElement>(null)
  const locked=useRef(false)
  function check(value:string) {if(answer||locked.current||busy)return;setInput(value);setAnswer({correct:mode==='choice'?value===word.ru:matches(value,word.kg,forgiving),helped:hint})}
  async function proceed(rating:Rating) {if(locked.current)return;locked.current=true;try {await next(rating)}finally{locked.current=false}}
  const correct=answer?.correct&&!answer.helped
  return <section className="vocab-study surface"><span className="vocab-topic">{word.topic}</span><h1>{mode==='discover'?'Познакомься со словом':mode==='choice'?'Узнаёшь значение?':'Как это по-кыргызски?'}</h1><p className="vocab-study-instruction">{mode==='discover'?'Здесь не нужно угадывать. Прочитай слово и перевод.':mode==='choice'?'Выбери перевод слова, которое только что видел.':'Попробуй вспомнить. Если не знаешь — открой подсказку.'}</p>
    <div className="vocab-study-face"><span className="eyebrow">{mode==='recall'?'ПО-РУССКИ':'КЫРГЫЗЧА'}</span><div className="vocab-word-heading"><h2 lang={mode==='recall'?'ru':'ky'}>{mode==='recall'?word.ru:word.kg}</h2>{mode!=='recall'&&<Sound word={word}/>}</div>{mode==='discover'&&<p className="vocab-translation">{word.ru}</p>}</div>
    {mode==='discover'?<><Example word={word}/><button className="primary vocab-next" disabled={busy} onClick={()=>void proceed('good')}>Прочитал, дальше <ArrowRight size={19}/></button></>:
      <>{mode==='choice'?<div className="vocab-options">{choices(word,seed).map((option,i)=><button key={option} disabled={!!answer||busy} className={answer?(option===word.ru?'correct':option===input?'incorrect':''):''} onClick={()=>check(option)}><span>{i+1}</span>{option}</button>)}</div>:
      <form onSubmit={e=>{e.preventDefault();if(input.trim())check(input)}}><label className="sr-only" htmlFor="vocab-answer">Ответ на кыргызском</label><input id="vocab-answer" className="vocab-answer" ref={inputRef} value={input} readOnly={!!answer} disabled={busy} lang="ky" autoComplete="off" autoCapitalize="none" autoCorrect="off" spellCheck={false} placeholder="Напиши слово…" onChange={e=>setInput(e.target.value)}/><div className="vocab-keyboard">{['ң','ө','ү'].map(letter=><button type="button" key={letter} disabled={!!answer||busy} aria-label={'Вставить '+letter} onClick={()=>{const el=inputRef.current,start=el?.selectionStart??input.length,end=el?.selectionEnd??start;setInput(input.slice(0,start)+letter+input.slice(end));requestAnimationFrame(()=>{el?.focus();el?.setSelectionRange(start+1,start+1)})}}>{letter}</button>)}</div>{!answer&&<div className="vocab-recall-actions"><button type="button" className="secondary" onClick={()=>setHint(true)}><Eye size={17}/> Не помню</button><button className="primary" disabled={!input.trim()||busy}>Проверить <Check size={18}/></button></div>}</form>}
      {hint&&!answer&&<div className="vocab-hint" role="status"><span>ПОДСКАЗКА</span><b lang="ky">{word.kg}</b><small>Ответ с подсказкой вернётся на повторение раньше.</small><button className="secondary" disabled={busy} onClick={()=>{setInput(word.kg);setAnswer({correct:true,helped:true})}}>Повторить это слово позже <ArrowRight size={17}/></button></div>}
      {answer&&<div className={`vocab-feedback ${correct?'success':'retry'}`} role="status"><span>{correct?<CheckCheck size={21}/>:<RotateCcw size={21}/>}</span><div><b>{correct?'Получилось!':answer.helped?'Закрепим ещё раз.':'Ничего, сейчас запомним.'}</b><p><strong lang="ky">{word.kg}</strong> — {word.ru}</p></div></div>}
      {answer&&<><Example word={word}/><div className="vocab-rating">{correct?<><button className="secondary" disabled={busy} onClick={()=>void proceed('hard')}>С трудом <small>раньше повторить</small></button><button className="primary" disabled={busy} onClick={()=>void proceed('good')}>Вспомнил <ArrowRight size={18}/></button></>:<button className="primary" disabled={busy} onClick={()=>void proceed('again')}>Продолжить <ArrowRight size={18}/></button>}</div></>}
    </>}
  </section>
}
