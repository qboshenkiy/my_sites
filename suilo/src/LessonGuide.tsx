import { useState } from 'react'
import { BookOpen, Check, ChevronDown } from 'lucide-react'
import type { LessonGuide } from './lessonGuides'

export function GuideCard({guide}: {guide: LessonGuide}) {
  return <div className="guide-content">
    <p>{guide.rule}</p>
    <dl className="guide-examples">
      {guide.examples.map(([phrase, translation])=><div key={phrase}><dt lang="ky">{phrase}</dt><dd>{translation}</dd></div>)}
    </dl>
  </div>
}

export function LessonWarmup({guide}: {guide: LessonGuide}) {
  const [chosen, setChosen] = useState('')
  const {warmup} = guide
  return <>
    <section className="guide-card">
      <span className="eyebrow"><BookOpen size={16}/> ШАГ 1 · РАЗБОР</span>
      <h2>{guide.title}</h2>
      <GuideCard guide={guide}/>
    </section>
    <section className="warmup">
      <span className="eyebrow">ШАГ 2 · РАЗМИНКА БЕЗ ОЦЕНКИ</span>
      <h2>{warmup.prompt}</h2>
      <div className="options">{warmup.options.map(option=><button key={option} type="button" aria-pressed={chosen===option} className={chosen===option?'picked':''} onClick={()=>setChosen(option)} lang="ky">{option}</button>)}</div>
      {chosen && <div className={'feedback '+(chosen===warmup.correct?'correct':'wrong')} role="status">
        <strong>{chosen===warmup.correct?<><Check size={17}/> Верно</>:'Попробуйте ещё раз'}</strong>
        <p>{warmup.explanation}</p>
      </div>}
    </section>
  </>
}

export function GuideHint({guide, expanded}: {guide: LessonGuide; expanded: boolean}) {
  return <details className="guide-hint" open={expanded || undefined}>
    <summary><BookOpen size={18}/> Правило и примеры <ChevronDown size={16}/></summary>
    <GuideCard guide={guide}/>
  </details>
}
