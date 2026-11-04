#!/usr/bin/python3
"""GTK application with an embedded WebKit panel and an owned SSH tunnel."""
import json,os,signal,socket,subprocess,tempfile,threading,time,urllib.request
from pathlib import Path
import gi
gi.require_version('Gtk','3.0');gi.require_version('WebKit2','4.1')
from gi.repository import Gtk,GLib,WebKit2
from settings import load,save,validate

def terminate(process):
    try:os.killpg(process.pid,signal.SIGTERM)
    except ProcessLookupError:pass

class Window(Gtk.Window):
    def __init__(self):
        super().__init__(title='GitDeck 1.1.2');self.set_default_size(1160,820)
        self.path=Path.home()/'.config/gitdeck-desktop/settings.json';self.values=load(self.path)
        self.process=None;self.stop_event=threading.Event();self.generation=0
        self.connect('delete-event',self.close)
        outer=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=10);self.add(outer)
        bar=Gtk.Box(spacing=10);bar.set_border_width(10);outer.pack_start(bar,False,False,0)
        self.status=Gtk.Label(label='Подключитесь к серверу');bar.pack_start(self.status,True,True,0)
        reload=Gtk.Button(label='Обновить страницу');reload.connect('clicked',lambda *_:self.web.reload());bar.pack_start(reload,False,False,0)
        disconnect=Gtk.Button(label='Настройки / отключиться');disconnect.connect('clicked',self.disconnect);bar.pack_start(disconnect,False,False,0)
        self.stack=Gtk.Stack();outer.pack_start(self.stack,True,True,0)
        form=Gtk.Box(orientation=Gtk.Orientation.VERTICAL,spacing=14);form.set_border_width(32)
        form.pack_start(Gtk.Label(label='Подключение GitDeck через SSH',xalign=0),False,False,0)
        grid=Gtk.Grid(column_spacing=16,row_spacing=12);form.pack_start(grid,False,False,0);self.fields={}
        for i,(key,label) in enumerate([('host','Сервер'),('user','Пользователь SSH'),('ssh_port','Порт SSH'),('local_port','Локальный порт'),('remote_port','Порт панели на сервере')]):
            grid.attach(Gtk.Label(label=label,xalign=0),0,i,1,1);entry=Gtk.Entry();entry.set_text(str(self.values[key]));entry.set_hexpand(True);grid.attach(entry,1,i,1,1);self.fields[key]=entry
        self.remember=Gtk.CheckButton(label='Запомнить пароль SSH в системной связке ключей');self.remember.set_active(self.values['remember']);form.pack_start(self.remember,False,False,0)
        forget=Gtk.Button(label='Забыть сохранённый пароль');forget.connect('clicked',self.forget);form.pack_start(forget,False,False,0)
        self.connect_button=Gtk.Button(label='Сохранить и подключиться');self.connect_button.connect('clicked',self.begin);form.pack_start(self.connect_button,False,False,0)
        form.pack_start(Gtk.Label(label='SSH использует настроенный ключ и при необходимости запрашивает пароль. Все поля сохраняются.\nЗакрытие приложения отключает SSH-туннель.',xalign=0),False,False,0)
        self.stack.add_named(form,'settings')
        data=Path.home()/'.local/share/gitdeck-desktop/web';cache=Path.home()/'.cache/gitdeck-desktop/web';data.mkdir(parents=True,exist_ok=True);cache.mkdir(parents=True,exist_ok=True)
        manager=WebKit2.WebsiteDataManager(base_data_directory=str(data),base_cache_directory=str(cache))
        context=WebKit2.WebContext.new_with_website_data_manager(manager)
        context.get_cookie_manager().set_persistent_storage(str(data/'cookies.sqlite'),WebKit2.CookiePersistentStorage.SQLITE)
        self.web=WebKit2.WebView.new_with_context(context);self.web.connect('load-failed',self.load_failed)
        self.stack.add_named(self.web,'panel');self.stack.set_visible_child_name('settings');self.show_all()
    def current(self):return validate({**{k:e.get_text() for k,e in self.fields.items()},'remember':self.remember.get_active()})
    def show_error(self,text):
        self.status.set_text(text);d=Gtk.MessageDialog(transient_for=self,modal=True,message_type=Gtk.MessageType.ERROR,buttons=Gtk.ButtonsType.CLOSE,text=text);d.run();d.destroy()
    def begin(self,*_):
        try:
            self.values=self.current();original=self.values['local_port']
            for candidate in range(original,min(65535,original+20)+1):
                try:
                    with socket.socket() as sock:sock.bind(('127.0.0.1',candidate))
                    self.values['local_port']=candidate;self.fields['local_port'].set_text(str(candidate));break
                except OSError:continue
            else:raise ValueError('Нет свободного локального порта. Укажите другой порт.')
            save(self.path,self.values)
        except (ValueError,OSError) as error:self.show_error(str(error));return
        self.stop_event=threading.Event();self.generation+=1;generation=self.generation
        self.connect_button.set_sensitive(False);self.status.set_text('Подключение… Если появится окно SSH, введите пароль пользователя сервера.')
        threading.Thread(target=self.connect_tunnel,args=(dict(self.values),generation,self.stop_event),daemon=True).start()
    def deliver(self,generation,ready,text):
        if generation!=self.generation:return False
        self.connect_button.set_sensitive(True)
        if ready:
            self.status.set_text('Подключено: '+self.values['host']);self.stack.set_visible_child_name('panel');self.web.load_uri(f"http://127.0.0.1:{self.values['local_port']}/")
        else:self.stack.set_visible_child_name('settings');self.show_error(text)
        return False
    def connect_tunnel(self,v,generation,stop):
        process=None
        try:
            with socket.socket() as sock:sock.bind(('127.0.0.1',v['local_port']))
            env=dict(os.environ,SSH_ASKPASS=str(Path(__file__).with_name('ssh-askpass.py')),SSH_ASKPASS_REQUIRE='force',GITDECK_REMEMBER='1' if v['remember'] else '0',GITDECK_HOST=v['host'],GITDECK_USER=v['user'],GITDECK_PORT=str(v['ssh_port']))
            with tempfile.TemporaryFile() as log:
                process=subprocess.Popen(['ssh','-N','-T','-p',str(v['ssh_port']),'-o','ExitOnForwardFailure=yes','-o','StrictHostKeyChecking=ask','-o','ConnectTimeout=15','-o','ServerAliveInterval=15','-o','ServerAliveCountMax=3','-o','NumberOfPasswordPrompts=1','-L',f"127.0.0.1:{v['local_port']}:127.0.0.1:{v['remote_port']}",v['user']+'@'+v['host']],stdin=subprocess.DEVNULL,stdout=log,stderr=log,env=env,start_new_session=True)
                self.process=process;ready=False
                for _ in range(180):
                    if stop.is_set():return
                    if process.poll() is not None:
                        log.seek(0);raise RuntimeError(log.read(3000).decode(errors='replace') or 'SSH завершил подключение.')
                    try:
                        with urllib.request.urlopen(f"http://127.0.0.1:{v['local_port']}/health",timeout=1) as response:
                            health=json.load(response);ready=health.get('ok') is True and bool(health.get('version'))
                        if ready:break
                    except (OSError,ValueError):pass
                    stop.wait(.5)
                if not ready:raise RuntimeError('SSH-туннель не открыл панель. Проверьте порт GitDeck на сервере.')
                GLib.idle_add(self.deliver,generation,True,'')
                while not stop.wait(.5):
                    if process.poll() is not None:raise RuntimeError('SSH-соединение прервано. Можно подключиться повторно.')
        except Exception as error:
            if not stop.is_set():GLib.idle_add(self.deliver,generation,False,str(error))
        finally:
            if process and process.poll() is None:
                terminate(process)
                try:process.wait(timeout=5)
                except subprocess.TimeoutExpired:process.kill();process.wait()
    def disconnect(self,*_):
        # Persist edits even when the user disconnects or closes the settings window.
        try:save(self.path,self.current())
        except (ValueError,OSError):pass
        self.stop_event.set();self.generation+=1
        if self.process and self.process.poll() is None:terminate(self.process)
        self.process=None;self.web.stop_loading();self.web.load_uri('about:blank');self.stack.set_visible_child_name('settings');self.connect_button.set_sensitive(True);self.status.set_text('Отключено')
    def forget(self,*_):
        try:
            gi.require_version('Secret','1')
            from gi.repository import Secret
            v=self.current();schema=Secret.Schema.new('net.gitdeck.SSH',Secret.SchemaFlags.NONE,{'host':Secret.SchemaAttributeType.STRING,'user':Secret.SchemaAttributeType.STRING,'port':Secret.SchemaAttributeType.STRING})
            Secret.password_clear_sync(schema,{'host':v['host'],'user':v['user'],'port':str(v['ssh_port'])},None);self.status.set_text('Сохранённый пароль удалён')
        except Exception as error:self.show_error('Не удалось открыть связку ключей: '+str(error))
    def load_failed(self,web,event,uri,error):
        if not uri.startswith('about:'):self.status.set_text('Ошибка загрузки панели. Проверьте соединение или обновите страницу.')
        return False
    def close(self,*_):self.disconnect();Gtk.main_quit();return False
if __name__=='__main__':Window();Gtk.main()
