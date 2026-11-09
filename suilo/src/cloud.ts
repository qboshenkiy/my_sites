import { createClient } from '@supabase/supabase-js'
import { mergeProgress, type Progress } from './progress'

const url = import.meta.env.VITE_SUPABASE_URL
const key = import.meta.env.VITE_SUPABASE_ANON_KEY
export const cloud = url && key ? createClient(url,key) : undefined
export async function synchronize(local:Progress) {
  if (!cloud) throw new Error('Облако не настроено.')
  const {data:{user},error:authError}=await cloud.auth.getUser()
  if (!user || authError) throw new Error('Войдите по email.')
  for (let i=0;i<3;i++) {
    const {data,error}=await cloud.from('suilo_progress').select('progress,revision').eq('user_id',user.id).maybeSingle()
    if (error) throw error
    const merged=data ? mergeProgress(local,data.progress as Progress) : local
    if (!data) {
      const {error:insertError}=await cloud.from('suilo_progress').insert({user_id:user.id,progress:merged,revision:1})
      if (!insertError) return merged
      if (insertError.code==='23505') continue
      throw insertError
    }
    const {data:updated,error:updateError}=await cloud.from('suilo_progress')
      .update({progress:merged,revision:data.revision+1}).eq('user_id',user.id).eq('revision',data.revision).select('revision')
    if (updateError) throw updateError
    if (updated.length) return merged
  }
  throw new Error('Прогресс меняется на другом устройстве. Повторите синхронизацию.')
}
