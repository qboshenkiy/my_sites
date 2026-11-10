import { useState } from 'react'
import { ArrowRight, BookOpen, Pencil, Plus, Trash2 } from 'lucide-react'
import { normalize, parsePersonalWords, type PersonalWord } from './progress'

type Pair = Pick<PersonalWord,'ru'|'ky'>
const pairKey = ({ru,ky}:Pair) => JSON.stringify([normalize(ru),ky.split(' / ').map(v=>normalize(v)).sort()])
const maxWords = 500

export function PersonalWords({words, add, edit, remove, study, train}: {
  words:PersonalWord[]
  add:(pairs:Pair[])=>Promise<void>
  edit:(id:string,pair:Pair)=>Promise<void>
  remove:(id:string)=>Promise<void>
  study:()=>void
  train:()=>void
}) {
  const [input,setInput]=useState('')
  const [message,setMessage]=useState('')
  const [editing,setEditing]=useState<PersonalWord>()
  const [confirm,setConfirm]=useState<string>()
  const [busy,setBusy]=useState(false)

  async function submit(e:React.FormEvent) {
    e.preventDefault()
    if (busy) return
    const {words:parsed,invalid}=parsePersonalWords(input)
    if (invalid.length) return setMessage('Проверьте строки '+invalid.join(', ')+'. В каждой нужны русское слово и кыргызский перевод.')
    const known=new Map(words.map(word=>[normalize(word.ru),pairKey(word)]))
    const unique: Pair[] = []
    for (const pair of parsed) {
      const prompt=normalize(pair.ru)
      const key=pairKey(pair)
      const previous=known.get(prompt)
      if (previous===key) continue
      if (previous) return setMessage('Для «'+pair.ru+'» уже есть перевод. Объедините варианты через «/» в одной карточке.')
      known.set(prompt,key)
      unique.push(pair)
    }
    if (!unique.length) return setMessage(parsed.length?'Такие карточки уже есть.':'Вставьте хотя бы одну пару слов.')
    if (words.length+unique.length>maxWords) return setMessage('Можно сохранить до 500 личных карточек.')
    setBusy(true)
    try {
      await add(unique)
      setInput('')
      setMessage('Добавлено карточек: '+unique.length+(parsed.length>unique.length?'. Повторы пропущены.':'.'))
    } finally {setBusy(false)}
  }

  async function saveEdit(e:React.FormEvent) {
    e.preventDefault()
    if (!editing || busy) return
    const ru=editing.ru.trim()
    const variants=editing.ky.split('/').map(v=>v.trim())
    if (!normalize(ru) || variants.some(v=>!normalize(v))) return setMessage('Укажите слово и хотя бы один перевод.')
    const pair={ru,ky:variants.join(' / ')}
    if (words.some(word=>word.id!==editing.id && normalize(word.ru)===normalize(ru))) return setMessage('Такая карточка уже есть.')
    setBusy(true)
    try {await edit(editing.id,pair);setEditing(undefined);setMessage('Карточка обновлена.')}
    finally {setBusy(false)}
  }

  return <section className="surface personal-words">
    <header className="personal-heading"><div><span className="eyebrow">СЛОВА ДЛЯ СВОЕЙ ПРАКТИКИ</span><h2>Мои карточки</h2><p>Русское слово появится на экране. Введите его перевод на кыргызском.</p></div>
      {words.length>0&&<div className="actions personal-study-actions">
        <button className="primary" disabled={busy} onClick={study}><BookOpen size={17}/> Разучивать слова</button>
        <button className="secondary" disabled={busy} onClick={train}>Тренировать свои слова <ArrowRight size={17}/></button>
      </div>}
    </header>
    <form className="personal-form" onSubmit={submit}>
      <label htmlFor="word-pairs">Вставьте пары «русский — кыргызский»</label>
      <textarea id="word-pairs" rows={3} value={input} maxLength={20000} spellCheck={false} placeholder={'книга — китеп\nдруг — дос'} onChange={e=>setInput(e.target.value)} aria-describedby="word-pairs-help"/>
      <small id="word-pairs-help">Одна пара на строку. Можно вставить два столбца из таблицы. Варианты перевода разделяйте через «/».</small>
      <button className="secondary" type="submit" disabled={busy||!input.trim()}><Plus size={17}/> Добавить слова</button>
    </form>
    {message&&<p className="feedback" role="status">{message}</p>}
    {words.length>0&&<details className="personal-list">
      <summary>Список карточек · {words.length}</summary>
      <ul>{words.map(word=><li key={word.id}>
        {editing?.id===word.id ? <form onSubmit={saveEdit} className="personal-form">
          <label>Русское слово<input value={editing.ru} maxLength={160} onChange={e=>setEditing({...editing,ru:e.target.value})}/></label>
          <label>Кыргызский перевод<input value={editing.ky} maxLength={160} onChange={e=>setEditing({...editing,ky:e.target.value})}/></label>
          <div className="actions"><button className="primary" disabled={busy}>Сохранить</button><button className="secondary" type="button" onClick={()=>setEditing(undefined)}>Отмена</button></div>
        </form> : <>
          <div><strong>{word.ru}</strong><p lang="ky">{word.ky}</p></div>
          <div className="personal-controls">
            {confirm===word.id ? <><button className="secondary" disabled={busy} onClick={async ()=>{setBusy(true);try {await remove(word.id);setConfirm(undefined);setMessage('Карточка удалена.')} finally {setBusy(false)}}}>Удалить карточку</button><button className="secondary" onClick={()=>setConfirm(undefined)}>Отмена</button></> : <>
              <button className="icon-button" aria-label={'Изменить '+word.ru} onClick={()=>{setMessage('');setEditing(word)}}><Pencil size={16}/></button>
              <button className="icon-button" aria-label={'Удалить '+word.ru} onClick={()=>setConfirm(word.id)}><Trash2 size={16}/></button>
            </>}
          </div>
        </>}
      </li>)}</ul>
    </details>}
  </section>
}
