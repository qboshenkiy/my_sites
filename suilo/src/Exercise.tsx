import { useEffect, useRef, useState } from 'react'
import { ArrowLeft, ArrowRight, Check, Mic, Volume2, X } from 'lucide-react'
import { kindLabel, type Exercise } from './course'
import { accepts } from './progress'
import { recognize, speak } from './platform'

export function TextAnswer({value, change, label='Ваш ответ', kyrgyz=true, disabled=false}: {
  value:string; change:(v:string)=>void; label?:string; kyrgyz?:boolean; disabled?:boolean
}) {
  const input=useRef<HTMLInputElement>(null)
  function add(letter:string) {
    const el=input.current
    if (!el) return
    const start=el.selectionStart ?? value.length
    const end=el.selectionEnd ?? start
    change(value.slice(0,start)+letter+value.slice(end))
    el.focus()
    requestAnimationFrame(()=>el.setSelectionRange(start+1,start+1))
  }
  return <>
    <label className="answer-label">{label}<input ref={input} autoComplete="off" autoCorrect="off" spellCheck={false} value={value} maxLength={300} disabled={disabled} onChange={e=>change(e.target.value)} /></label>
    {kyrgyz && <div className="keys" aria-label="Кыргызская клавиатура">{['ң','ө','ү'].map(letter=><button type="button" disabled={disabled} key={letter} onMouseDown={e=>e.preventDefault()} onClick={()=>add(letter)}>{letter}</button>)}</div>}
  </>
}

