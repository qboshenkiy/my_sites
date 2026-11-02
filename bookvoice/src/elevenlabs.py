"""Explicit opt-in ElevenLabs transport; fixed API origin, server-side key only."""
import json,re,urllib.request,urllib.error,urllib.parse
from pathlib import Path

MODEL='eleven_multilingual_v2'

def request_api(key,path,body=None):
    req=urllib.request.Request('https://api.elevenlabs.io'+path,data=None if body is None else json.dumps(body).encode(),headers={'xi-api-key':key,'Content-Type':'application/json','Accept':'audio/mpeg' if body else 'application/json'})
    try:
        with urllib.request.urlopen(req,timeout=120) as response:
            result=response.read(24*1024*1024+1)
            if len(result)>24*1024*1024:raise ValueError('ElevenLabs вернул слишком большой ответ.')
            return result
    except urllib.error.HTTPError as error:
        if error.code in [401,403]:raise ValueError('ElevenLabs: проверьте API-ключ, права Text to Speech и Voices и доступ к голосу.') from None
        if error.code in [402,429]:raise ValueError('ElevenLabs: лимит аккаунта или слишком много запросов. Проверьте аккаунт перед продолжением.') from None
        raise ValueError('ElevenLabs: не удалось озвучить фрагмент (HTTP '+str(error.code)+'). Повторите вручную после проверки аккаунта.') from None
    except (urllib.error.URLError,TimeoutError,OSError):raise ValueError('Нет ответа ElevenLabs. Проверьте интернет и историю аккаунта перед повтором: запрос мог быть учтён в лимите.') from None

def list_voices(key):
    voices=[];token=None
    for _ in range(20):
        params={'page_size':100,'include_total_count':'false'}
        if token:params['next_page_token']=token
        data=json.loads(request_api(key,'/v2/voices?'+urllib.parse.urlencode(params)))
        for item in data.get('voices',[]):
            id=item.get('voice_id','')
            if re.fullmatch(r'[A-Za-z0-9_-]{1,100}',id):voices.append({'id':id,'name':str(item.get('name',id))[:120]})
        if not data.get('has_more'):break
        token=data.get('next_page_token')
        if not token:break
    if not voices:raise ValueError('В аккаунте не найдены доступные голоса. Добавьте голос в ElevenLabs и обновите список.')
    return list({v['id']:v for v in voices}.values())

def render(key,text,path,voice,speed):
    if not re.fullmatch(r'[A-Za-z0-9_-]{1,100}',voice):raise ValueError('Выберите голос ElevenLabs.')
    raw=request_api(key,'/v1/text-to-speech/'+voice+'?output_format=mp3_44100_128',{'text':text,'model_id':MODEL,'voice_settings':{'stability':.5,'similarity_boost':.75,'style':0,'use_speaker_boost':True,'speed':float(speed)}})
    if not raw or raw[:1] in [b'{',b'<']:raise ValueError('ElevenLabs не вернул аудио. Проверьте настройки аккаунта.')
    Path(path).write_bytes(raw)
