#!/usr/bin/python3
"""Ubuntu launcher; credentials are handled by OpenSSH askpass, never stored."""
import json,os,re,socket,subprocess,time,urllib.request
from pathlib import Path

def ui(*args):
    return subprocess.run(['zenity',*args],stdout=subprocess.PIPE,stderr=subprocess.DEVNULL,text=True)
def error(message):ui('--error','--title=GitDeck','--text='+message)
def main():
    config=Path.home()/'.config/gitdeck-desktop/settings.json'
    try:saved=json.loads(config.read_text())
    except (OSError,ValueError):saved={}
    form=ui('--forms','--title=GitDeck — подключение','--text=Подключение к серверу через защищённый SSH-туннель. Пароль спросит OpenSSH; приложение его не сохраняет.','--separator=|','--add-entry=Сервер','--add-entry=Пользователь SSH','--add-entry=Порт SSH (22)','--add-entry=Локальный порт (8120)','--add-entry=Порт GitDeck на сервере (8120)')
    if form.returncode:return
    host,user,sshport,local,remote=form.stdout.strip().split('|')
    host=host.strip() or saved.get('host','2.28.57.159');user=user.strip() or saved.get('user','root')
    try:
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9.-]{0,252}',host) or not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_-]{0,63}',user):raise ValueError()
        sshport,local,remote=[int(v or default) for v,default in [(sshport,22),(local,8120),(remote,8120)]]
        if not all(1<=v<=65535 for v in (sshport,local,remote)):raise ValueError()
    except ValueError:error('Проверьте адрес, пользователя и порты.');return
    try:
        with socket.socket() as sock:sock.bind(('127.0.0.1',local))
    except OSError:error('Локальный порт занят. Закройте прежнее подключение или укажите другой порт.');return
    config.parent.mkdir(parents=True,exist_ok=True);config.write_text(json.dumps({'host':host,'user':user}));config.chmod(0o600)
    env=dict(os.environ,SSH_ASKPASS=str(Path(__file__).with_name('ssh-askpass.py')),SSH_ASKPASS_REQUIRE='force')
    import tempfile
    with tempfile.TemporaryFile() as log:
        process=subprocess.Popen(['ssh','-N','-T','-p',str(sshport),'-o','ExitOnForwardFailure=yes','-o','StrictHostKeyChecking=ask','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','NumberOfPasswordPrompts=1','-L',f'127.0.0.1:{local}:127.0.0.1:{remote}',user+'@'+host],stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,start_new_session=True)
        progress=subprocess.Popen(['zenity','--progress','--pulsate','--title=GitDeck','--text=Подключение к серверу…','--no-percentage'],stdin=subprocess.PIPE,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
        try:
            ready=False
            for _ in range(180):
                if progress.poll() is not None:return
                if process.poll() is not None:break
                try:
                    with urllib.request.urlopen(f'http://127.0.0.1:{local}/health',timeout=1) as response:
                        data=json.load(response);ready=data.get('ok') is True and bool(data.get('version'))
                    if ready:break
                except (OSError,ValueError):pass
                time.sleep(.5)
            progress.terminate();progress.wait()
            if not ready:
                log.seek(0);error('Не удалось подключиться к GitDeck.\n'+log.read(4000).decode(errors='replace'));return
            subprocess.Popen(['xdg-open',f'http://127.0.0.1:{local}/'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            status=subprocess.Popen(['zenity','--info','--title=GitDeck подключён','--text=GitDeck открыт в браузере. Пока это окно открыто, SSH-туннель работает.\n\nЗакройте окно, чтобы отключиться.','--ok-label=Отключиться'],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
            while status.poll() is None and process.poll() is None:time.sleep(.5)
            if process.poll() is not None and status.poll() is None:status.terminate();error('SSH-соединение прервано. Запустите GitDeck повторно.')
        finally:
            if progress.poll() is None:progress.terminate();progress.wait()
            if process.poll() is None:
                process.terminate()
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
if __name__=='__main__':main()
