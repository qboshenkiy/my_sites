#!/usr/bin/python3
import subprocess,sys
prompt=sys.argv[1] if len(sys.argv)>1 else 'Пароль SSH'
if 'yes/no' in prompt:
    r=subprocess.run(['zenity','--question','--title=GitDeck — ключ сервера','--text='+prompt+'\n\nПодтверждайте только ключ вашего сервера. При изменении известного ключа SSH остановит подключение.'],stdout=subprocess.DEVNULL)
    print('yes' if r.returncode==0 else 'no')
    sys.exit(0)
r=subprocess.run(['zenity','--password','--title=GitDeck — SSH','--text='+prompt],stdout=subprocess.PIPE,text=True)
if r.returncode:sys.exit(1)
sys.stdout.write(r.stdout)
