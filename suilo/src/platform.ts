import recordings from './audio.json'
export type InstallEvent = Event & { prompt(): Promise<void>; userChoice: Promise<{outcome:string}> }
type WebApp = { BackButton?:{show():void;hide():void;onClick(fn:()=>void):void;offClick(fn:()=>void):void}; initData: string; ready():void; expand():void; colorScheme?:string; setHeaderColor?(color:string):void; setBackgroundColor?(color:string):void }
type Recognition = {
  lang:string; interimResults:boolean; maxAlternatives:number;
  onresult: ((e:{results: ArrayLike<ArrayLike<{transcript:string}>>})=>void)|null;
  onerror: (()=>void)|null; onend:(()=>void)|null; start():void; abort():void;
}
type Platform = Window & { Telegram?: {WebApp?:WebApp}; SpeechRecognition?: new()=>Recognition; webkitSpeechRecognition?: new()=>Recognition; Capacitor?: {isNativePlatform():boolean} }
const platform = window as Platform
export const isNative = () => !!platform.Capacitor?.isNativePlatform()
let telegramReady:Promise<string>|undefined
export function telegramBack(handler?:()=>void) {
  const button=platform.Telegram?.WebApp?.BackButton
  if(!button)return ()=>{}
  if(!handler){button.hide();return ()=>{}}
  button.show();button.onClick(handler)
  return ()=>{button.offClick(handler);button.hide()}
}
export function connectTelegram():Promise<string> {
  if (!/tgWebApp(?:Data|Version|Platform)/.test(location.hash+location.search)) return Promise.resolve('')
  if(telegramReady)return telegramReady
  telegramReady=new Promise(resolve=>{
    const raw=new URLSearchParams(location.hash.slice(1)).get('tgWebAppData')??new URLSearchParams(location.search).get('tgWebAppData')??''
    const script=document.createElement('script')
    let completed=false
    const complete=()=>{
      if(completed)return
      completed=true
      const app=platform.Telegram?.WebApp
      document.documentElement.dataset.telegram='true'
      if(app){app.ready();app.expand();app.setHeaderColor?.('#184c3b')}
      resolve(app?.initData||raw)
    }
    script.src='https://telegram.org/js/telegram-web-app.js'
    script.onload=complete;script.onerror=complete
    document.head.append(script)
    setTimeout(complete,8000)
  })
  return telegramReady
}
export function speak(text:string, failed:()=>void) {
  const recording = (recordings as Record<string,string>)[text]
  if (recording) {
    const audio = new Audio(recording)
    void audio.play().catch(failed)
    return
  }
  if (!('speechSynthesis' in window)) return failed()
  const voice = speechSynthesis.getVoices().find(v=>/^(ky|kir)([-_]|$)/i.test(v.lang))
  if (!voice) return failed()
  const phrase = new SpeechSynthesisUtterance(text)
  phrase.lang='ky-KG'; phrase.voice=voice; phrase.rate=.85; phrase.onerror=failed
  speechSynthesis.cancel()
  speechSynthesis.speak(phrase)
}
export function recognize(done:(text:string)=>void, failed:()=>void) {
  const Constructor = platform.SpeechRecognition ?? platform.webkitSpeechRecognition
  if (!Constructor) {failed(); return}
  const recognition = new Constructor()
  recognition.lang='ky-KG'; recognition.interimResults=false; recognition.maxAlternatives=1
  let answered = false
  const fail = ()=>{ if (!answered) { answered=true; failed() } }
  recognition.onresult=e=>{answered=true; done(e.results[0][0].transcript)}
  recognition.onerror=fail
  recognition.onend=fail
  try {recognition.start()} catch {fail()}
  return ()=>{ answered=true; recognition.abort() }
}
