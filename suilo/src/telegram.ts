import { fresh, mergeProgress, type Progress } from './progress'
let sessionToken=''
const authHeaders=():Record<string,string>=>sessionToken?{Authorization:'Bearer '+sessionToken}:{}
export type TelegramUser={id:number;name:string;username:string}
async function request(path:string, options:RequestInit={}) {
  const response=await fetch(path,{...options,credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000),headers:{'Content-Type':'application/json','X-Suilo-Request':'1',...authHeaders(),...options.headers}})
  if(!response.ok)throw new Error(response.status===401?'Откройте приложение заново из бота Telegram.':response.status===503?'Вход Telegram ещё не подключён на сервере.':'Сервер временно недоступен.')
  return response.json()
}
export async function telegramLogin(initData:string):Promise<TelegramUser> {
  const data=await request('/api/auth/telegram',{method:'POST',body:JSON.stringify({initData})})
  sessionToken=data.session
  return data.user
}
export async function telegramSync(local:Progress):Promise<Progress> {
  for(let attempt=0;attempt<3;attempt++) {
    const remote=await request('/api/progress')
    const merged=remote.progress?mergeProgress(local,{...structuredClone(fresh),...remote.progress}):local
    const response=await fetch('/api/progress',{method:'PUT',credentials:'same-origin',cache:'no-store',signal:AbortSignal.timeout(12000),headers:{'Content-Type':'application/json','X-Suilo-Request':'1',...authHeaders()},body:JSON.stringify({revision:remote.revision,progress:merged})})
    if(response.status===409)continue
    if(!response.ok)throw new Error('Не удалось сохранить на сервере.')
    return merged
  }
  throw new Error('Прогресс изменился на другом устройстве. Повторим позже.')
}
export const inTelegram=()=>/tgWebApp(?:Data|Version|Platform)/.test(location.hash+location.search)
