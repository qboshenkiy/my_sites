"""Small bounded Docker Unix socket client. Only fixed container operations are exposed."""
import http.client
import json
import socket
import struct
import urllib.parse


class UnixConnection(http.client.HTTPConnection):
    def __init__(self):
        super().__init__('localhost',timeout=25)
    def connect(self):
        self.sock=socket.socket(socket.AF_UNIX,socket.SOCK_STREAM)
        self.sock.settimeout(self.timeout)
        self.sock.connect('/var/run/docker.sock')


def request(method,path,data=None,limit=8*1024*1024):
    connection=UnixConnection()
    try:
        body=json.dumps(data).encode() if data is not None else None
        connection.request(method,'/v1.44'+path,body,{'Content-Type':'application/json'})
        response=connection.getresponse();raw=response.read(limit+1)
        if len(raw)>limit:raise ValueError('Журнал слишком большой. Уменьшите период.')
        if response.status>=300:raise ValueError('Docker не выполнил запрос. Проверьте контейнер.')
        return raw
    finally:
        connection.close()


def demux(raw):
    # Docker multiplexes stdout/stderr as 8-byte headers unless the container has TTY.
    chunks=[];position=0
    while position+8<=len(raw) and raw[position:position+4] in (b'\x01\x00\x00\x00',b'\x02\x00\x00\x00'):
        length=struct.unpack('>I',raw[position+4:position+8])[0]
        if position+8+length>len(raw):break
        chunks.append(raw[position+8:position+8+length]);position+=8+length
    return (b''.join(chunks) if chunks else raw).decode('utf-8',errors='replace')


def inspect(name):
    info=json.loads(request('GET','/containers/'+urllib.parse.quote(name,safe='')+'/json'))
    state=info.get('State',{})
    return {'status':state.get('Status','unknown'),'restarts':info.get('RestartCount',0),'started':state.get('StartedAt',''),
            'exit_code':state.get('ExitCode'),'oom_killed':bool(state.get('OOMKilled')),
            'health':state.get('Health',{}).get('Status'),'finished':state.get('FinishedAt','')}


def logs(name,since=0,tail=10000,timestamps=False):
    query=urllib.parse.urlencode({'stdout':1,'stderr':1,'since':int(since),'tail':tail})
    if timestamps:query+='&timestamps=1'
    return demux(request('GET','/containers/'+urllib.parse.quote(name,safe='')+'/logs?'+query))


def execute(name,command,user=None):
    config={'AttachStdout':True,'AttachStderr':True,'Cmd':command}
    if user:config['User']=user
    created=json.loads(request('POST','/containers/'+urllib.parse.quote(name,safe='')+'/exec',config))
    identifier=created['Id']
    output=demux(request('POST','/exec/'+identifier+'/start',{'Detach':False,'Tty':False},limit=2*1024*1024))
    state=json.loads(request('GET','/exec/'+identifier+'/json'))
    try:result=json.loads(output)
    except ValueError:raise ValueError('Этот бот ещё не обновлён для работы с Guard.') from None
    if state.get('ExitCode') or result.get('error'):raise ValueError(result.get('error','Не удалось выполнить действие бота'))
    return result
