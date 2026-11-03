#!/usr/bin/python3
import os,subprocess,sys
prompt=sys.argv[1] if len(sys.argv)>1 else 'Пароль SSH'
if 'yes/no' in prompt:
    result=subprocess.run(['zenity','--question','--no-markup','--title=GitDeck — ключ сервера','--text='+prompt+'\n\nПодтвердите отпечаток только вашего сервера.'],stdout=subprocess.DEVNULL)
    print('yes' if result.returncode==0 else 'no');sys.exit(0)
schema=None;attributes=None;Secret=None
remember=os.getenv('GITDECK_REMEMBER')=='1'
# Cache server passwords only; private-key passphrases still use the normal prompt.
if remember and 'password' in prompt.lower() and 'passphrase' not in prompt.lower():
    try:
        import gi
        gi.require_version('Secret','1')
        from gi.repository import Secret
        schema=Secret.Schema.new('net.gitdeck.SSH',Secret.SchemaFlags.NONE,{'host':Secret.SchemaAttributeType.STRING,'user':Secret.SchemaAttributeType.STRING,'port':Secret.SchemaAttributeType.STRING})
        attributes={k:os.environ['GITDECK_'+k.upper()] for k in ('host','user','port')}
        cached=Secret.password_lookup_sync(schema,attributes,None)
        if cached:print(cached);sys.exit(0)
    except Exception:
        schema=None
        subprocess.run(['zenity','--warning','--text=Системная связка ключей недоступна. Подключение продолжится без сохранения пароля.'],stdout=subprocess.DEVNULL)
result=subprocess.run(['zenity','--password','--title=GitDeck — SSH','--text='+prompt],stdout=subprocess.PIPE,text=True)
if result.returncode:sys.exit(1)
password=result.stdout.rstrip('\n')
if schema:
    try:Secret.password_store_sync(schema,attributes,Secret.COLLECTION_DEFAULT,'GitDeck SSH '+attributes['host'],password,None)
    except Exception:
        subprocess.run(['zenity','--warning','--text=Не удалось сохранить пароль в системной связке ключей. Подключение продолжится без сохранения.'],stdout=subprocess.DEVNULL)
print(password)