export function ExerciseScreen({exercise:q, index, length, title, forgiving, exit, next}:{
  exercise:Exercise; index:number; length:number; title:string; forgiving:boolean; exit:()=>void;
  next:(result:{correct:boolean;given:string;expected:string;skipped?:boolean})=>Promise<void>
}) {
  const [answer,setAnswer]=useState('')
  const [pending,setPending]=useState(false)
  async function advance(result:Parameters<typeof next>[0]) {
    if (pending) return
    setPending(true)
    try { await next(result) } finally { setPending(false) }
  }
  const [tokens,setTokens]=useState<number[]>([])
  const [pairs,setPairs]=useState<Record<number,string>>({})
  const [selected,setSelected]=useState<number>()
  const [feedback,setFeedback]=useState<boolean>()
  const [audioError,setAudioError]=useState(false)
  const [mic,setMic]=useState<'idle'|'recording'|'unavailable'>('idle')
  const stop=useRef<(()=>void)|undefined>(undefined)
  useEffect(()=>()=>stop.current?.(),[])
  const options=q.options ?? []
  const locked=feedback!==undefined
  const given=q.kind==='order' ? tokens.map(i=>options[i]).join(' ') : q.kind==='match' ? q.pairs?.map((_,i)=>pairs[i]).join(' / ') ?? '' : answer
  const expected=q.kind==='match' ? q.pairs?.map(p=>p.ky+' — '+p.ru).join(' · ') ?? '' : q.answers[0]
  const ready=q.kind==='match' ? Object.keys(pairs).length===q.pairs?.length : !!given.trim()
  const missingAudio=q.kind==='listen' && audioError
  function check(event:React.FormEvent) {
    event.preventDefault()
    if (locked) return void advance({correct:feedback,given,expected})
    if (!ready) return
    stop.current?.()
    setFeedback(q.kind==='match'
      ? !!q.pairs?.every((word,i)=>pairs[i]===word.ru)
      : accepts(given,q.answers,forgiving && q.kind!=='ky-ru' && q.kind!=='speak'))
  }
  function microphone() {
    stop.current?.()
    setMic('recording')
    stop.current=recognize(value=>{setAnswer(value);setMic('idle')},()=>setMic('unavailable'))
  }
  return <section className="exercise page-entrance">
    <div className="exercise-top"><button className="icon-button" type="button" aria-label="Выйти из урока" onClick={exit}><ArrowLeft size={21}/></button><div><small>{title}</small><div className="meter"><i style={{width:`${100*index/length}%`}}/></div></div><b>{index+1}/{length}</b></div>
    <form onSubmit={check} className="surface question">
      <span className="eyebrow">ЗАДАНИЕ {String(index+1).padStart(2,'0')}</span>
      <h1>{missingAudio ? 'Прочитайте фразу' : kindLabel[q.kind]}</h1>
      <p className="prompt" lang={['ky-ru','speak','gap','dialog'].includes(q.kind)?'ky':undefined}>{missingAudio ? q.audio : q.prompt}</p>
      {q.kind==='listen' && <><button className="secondary" disabled={locked} type="button" onClick={()=>{setAudioError(false);speak(q.audio!,()=>setAudioError(true))}}><Volume2 size={19}/> Прослушать</button>{audioError&&<p className="muted" role="status">Аудио недоступно. Выберите фразу по тексту.</p>}</>}
      {q.kind==='speak' && <div className="actions"><button className="secondary" type="button" disabled={locked || mic==='recording'} onClick={microphone}><Mic size={18}/> {mic==='recording'?'Слушаю…':'Включить микрофон'}</button>
        <button className="secondary" type="button" onClick={()=>speak(q.prompt,()=>setAudioError(true))}><Volume2 size={18}/> Послушать</button>
        {audioError&&<small>Кыргызская озвучка недоступна на этом устройстве.</small>}
        {mic==='unavailable'&&<small role="status">Распознавание недоступно. Можно произнести фразу и записать её вручную.</small>}
      </div>}
      {q.kind==='match' && <div className="match">
        <div>{q.pairs?.map((word,i)=><button type="button" key={word.ky} disabled={locked} className={selected===i?'picked':''} onClick={()=>setSelected(i)}>{word.ky}{pairs[i]&&<small>{pairs[i]}</small>}</button>)}</div>
        <div>{q.pairs?.map(w=>w.ru).reverse().map(ru=><button type="button" key={ru} disabled={locked || selected===undefined} onClick={()=>{
          if (selected===undefined) return
          const updated={...pairs}
          for (const id of Object.keys(updated)) if (updated[Number(id)]===ru) delete updated[Number(id)]
          updated[selected]=ru
          setPairs(updated);setSelected(undefined)
        }}>{ru}</button>)}</div>
      </div>}
      {q.kind==='order' && <><div className="token-tray" aria-label="Ваше предложение">{tokens.map((i,j)=><button key={i} type="button" disabled={locked} onClick={()=>setTokens(tokens.filter((_,k)=>k!==j))}>{options[i]}</button>)}</div><div className="tokens">{options.map((token,i)=><button key={i} type="button" disabled={locked || tokens.includes(i)} onClick={()=>setTokens([...tokens,i])}>{token}</button>)}</div></>}
      {options.length>0 && q.kind!=='order' && <div className="options">{options.map((option,i)=><button type="button" key={option} disabled={locked} aria-pressed={answer===option} className={answer===option?'picked':''} onClick={()=>setAnswer(option)}><span>{i+1}</span>{option}</button>)}</div>}
      {options.length===0 && q.kind!=='match' && <TextAnswer value={answer} change={setAnswer} kyrgyz={q.kind!=='ky-ru'} disabled={locked} label={q.kind==='speak'?'Распознанный текст или ручной ввод':'Ваш ответ'}/>}
      {locked && <div className={feedback?'feedback correct':'feedback wrong'} role="status"><strong>{feedback?<Check size={18}/>:<X size={18}/>} {feedback?'Туура! Верно.':'Правильный вариант'}</strong>{!feedback && <p>{expected}</p>}<small>{q.why}</small></div>}
      <div className="actions">
        <button className="primary" disabled={pending||(!locked&&!ready)} type="submit">{locked?'Дальше':'Проверить'} <ArrowRight size={19}/></button>
        {q.kind==='speak' && !locked && <button type="button" className="secondary" disabled={pending} onClick={()=>void advance({correct:false,given:'',expected,skipped:true})}>Пропустить микрофон</button>}
      </div>
    </form>
  </section>
}
