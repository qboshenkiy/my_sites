import { useEffect, useState } from 'react'
import { ArrowLeft, ArrowRight, Eye, EyeOff } from 'lucide-react'
import type { Word } from './course'

export function StudyCards({words, exit, check}: {words:Word[]; exit:()=>void; check:()=>void}) {
  const [index,setIndex]=useState(0)
  const [revealed,setRevealed]=useState(false)
  const word=words[index]
  const last=index===words.length-1

  useEffect(()=>{window.scrollTo(0,0)},[])

  function move(next:number) {
    setIndex(next)
    setRevealed(false)
  }

  return <section className="surface study-cards page-entrance">
    <button className="secondary" onClick={exit}><ArrowLeft size={17}/> К моим словам</button>
    <header>
      <span className="eyebrow">МОИ КАРТОЧКИ</span>
      <h1>Разучивание слов</h1>
      <p className="muted">Попробуйте вспомнить перевод, затем откройте карточку.</p>
    </header>
    <div className="study-counter">Карточка {index+1} из {words.length}</div>
    <div className="meter" aria-hidden="true"><i style={{width:`${100*(index+1)/words.length}%`}}/></div>
    <div className="study-face" aria-live="polite">
      <span className="eyebrow">РУССКИЙ</span>
      <h2>{word.ru}</h2>
      <div className="study-translation" id="study-translation" hidden={!revealed}>
        <span className="eyebrow">КЫРГЫЗСКИЙ</span>
        <p lang="ky">{word.ky}</p>
      </div>
    </div>
    <button className="secondary study-reveal" aria-controls="study-translation" aria-expanded={revealed} onClick={()=>setRevealed(!revealed)}>
      {revealed?<EyeOff size={18}/>:<Eye size={18}/>} {revealed?'Скрыть перевод':'Показать перевод'}
    </button>
    <div className="study-navigation">
      <button className="secondary" disabled={index===0} onClick={()=>move(index-1)}><ArrowLeft size={17}/> Назад</button>
      {last?<button className="primary" onClick={check}>Проверить себя <ArrowRight size={17}/></button>:
        <button className="primary" onClick={()=>move(index+1)}>Следующее слово <ArrowRight size={17}/></button>}
    </div>
  </section>
}
