"""Connection preferences contain no passwords."""
import json,os,re
from pathlib import Path
DEFAULTS={'host':'2.28.57.159','user':'root','ssh_port':22,'local_port':8120,'remote_port':8120,'remember':False}
def load(path):
    try:data=json.loads(Path(path).read_text())
    except (OSError,ValueError):data={}
    # Migrate the first version's host/user preferences.
    return {**DEFAULTS,**{k:v for k,v in data.items() if k in DEFAULTS}}
def validate(values):
    result=dict(values)
    for name,pattern in [('host',r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}'),('user',r'[A-Za-z_][A-Za-z0-9_-]{0,63}')]:
        result[name]=str(result[name]).strip()
        if not re.fullmatch(pattern,result[name]):raise ValueError('Проверьте адрес сервера и пользователя SSH.')
    for name in ('ssh_port','local_port','remote_port'):
        try:result[name]=int(result[name])
        except (TypeError,ValueError):raise ValueError('Порты должны быть числами от 1 до 65535.')
        if not 1<=result[name]<=65535:raise ValueError('Порты должны быть числами от 1 до 65535.')
    result['remember']=bool(result['remember'])
    return result
def save(path,values):
    values=validate(values);path=Path(path);path.parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    temp=path.with_name(path.name+'.tmp')
    fd=os.open(temp,os.O_WRONLY|os.O_CREAT|os.O_TRUNC,0o600)
    with os.fdopen(fd,'w') as f:json.dump(values,f)
    os.chmod(temp,0o600);os.replace(temp,path)
