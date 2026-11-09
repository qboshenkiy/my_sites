import { useEffect, useRef, useState } from 'react'
import { createRoot } from 'react-dom/client'
import { ArrowDownToLine, ArrowLeft, ArrowRight, BookOpen, ChartNoAxesColumnIncreasing, Check, ChevronRight, Compass, Flame, Flag, GraduationCap, LockKeyhole, MessagesSquare, Mountain, Search, Settings2, Sparkles, Star, Target, Trophy, Volume2, Zap } from 'lucide-react'
import { allWords, levels, type Exercise, type Word } from './course'
import { addWords, daily, day, fresh, load, mergeProgress, persist, review, schedule, streak, total, type Progress } from './progress'
import { connectTelegram, isNative, speak, type InstallEvent } from './platform'
import { ExerciseScreen, type ExerciseResult } from './Exercise'
import { LessonWarmup } from './LessonGuide'
import { lessonGuides } from './lessonGuides'
import { Conversation } from './Conversation'
import { Mascot } from './Mascot'
import { cloud, synchronize } from './cloud'
import './style.css'

const navigation = [
  {id:'map',title:'Путь',icon:Compass},
  {id:'words',title:'Мои слова',icon:BookOpen},
  {id:'talk',title:'Диалоги',icon:MessagesSquare},
  {id:'stats',title:'Прогресс',icon:ChartNoAxesColumnIncreasing},
  {id:'settings',title:'Настройки',icon:Settings2},
] as const
type Page = typeof navigation[number]['id'] | 'install'
type Lesson = typeof levels[number]['lessons'][number]
const slug = (path: string):Page => navigation.find(item=>item.id===path)?.id ?? (path==='install'?'install':'map')
function App() {
  const [p,setP]=useState<Progress>(fresh)
  const pRef=useRef(p)
  const queue=useRef(Promise.resolve())
  const [ready,setReady]=useState(false)
  const [storageError,setStorageError]=useState('')
  const [page,setPage]=useState<Page>(()=>slug(new URLSearchParams(location.search).get('page')??''))
  const [lesson,setLesson]=useState<Lesson>()
  const [running,setRunning]=useState(false)
  const [result,setResult]=useState<{title:string;xp:number;mistakes:number;review?:boolean}>()
  const [install,setInstall]=useState<InstallEvent>()
  const [practice,setPractice]=useState<{words:Word[];index:number;mistakes:number}>()
  const [search,setSearch]=useState('')
  const [topic,setTopic]=useState('')
  const [filter,setFilter]=useState('all')
  const [wordError,setWordError]=useState('')
  const [online,setOnline]=useState(navigator.onLine)
  const [email,setEmail]=useState('')
  const [syncMessage,setSyncMessage]=useState('')
  const [syncing,setSyncing]=useState(false)
  const [cloudUser,setCloudUser]=useState('')
  useEffect(()=>{
    load().then(saved=>{pRef.current=saved;setP(saved)}).catch(()=>setStorageError('Хранилище недоступно. Прогресс сохранится только до закрытия.')).finally(()=>setReady(true))
    const handleInstall=(e:Event)=>{e.preventDefault();setInstall(e as InstallEvent)}
    const installed=()=>setInstall(undefined)
    const connectivity=()=>setOnline(navigator.onLine)
    const onPop=()=>{setPage(slug(new URLSearchParams(location.search).get('page')??''));setLesson(undefined);setRunning(false);setPractice(undefined);setResult(undefined)}
    window.addEventListener('beforeinstallprompt',handleInstall)
    window.addEventListener('appinstalled',installed)
    window.addEventListener('online',connectivity);window.addEventListener('offline',connectivity);window.addEventListener('popstate',onPop)
    connectTelegram()
    const sub=cloud?.auth.onAuthStateChange((_,session)=>setCloudUser(session?.user.email??''))
    return ()=>{window.removeEventListener('beforeinstallprompt',handleInstall);window.removeEventListener('appinstalled',installed);window.removeEventListener('online',connectivity);window.removeEventListener('offline',connectivity);window.removeEventListener('popstate',onPop);sub?.data.subscription.unsubscribe()}
  },[])
  useEffect(()=>{document.documentElement.dataset.theme=p.theme},[p.theme])
  const save=(next:Progress, afterWrite=false)=>{
    pRef.current=next
    if (!afterWrite) setP(next)
    queue.current=queue.current.catch(()=>{}).then(()=>persist(next)).then(()=>setStorageError('')).catch(()=>setStorageError('Не удалось сохранить прогресс на устройстве.'))
    return queue.current.then(()=>{if (afterWrite && pRef.current===next) setP(next)})
  }
  const go=(next:Page)=>{
    setPage(next);setLesson(undefined);setRunning(false);setResult(undefined);setPractice(undefined)
    const url=new URL(location.href)
    if (next==='map') url.searchParams.delete('page'); else url.searchParams.set('page',next)
    if (url.href!==location.href) history.pushState(null,'',url)
    window.scrollTo(0,0)
  }
  const level=levels.find(item=>item.id===p.level)??levels[0]
  const completedCount=level.lessons.filter(item=>p.completed[item.id]).length
  const nextLesson=level.lessons.find(item=>!p.completed[item.id])
  const currentDay=daily(p)
  const currentStreak=streak(p.activity)
  const learned=allWords.filter(word=>p.cards[word.ky])
  const due=learned.filter(word=>p.cards[word.ky].due<=Date.now()).sort((a,b)=>p.cards[a.ky].due-p.cards[b.ky].due)
  const weak=due.find(word=>p.cards[word.ky].box===0)
  const achievements=[
    {title:'Первый шаг',copy:'Завершите первый урок',active:Object.keys(p.completed).length>0,icon:Flag},
    {title:'Без ошибок',copy:'Пройдите урок идеально',active:Object.values(p.completed).some(c=>c.mistakes===0),icon:Star},
    {title:'Три дня подряд',copy:'Занимайтесь регулярно',active:currentStreak>=3,icon:Flame},
    {title:'Коллекционер',copy:'Изучите 10 слов',active:learned.length>=10,icon:BookOpen},
  ]
  async function begin(item:Lesson) {
    setLesson(item)
    const current=pRef.current
    if (current.draft?.id!==item.id) await save({...current,draft:{id:item.id,index:0,mistakes:0}},true)
    setRunning(true)
    window.scrollTo(0,0)
  }
  function record(current:Progress, q:Exercise, r:ExerciseResult) {
    if ((r.correct || r.skipped) && r.firstMistake === undefined) return current.errors
    return [{id:crypto.randomUUID(),prompt:q.prompt,given:r.firstMistake ?? r.given,expected:r.expected,at:Date.now()},...current.errors].slice(0,100)
  }
  async function step(r:ExerciseResult) {
    const current=pRef.current
    const draft=current.draft
    if (!lesson || !draft || draft.id!==lesson.id) return
    const mistakes=draft.mistakes+Number(!r.correct || r.firstMistake !== undefined)
    const errors=record(current,lesson.exercises[draft.index],r)
    if (draft.index+1<lesson.exercises.length) {
      await save({...current,errors,draft:{...draft,index:draft.index+1,mistakes}},true)
      return
    }
    const at=Date.now()
    const xp=current.completed[lesson.id]?0:20+(mistakes===0?10:0)
    const completed=xp ? {...current.completed,[lesson.id]:{xp,mistakes,day:day(),at}} : current.completed
    const activity=xp ? [...current.activity,{id:lesson.id,xp,day:day(),at}] : current.activity
    await save({...current,completed,activity,cards:addWords(current,lesson.words),errors,draft:undefined},true)
    setLesson(undefined);setRunning(false);setResult({title:lesson.title,xp,mistakes});window.scrollTo(0,0)
  }
  async function practiceStep(r:ExerciseResult) {
    if (!practice) return
    const current=pRef.current
    const word=practice.words[practice.index]
    const errors=record(current,review(word),r)
    const cards={...current.cards,[word.ky]:schedule(current.cards[word.ky],r.correct)}
    const mistakes=practice.mistakes+Number(!r.correct)
    if (practice.index+1<practice.words.length) {
      await save({...current,errors,cards},true);setPractice({...practice,index:practice.index+1,mistakes});return
    }
    const at=Date.now()
    const id='review:'+day()
    const xp=current.activity.some(a=>a.id===id)?0:10
    await save({...current,errors,cards,activity:xp?[...current.activity,{id,day:day(),xp,at}]:current.activity},true)
    setPractice(undefined);setResult({title:'Повторение слов',xp,mistakes,review:true})
  }
  async function installApp() {
    if (!install) return
    try {await install.prompt();await install.userChoice} finally {setInstall(undefined)}
  }
  async function sync() {
    if (syncing) return
    setSyncing(true);setSyncMessage('')
    try {const merged=await synchronize(pRef.current);save(mergeProgress(pRef.current,merged));setSyncMessage('Прогресс синхронизирован.')}
    catch {setSyncMessage('Синхронизация недоступна. Локальный прогресс сохранён.')}
    finally {setSyncing(false)}
  }
  const pageTitle=navigation.find(item=>item.id===page)?.title??'Скачать'
  const visible=learned.filter(word=>(!topic || levels.some(l=>l.lessons.some(item=>item.id===topic&&item.words.includes(word)))) &&
    (filter==='all'||(filter==='due' ? p.cards[word.ky].due<=Date.now() : p.cards[word.ky].box>=3)) &&
    `${word.ky} ${word.ru}`.toLocaleLowerCase('ru').includes(search.trim().toLocaleLowerCase('ru')))
  const map=<>
    <section className="hero">
      <div className="hero-copy"><span className="hero-kicker"><Mountain size={16}/> ЯЗЫК. КУЛЬТУРА. ПУТЬ.</span>
      <h1>Кыргызский<br/><em>с первого слова.</em></h1>
      <p>{p.name ? p.name+', продолжим? ' : ''}Пять минут в день, чтобы понимать больше и говорить увереннее.</p>
      <button className="hero-button" onClick={()=>{const item=level.lessons.find(l=>l.id===p.draft?.id)??nextLesson??level.lessons[0];setLesson(item);setRunning(false)}}>
        {p.draft&&level.lessons.some(l=>l.id===p.draft?.id)?'Продолжить урок':nextLesson?'Начать урок':'Повторить уровень'} <ArrowRight size={20}/>
      </button></div><Mascot/>
    </section>
    <div className="section-heading"><div><span className="eyebrow">ТВОЙ МАРШРУТ</span><h2>{level.title}</h2></div><label className="level-select">Уровень <select aria-label="Уровень" value={level.id} onChange={e=>save({...p,level:e.target.value})}>{levels.map(l=><option key={l.id}>{l.id}</option>)}</select></label></div>
    <div className="section-description"><span>{level.label}</span><b>{completedCount} из {level.lessons.length} уроков</b></div>
    <div className="lesson-list">{level.lessons.map((item,i)=>{
      const done=!!p.completed[item.id]
      const unlocked=i===0||!!p.completed[level.lessons[i-1].id]||done
      const active=unlocked&&!done
      return <button className={`lesson-card ${active?'active':''} ${done?'done':''}`} key={item.id} type="button" disabled={!unlocked} onClick={()=>{setLesson(item);setRunning(false);window.scrollTo(0,0)}}>
        <span className="lesson-icon">{done?<Check size={22}/>:!unlocked?<LockKeyhole size={18}/>:i===level.lessons.length-1?<Flag size={22}/>:<Star size={22}/>}</span>
        <span><small>{i===level.lessons.length-1?'ПРОВЕРКА':`УРОК ${String(i+1).padStart(2,'0')}`}</small><strong>{item.title}</strong></span>
        <span className="lesson-status">{done?'Пройден':active?'Готов к старту':'Закрыт'} <ChevronRight size={18}/></span>
      </button>
    })}</div>
    {!nextLesson&&levels.indexOf(level)<levels.length-1&&<div className="actions"><button className="primary" onClick={()=>save({...p,level:levels[levels.indexOf(level)+1].id})}>Открыть следующий уровень <ArrowRight size={18}/></button></div>}
  </>
  return <div className="app-shell">
    <aside className="sidebar"><button className="brand" onClick={()=>go('map')}><img src="/icon.svg" alt=""/><span>Сүйлө<small>КЫРГЫЗСКИЙ ЯЗЫК</small></span></button>
      <nav aria-label="Разделы">{navigation.map(({id,title,icon:Icon})=><button key={id} aria-current={page===id?'page':undefined} onClick={()=>go(id)}><Icon size={21}/><span>{title}</span></button>)}</nav>
      <button className="sidebar-install" onClick={()=>go('install')}><ArrowDownToLine size={19}/> Скачать приложение</button>
    </aside>
    <div className="workspace"><header className="topbar"><button className="brand mobile-brand" onClick={()=>go('map')}><img src="/icon.svg" alt=""/><span>Сүйлө</span></button><span className="breadcrumb">Обучение <ChevronRight size={14}/> <b>{pageTitle}</b></span>
      <div className="top-metrics"><span title="Серия дней"><Flame size={19} className="flame"/> {currentStreak}</span><span title="Весь опыт"><Zap size={18} className="zap"/> {total(p)} XP</span><button className="avatar" onClick={()=>go('settings')} aria-label="Профиль">{p.name.trim().slice(0,1).toUpperCase()||'С'}</button></div>
    </header>
    {!online&&<p className="notice">Офлайн · уроки и локальный прогресс доступны</p>}
    {storageError&&<p role="alert" className="notice">{storageError}</p>}
    {!ready ? <main className="main"><p role="status">Загружаем прогресс…</p></main> :
    <div className={`layout ${page==='map'&&!lesson&&!result?'with-aside':''}`}><main className="main">
      {running&&lesson&&p.draft?.id===lesson.id ? <ExerciseScreen key={lesson.id+p.draft.index} exercise={lesson.exercises[p.draft.index]} index={p.draft.index} length={lesson.exercises.length} title={lesson.title} guide={lessonGuides[lesson.id]} forgiving={p.forgiving} exit={()=>go('map')} next={step}/> :
      practice ? <ExerciseScreen key={'review'+practice.index} exercise={review(practice.words[practice.index])} index={practice.index} length={practice.words.length} title="Повторение слов" forgiving={p.forgiving} exit={()=>go('words')} next={practiceStep}/> :
      result ? <section className="surface finish page-entrance"><div className="finish-icon"><Trophy size={42}/></div><span className="eyebrow">АЗАМАТСЫЗ!</span><h1>{result.review?'Повторение завершено':'Урок завершён'}</h1><p>{result.title}</p><div className="result-numbers"><span><Zap size={21}/> +{result.xp} XP</span><span>{result.mistakes} ошибок / пропусков</span></div><button className="primary" onClick={()=>go(result.review?'words':'map')}>Продолжить <ArrowRight size={19}/></button></section> :
      lesson ? <section className="surface lesson-intro page-entrance">
        <button className="secondary" onClick={()=>go('map')}><ArrowLeft size={17}/> К урокам</button>
        <span className="eyebrow">{level.id} · {level.title}</span>
        <h1>{lesson.title}</h1><p className="lead">{lesson.goal}</p>
        <LessonWarmup key={lesson.id} guide={lessonGuides[lesson.id]}/>
        {lesson.words.length>0&&<details className="lesson-vocabulary"><summary>Слова урока · {lesson.words.length}</summary><div className="intro-words">{lesson.words.map(word=><div key={word.ky}><b lang="ky">{word.ky}</b><small>{word.ru}</small></div>)}</div></details>}
        <div className="lesson-start"><div><span className="eyebrow">ШАГ 3 · ПРАКТИКА</span><p>Правило можно открыть в любом задании.</p></div><button className="primary" onClick={()=>begin(lesson)}>{p.draft?.id===lesson.id?'Продолжить задания':'Перейти к заданиям'} <ArrowRight size={19}/></button></div>
      </section> :
      page==='map' ? map :
      page==='words' ? <div className="page-entrance"><div className="page-heading"><span className="eyebrow">ЛИЧНЫЙ СЛОВАРЬ</span><h1>Мои слова</h1><p>{learned.length} изучено · {due.length} пора повторить · {learned.filter(w=>p.cards[w.ky].box>=3).length} закреплено</p></div>
        <div className="surface word-tools"><label className="search"><Search size={18}/><input placeholder="Слово или перевод" aria-label="Найти слово" value={search} onChange={e=>setSearch(e.target.value)}/></label><select aria-label="Тема" value={topic} onChange={e=>setTopic(e.target.value)}><option value="">Все темы</option>{levels.flatMap(l=>l.lessons.filter(item=>item.words.length).map(item=><option key={item.id} value={item.id}>{item.title}</option>))}</select><select aria-label="Статус" value={filter} onChange={e=>setFilter(e.target.value)}><option value="all">Все слова</option><option value="due">Пора повторить</option><option value="known">Закреплённые</option></select><button className="primary" disabled={!due.length} onClick={()=>setPractice({words:due.slice(0,8),index:0,mistakes:0})}>Быстрое повторение <ArrowRight size={17}/></button></div>
        {wordError&&<p role="status" className="notice">{wordError}</p>}
        {!visible.length&&<div className="surface empty"><BookOpen size={30}/><h2>{learned.length?'Слов не найдено':'Здесь будут ваши слова'}</h2><p>{learned.length?'Попробуйте изменить поиск или фильтры.':'Завершите урок, чтобы добавить его слова в словарь.'}</p>{!learned.length&&<button className="secondary" onClick={()=>go('map')}>К урокам <ArrowRight size={17}/></button>}</div>}
        <div className="word-grid">{visible.map(word=><article className="surface word" key={word.ky}><div className="word-title"><h2 lang="ky">{word.ky}</h2><button className="icon-button" aria-label={`Произнести ${word.ky}`} onClick={()=>{setWordError('');speak(word.ky,()=>setWordError('Кыргызская озвучка этого слова недоступна.'))}}><Volume2 size={19}/></button></div><b>{word.ru}</b><p lang="ky">{word.example}</p><small>{p.cards[word.ky].due<=Date.now()?'Пора повторить':`Повторить ${new Date(p.cards[word.ky].due).toLocaleString('ru',{day:'numeric',month:'short',hour:'2-digit',minute:'2-digit'})}`}</small><div className="actions"><button className="secondary" onClick={()=>save({...p,cards:{...p.cards,[word.ky]:schedule(p.cards[word.ky],true)}})}>Знаю</button><button className="secondary" onClick={()=>save({...p,cards:{...p.cards,[word.ky]:schedule(p.cards[word.ky],false)}})}>Повторить</button></div></article>)}</div>
      </div> :
      page==='talk' ? <Conversation level={p.level} reviewWord={weak?.ky}/> :
      page==='stats' ? <div className="page-entrance"><div className="page-heading"><span className="eyebrow">ТВОИ РЕЗУЛЬТАТЫ</span><h1>Прогресс</h1><p>Следите за регулярностью и возвращайтесь к сложным фразам.</p></div>
        <div className="stat-grid">{[[total(p)+' XP','Всего опыта'],[currentStreak,'Дней подряд'],[Object.keys(p.completed).length,'Уроков завершено']].map(([n,label])=><div className="surface stat" key={label}><b>{n}</b><span>{label}</span></div>)}</div>
        <section className="surface stats-section"><h2>Последние 7 дней</h2><div className="week">{Array.from({length:7},(_,i)=>{const date=new Date();date.setDate(date.getDate()-6+i);const xp=p.activity.filter(a=>a.day===day(date)).reduce((s,a)=>s+a.xp,0);return <div key={day(date)}><b>{xp}</b><span className="bar"><i style={{height:`${Math.min(100,xp/Math.max(30,p.goal)*100)}%`}}/></span><small>{date.toLocaleDateString('ru',{weekday:'short'})}</small></div>})}</div></section>
        <section className="surface stats-section"><h2>Достижения</h2><div className="achievement-list">{achievements.map(({title,copy,active,icon:Icon})=><div key={title}><span className={active?'badge-icon unlocked':'badge-icon'}><Icon size={20}/></span><span><b>{title}</b><small>{copy}</small></span><span>{active?'Открыто':'Закрыто'}</span></div>)}</div></section>
        <section className="surface stats-section"><h2>История ошибок</h2>{!p.errors.length?<p className="muted">Ошибок пока нет.</p>:<div className="error-list">{p.errors.map(err=><div key={err.id}><b>{err.prompt}</b><small>Ваш ответ: {err.given}</small><small>Правильно: {err.expected}</small></div>)}</div>}</section>
      </div> :
      page==='settings' ? <div className="page-entrance"><div className="page-heading"><span className="eyebrow">ВАШЕ ПРОСТРАНСТВО</span><h1>Настройки</h1><p>Настройте темп и внешний вид приложения.</p></div><section className="surface settings">
        <h2>Профиль</h2><label>Имя<input value={p.name} maxLength={50} placeholder="Как к вам обращаться?" onChange={e=>save({...p,name:e.target.value})}/></label>
        <label>Уровень<select aria-label="Уровень" value={p.level} onChange={e=>save({...p,level:e.target.value})}>{levels.map(l=><option value={l.id} key={l.id}>{l.id} · {l.title}</option>)}</select></label>
        <label>Дневная цель<select aria-label="Дневная цель" value={p.goal} onChange={e=>save({...p,goal:Number(e.target.value)})}>{[10,20,30,50,80].map(goal=><option key={goal} value={goal}>{goal} XP</option>)}</select></label>
        <label>Тема<select aria-label="Тема" value={p.theme} onChange={e=>save({...p,theme:e.target.value as Progress['theme']})}><option value="system">Как на устройстве</option><option value="light">Светлая</option><option value="dark">Тёмная</option></select></label>
        <label className="checkbox"><input type="checkbox" checked={p.forgiving} onChange={e=>save({...p,forgiving:e.target.checked})}/> Разрешить ввод без ң, ө, ү</label>
        <small>Замена букв действует только при совпадении остального текста с допустимым ответом.</small>
      </section><section className="surface settings"><h2>Синхронизация</h2>
        {!cloud?<p>Прогресс хранится на этом устройстве. Облачная синхронизация появится после настройки сервера Supabase.</p>:
          cloudUser ? <><p>{cloudUser}</p><div className="actions"><button className="primary" disabled={syncing} onClick={()=>void sync()}>Синхронизировать</button><button className="secondary" onClick={()=>void cloud?.auth.signOut()}>Выйти</button></div></>:
          <form onSubmit={async e=>{e.preventDefault();const {error}=await cloud!.auth.signInWithOtp({email,options:{emailRedirectTo:location.origin+'/?page=settings'}});setSyncMessage(error?'Не удалось отправить письмо.':'Проверьте почту и откройте ссылку для входа.')}}><label>Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required/></label><button className="primary">Получить ссылку</button></form>}
        {syncMessage&&<p role="status">{syncMessage}</p>}</section></div> :
      <div className="page-entrance"><div className="page-heading"><span className="eyebrow">УЧИТЕСЬ В УДОБНОМ МЕСТЕ</span><h1>Скачать приложение</h1><p>Откройте «Сүйлө» с домашнего экрана и занимайтесь офлайн.</p></div><section className="surface settings">{isNative()?<p>У вас установлена версия для Android.</p>:install&&<button className="primary" onClick={()=>void installApp()}><ArrowDownToLine size={19}/> Установить «Сүйлө»</button>}<h2>Android</h2><p>В Chrome откройте меню ⋮ и выберите «Установить приложение» или «Добавить на главный экран».</p><h2>iPhone и iPad</h2><p>Откройте сайт в Safari, нажмите «Поделиться» → «На экран “Домой”» → «Добавить».</p><h2>Компьютер</h2><p>В Chrome или Edge нажмите значок установки в адресной строке либо найдите установку приложения в меню браузера.</p><small>Откройте сайт онлайн хотя бы один раз, чтобы загрузить уроки и словарь для офлайн-режима.</small></section></div>}
    </main>
    {page==='map'&&!lesson&&!result&&<aside className="right-rail">
      <section className="surface goal"><div className="rail-heading"><span className="rail-icon"><Target size={20}/></span><div><h2>Цель на сегодня</h2><small>Понемногу каждый день</small></div></div><div className="goal-label"><b>{currentDay} <span>/ {p.goal} XP</span></b><span>{Math.min(100,Math.round(100*currentDay/p.goal))}%</span></div><div className="meter"><i style={{width:`${Math.min(100,100*currentDay/p.goal)}%`}}/></div></section>
      <section className="surface rail-talk"><span className="rail-icon"><MessagesSquare size={21}/></span><span className="eyebrow">ПОРА ГОВОРИТЬ</span><h2>Сүйлөшөлү!</h2><p>Попробуйте заказать чай или познакомиться по-кыргызски.</p><button onClick={()=>go('talk')}>К диалогам <ArrowRight size={16}/></button></section>
      <section className="surface rail-achieve"><div className="rail-heading"><span className="rail-icon"><Trophy size={20}/></span><div><h2>Достижения</h2><small>{achievements.filter(a=>a.active).length} из {achievements.length} открыто</small></div></div><div className="badge-row">{achievements.map(({title,active,icon:Icon})=><span key={title} title={title} className={active?'badge-icon unlocked':'badge-icon'}><Icon size={19}/></span>)}</div><button onClick={()=>go('stats')}>Смотреть прогресс <ChevronRight size={16}/></button></section>
      <p className="rail-signature"><Sparkles size={15}/> Аз-аздан — көп болот.</p>
    </aside>}
    </div>}
    <footer><GraduationCap size={15}/> Сүйлө <span>·</span> <button onClick={()=>go('install')}>Скачать приложение</button></footer></div>
  </div>
}
createRoot(document.getElementById('root')!).render(<App/>)
