import { useState } from 'react'
import { ArrowRight, Lightbulb, MessagesSquare, RotateCcw } from 'lucide-react'
import { TextAnswer } from './Exercise'
import { accepts, normalize } from './progress'

type Turn = {ask:string; hint:string; example:string; pattern:RegExp; correction?:[RegExp,string]}
const scenes:{title:string; turns:Turn[]}[] = [
  {title:'Знакомство',turns:[
    {ask:'Салам! Атың ким?',hint:'Назовите своё имя: «Менин атым …»',example:'Менин атым Айжан.',pattern:/^(менин )?атым [а-яңөү]+$/u,correction:[/^менин атың /,'Для своего имени используйте «атым» вместо «атың».']},
    {ask:'Кайда жашайсың?',hint:'Назовите город с окончанием места и добавьте «жашайм».',example:'Мен Ошто жашайм.',pattern:/^(мен )?[а-яңөү]+(?:да|де|до|дө|та|те|то|тө) жашайм$/u,correction:[/ жашайсың$/,'О себе скажите «жашайм». «Жашайсың» означает «ты живёшь».']},
  ]},
  {title:'Встреча с другом',turns:[
    {ask:'Кандайсың?',hint:'Скажите, как вы себя чувствуете.',example:'Мен жакшымын, рахмат.',pattern:/^(мен )?(жакшымын|жакшы|жаман эмесмин|жаман эмес)( рахмат)?$/u},
    {ask:'Бүгүн эмне кыласың?',hint:'Расскажите, что будете делать. Попробуйте «бүгүн … окуйм» или «… барам».',example:'Бүгүн китеп окуйм.',pattern:/^(мен )?(бүгүн )?[а-яңөү]+ (окуйм|барам|иштейм|болом)$/u},
  ]},
  {title:'В кафе',turns:[
    {ask:'Эмне ичесиз?',hint:'Назовите напиток и попросите его через «бериңизчи».',example:'Бир чыны чай бериңизчи.',pattern:/^(бир (чыны|стакан) )?(чай|суу|кофе|шире|айран) бериңизчи$/u},
    {ask:'Дагы эмне аласыз?',hint:'Выберите блюдо или скажите, что больше ничего не хотите.',example:'Салат бериңизчи.',pattern:/^((салат|шорпо|нан|манты|палоо) бериңизчи|жок рахмат)$/u},
  ]},
  {title:'В магазине',turns:[
    {ask:'Саламатсызбы! Эмне аласыз?',hint:'Скажите, что возьмёте. Используйте «алам».',example:'Мен нан алам.',pattern:/^(мен )?(нан|сүт|чай|суу|алма|эт) алам$/u},
    {ask:'Дагы сурооңуз барбы?',hint:'Уточните цену товара.',example:'Бул канча турат?',pattern:/^(бул|нан|сүт|чай|суу|алма|эт) канча турат$/u},
  ]},
  {title:'О работе',turns:[
    {ask:'Кайда иштейсиз?',hint:'Назовите место работы и добавьте «иштейм».',example:'Мен мектепте иштейм.',pattern:/^(мен )?[а-яңөү]+(?:да|де|до|дө|та|те|то|тө) иштейм$/u,correction:[/ иштейсиз$/,'«Иштейсиз» — «вы работаете». Для ответа от своего лица нужно «иштейм».']},
    {ask:'Эмне менен алектенесиз?',hint:'Расскажите об интересе: «… кызыгам».',example:'Музыкага кызыгам.',pattern:/^(мен )?[а-яңөү]+(?:га|ге|го|гө|ка|ке|ко|кө) кызыгам$/u},
  ]},
  {title:'Планы',turns:[
    {ask:'Эртең кайда баргың келет?',hint:'Назовите место в дательном падеже и добавьте «баргым келет».',example:'Эртең тоого баргым келет.',pattern:/^(мен )?(эртең )?[а-яңөү]+(?:га|ге|го|гө|ка|ке|ко|кө) баргым келет$/u,correction:[/ баргың келет$/,'«Баргың» — твоё желание. О себе скажите «баргым келет».']},
    {ask:'Эмне үчүн?',hint:'Начните объяснение с «анткени». Добавьте отдельную фразу с причиной.',example:'Анткени тоодо аба таза.',pattern:/^анткени [а-яңөү]+ [а-яңөү]+(?: [а-яңөү]+)+$/u},
  ]},
]
export function Conversation({level, reviewWord}:{level:string; reviewWord?:string}) {
  const [scene,setScene]=useState(0)
  const [step,setStep]=useState(0)
  const [answer,setAnswer]=useState('')
  const [history,setHistory]=useState<{ask:string;answer:string}[]>([])
  const [feedback,setFeedback]=useState('')
  const [hint,setHint]=useState(false)
  const [attempted,setAttempted]=useState(false)
  const s=scenes[scene]
  const turn=s.turns[step]
  function advance() {
    setHistory([...history,{ask:turn.ask,answer:answer.trim()}])
    setStep(step+1);setAnswer('');setHint(false);setFeedback('');setAttempted(false)
  }
  function check(e:React.FormEvent) {
    e.preventDefault()
    const input=normalize(answer)
    const correction=turn.correction
    if (correction?.[0].test(input)) {
      setAttempted(false);setFeedback(correction[1]);return
    }
    if (accepts(answer,[turn.example]) || turn.pattern.test(input)) {
      setAttempted(true);setFeedback('Основная конструкция подходит. Сверьте слова и смысл, затем продолжайте.');return
    }
    setAttempted(true);setFeedback('Эту формулировку тренажёр не смог проверить. Можно сравнить с примером или продолжить со своим ответом.')
  }
  function reset(i:number) {setScene(i);setStep(0);setAnswer('');setHistory([]);setFeedback('');setHint(false);setAttempted(false)}
  return <div className="page-entrance">
    <div className="page-heading"><span className="eyebrow">РАЗГОВОРНАЯ ПРАКТИКА</span><h1>Сүйлөшөлү</h1><p>Отвечайте своими словами. Тренажёр проверяет знакомые конструкции.</p></div>
    <div className="tokens scene-tabs">{scenes.map((item,i)=><button key={item.title} className={i===scene?'picked':''} onClick={()=>reset(i)}>{item.title}</button>)}</div>
    <div className="surface conversation">
      <h2><MessagesSquare size={23}/> {s.title}</h2>
      {reviewWord && <p className="muted">Если подходит по смыслу, попробуйте вспомнить слово «{reviewWord}».</p>}
      {history.map((entry,i)=><div className="conversation-turn" key={i}><p className="bubble" lang="ky">{entry.ask}</p><p className="bubble mine" lang="ky">{entry.answer}</p></div>)}
      {turn ? <>
        <p className="bubble" lang="ky">{turn.ask}</p>
        <form onSubmit={check}>
          <TextAnswer value={answer} change={value=>{setAnswer(value);setAttempted(false);setFeedback('')}} label="Ваш ответ по-кыргызски"/>
          {hint && <div className="feedback"><small>{level==='A0'||level==='A1' ? turn.hint : 'Сравните структуру с примером.'}</small><p lang="ky">{turn.example}</p></div>}
          {feedback && <p role="status" className="feedback">{feedback}</p>}
          <div className="actions">
            {attempted ? <button type="button" className="primary" onClick={advance}>Продолжить <ArrowRight size={18}/></button> : <button className="primary" disabled={!answer.trim()} type="submit">Проверить <ArrowRight size={18}/></button>}
            <button type="button" className="secondary" onClick={()=>setHint(!hint)}><Lightbulb size={18}/> {hint?'Скрыть подсказку':'Подсказка'}</button>
          </div>
        </form>
      </> : <><p className="feedback correct">Азаматсыз! Диалог завершён.</p><button type="button" className="secondary" onClick={()=>reset(scene)}><RotateCcw size={17}/> Повторить диалог</button></>}
    </div>
  </div>
}
