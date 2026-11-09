import recordings from './audio.json'
export type InstallEvent = Event & { prompt(): Promise<void>; userChoice: Promise<{outcome:string}> }
type WebApp = { initData: string; ready():void; expand():void; colorScheme?:string; setHeaderColor?(color:string):void; setBackgroundColor?(color:string):void }
type Recognition = {
  lang:string; interimResults:boolean; maxAlternatives:number;
  onresult: ((e:{results: ArrayLike<ArrayLike<{transcript:string}>>})=>void)|null;
  onerror: (()=>void)|null; onend:(()=>void)|null; start():void; abort():void;
}
type Platform = Window & { Telegram?: {WebApp?:WebApp}; SpeechRecognition?: new()=>Recognition; webkitSpeechRecognition?: new()=>Recognition; Capacitor?: {isNativePlatform():boolean} }
const platform = window as Platform
export const isNative = () => !!platform.Capacitor?.isNativePlatform()
export function connectTelegram() {
  if (!/tgWebApp(?:Data|Version|Platform)/.test(location.hash+location.search)) return
  const script = document.createElement('script')
  script.src='https://telegram.org/js/telegram-web-app.js'
  script.onload=()=>{
    const app=platform.Telegram?.WebApp
    if (!app) return
    app.ready()
    app.expand()
    app.setHeaderColor?.('#184c3b')
  }
  document.head.append(script)
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
