"""Visible, user-controlled Windows agent for Vano Remote."""
import asyncio
import base64
import io
import json
import os
from pathlib import Path
import queue
import secrets
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox
from urllib.parse import urlsplit

import aiohttp
import mss
from PIL import Image, ImageTk
from pynput import keyboard, mouse

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from shared.protocol import Channel, derive

CONFIG = Path(os.environ.get('LOCALAPPDATA', '.')) / 'VanoRemote' / 'pairing.json'

class Agent:
    def __init__(self):
        if os.name == 'nt':
            import ctypes
            try: ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except OSError: pass
        self.root = tk.Tk()
        self.root.title('Vano Remote — Windows')
        self.root.geometry('760x780')
        self.root.configure(bg='#101827')
        self.events = queue.Queue(maxsize=8)
        self.commands = queue.Queue(maxsize=64)
        self.stop = threading.Event()
        self.thread = None
        self.mouse = mouse.Controller()
        self.keyboard = keyboard.Controller()
        self.monitor = None
        self.phone_rect = (0, 0, 1, 1)
        self.phone_on = False
        self.pressed_at = None
        self.pairing = json.loads(CONFIG.read_text()) if CONFIG.exists() else {
            'server': 'wss://connect.vano.sbena.net',
            'room': secrets.token_hex(16), 'secret': secrets.token_urlsafe(32)}
        tk.Label(self.root, text='VANO / REMOTE', fg='#63ead2', bg='#101827', font=('Segoe UI', 22, 'bold')).pack(pady=(20, 4))
        tk.Label(self.root, text='Личный доступ • подтверждение отпечатком на телефоне', fg='white', bg='#101827').pack()
        self.url = tk.StringVar(value=self.pairing['server'])
        tk.Entry(self.root, textvariable=self.url, font=('Segoe UI', 12), width=65).pack(pady=12)
        row = tk.Frame(self.root, bg='#101827'); row.pack()
        self.start_button = tk.Button(row, text='Включить доступ', command=self.start)
        self.start_button.pack(side='left', padx=5)
        tk.Button(row, text='Отключить', command=self.disconnect).pack(side='left', padx=5)
        self.pair_button = tk.Button(row, text='Код привязки', command=self.show_pairing)
        self.pair_button.pack(side='left', padx=5)
        self.reset_button = tk.Button(row, text='Отозвать телефон', command=self.revoke)
        self.reset_button.pack(side='left', padx=5)
        self.status = tk.StringVar(value='Доступ выключен')
        tk.Label(self.root, textvariable=self.status, fg='#63ead2', bg='#101827', wraplength=720).pack(pady=10)
        tk.Label(self.root, text='Экран телефона появится после подтверждения на Android', fg='white', bg='#101827').pack()
        self.canvas = tk.Canvas(self.root, bg='#070d16', highlightthickness=0, height=350)
        self.canvas.pack(fill='both', expand=True, padx=20, pady=10)
        self.canvas.bind('<ButtonPress-1>', self.down)
        self.canvas.bind('<ButtonRelease-1>', self.up)
        toolbar = tk.Frame(self.root, bg='#101827'); toolbar.pack(pady=5)
        for label, name in [('Назад', 'back'), ('Домой', 'home'), ('Приложения', 'recents')]:
            tk.Button(toolbar, text=label, command=lambda n=name:self.control({'type':'action','name':n})).pack(side='left', padx=5)
        textrow = tk.Frame(self.root); textrow.pack(fill='x', padx=20, pady=(0,15))
        self.text = tk.Entry(textrow); self.text.pack(side='left', fill='x', expand=True)
        tk.Button(textrow, text='Текст на телефон', command=self.send_text).pack(side='left')
        self.root.protocol('WM_DELETE_WINDOW', self.close)
        self.root.after(70, self.poll)

    def persist(self):
        self.pairing['server'] = self.url.get().strip().rstrip('/')
        u = urlsplit(self.pairing['server'])
        if u.scheme != 'wss' or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('','/'):
            raise ValueError('Нужен адрес вида wss://connect.vano.sbena.net')
        CONFIG.parent.mkdir(parents=True, exist_ok=True)
        CONFIG.write_text(json.dumps(self.pairing), encoding='utf-8')
        if os.name == 'nt':
            sid = subprocess.check_output(['whoami', '/user', '/fo', 'csv', '/nh'], creationflags=0x08000000).decode(errors='replace').strip().split(',')[-1].strip('"')
            subprocess.run(['icacls', str(CONFIG), '/inheritance:r', '/grant:r', f'*{sid}:(F)', '*S-1-5-18:(F)'], check=True, capture_output=True, creationflags=0x08000000)

    def show_pairing(self):
        try: self.persist()
        except Exception as e: messagebox.showerror('Настройка', str(e)); return
        win = tk.Toplevel(self.root); win.title('Код привязки — секретный')
        tk.Label(win, text='Передай этот код только своему телефону. Он даёт доступ к ПК.').pack(padx=20,pady=10)
        field = tk.Text(win, width=75, height=6)
        field.insert('1.0', json.dumps(self.pairing)); field.pack(padx=20,pady=10)
        tk.Label(win, text='В Android: вставить код → сохранить с отпечатком.').pack(pady=10)

    def revoke(self):
        if not messagebox.askyesno('Отозвать доступ', 'Удалить привязку? Телефон потребуется привязать заново.'): return
        self.disconnect()
        self.pairing.update(room=secrets.token_hex(16), secret=secrets.token_urlsafe(32))
        try: self.persist(); self.status.set('Привязка отозвана. Создай новый код.')
        except Exception as e: messagebox.showerror('Ошибка',str(e))

    def start(self):
        if self.thread and self.thread.is_alive(): return
        try: self.persist()
        except Exception as e: messagebox.showerror('Настройка', str(e)); return
        self.stop.clear()
        self.start_button.config(state='disabled'); self.pair_button.config(state='disabled'); self.reset_button.config(state='disabled')
        self.thread = threading.Thread(target=lambda: asyncio.run(self.run()), daemon=True)
        self.thread.start()

    def disconnect(self):
        self.stop.set()
        self.phone_on = False
        while not self.commands.empty():
            try: self.commands.get_nowait()
            except queue.Empty: break

    def close(self):
        self.disconnect(); self.root.destroy()

    def emit(self, kind, value):
        try: self.events.put_nowait((kind,value))
        except queue.Full: pass

    def poll(self):
        try:
            while True:
                kind,value = self.events.get_nowait()
                if kind == 'status': self.status.set(value)
                elif kind == 'phone':
                    self.phone_on = True
                    im = Image.open(io.BytesIO(base64.b64decode(value))).convert('RGB')
                    im.thumbnail((max(1,self.canvas.winfo_width()),max(1,self.canvas.winfo_height())))
                    w,h=im.size; x=(self.canvas.winfo_width()-w)//2; y=(self.canvas.winfo_height()-h)//2
                    self.phone_rect=(x,y,w,h)
                    self.photo=ImageTk.PhotoImage(im)
                    self.canvas.delete('all'); self.canvas.create_image(x,y,anchor='nw',image=self.photo)
                elif kind == 'phone_off':
                    self.phone_on=False; self.canvas.delete('all')
                elif kind == 'ended':
                    self.start_button.config(state='normal'); self.pair_button.config(state='normal'); self.reset_button.config(state='normal')
        except queue.Empty: pass
        self.root.after(70,self.poll)

    def point(self,e):
        x,y,w,h=self.phone_rect
        if not (x<=e.x<x+w and y<=e.y<y+h): return None
        return [(e.x-x)/w,(e.y-y)/h]

    def down(self,e): self.pressed_at=self.point(e)
    def up(self,e):
        end=self.point(e)
        if self.pressed_at and end: self.control({'type':'gesture','start':self.pressed_at,'end':end})
        self.pressed_at=None

    def control(self,value):
        if self.phone_on:
            try:self.commands.put_nowait(value)
            except queue.Full:pass

    def send_text(self):
        self.control({'type':'text','value':self.text.get()[:2000]}); self.text.delete(0,'end')

    def input(self, value):
        kind=value.get('type')
        if kind in ('click','drag') and self.monitor:
            x=max(0,min(1,float(value['x']))); y=max(0,min(1,float(value['y'])))
            m=self.monitor
            self.mouse.position=(m['left']+round(x*(m['width']-1)),m['top']+round(y*(m['height']-1)))
            if kind=='drag':
                ex=max(0,min(1,float(value['ex'])));ey=max(0,min(1,float(value['ey'])))
                self.mouse.press(mouse.Button.left)
                try:
                    for i in range(1,9):
                        self.mouse.position=(m['left']+round((x+(ex-x)*i/8)*(m['width']-1)),m['top']+round((y+(ey-y)*i/8)*(m['height']-1)))
                        time.sleep(.015)
                finally:self.mouse.release(mouse.Button.left)
            else:self.mouse.click(mouse.Button.right if value.get('button')=='right' else mouse.Button.left)
        elif kind=='scroll': self.mouse.scroll(0,max(-10,min(10,int(value['dy']))))
        elif kind=='text': self.keyboard.type(str(value['value'])[:2000])
        elif kind=='key':
            keys={'enter':keyboard.Key.enter,'backspace':keyboard.Key.backspace,'esc':keyboard.Key.esc,'tab':keyboard.Key.tab,'up':keyboard.Key.up,'down':keyboard.Key.down,'left':keyboard.Key.left,'right':keyboard.Key.right}
            k=keys.get(value.get('name'))
            if k: self.keyboard.press(k); self.keyboard.release(k)

    async def run(self):
        p=dict(self.pairing)
        try:
            async with aiohttp.ClientSession(timeout=aiohttp.ClientTimeout(total=None,sock_connect=15)) as session:
                while not self.stop.is_set():
                    try:
                        self.emit('status','Соединение с сервером…')
                        headers={'Authorization':'Bearer '+derive('auth:',p['secret']).hex()}
                        async with session.ws_connect(p['server']+'/ws/'+p['room']+'/windows',headers=headers,heartbeat=20,max_msg_size=4_000_000) as ws:
                            self.emit('status','Ожидаю телефон. Доступ включён — окно должно оставаться открытым.')
                            state={'channel':None}
                            async def receive():
                                async for msg in ws:
                                    if msg.type==aiohttp.WSMsgType.TEXT:
                                        if json.loads(msg.data).get('event')=='paired':
                                            state['channel']=Channel(p['secret'],'windows')
                                            await ws.send_bytes(state['channel'].hello())
                                    elif msg.type==aiohttp.WSMsgType.BINARY:
                                        channel=state['channel']
                                        if not channel: raise ValueError('Handshake missing')
                                        value=channel.receive(msg.data)
                                        if value is None:self.emit('status','Телефон подключён • экран и управление доступны')
                                        elif value.get('type')=='frame':self.emit('phone',value['jpeg'])
                                        elif value.get('type')=='sharing_stopped':self.emit('phone_off',None)
                                        else:self.input(value)
                                    elif msg.type==aiohttp.WSMsgType.ERROR:raise ConnectionError('WebSocket error')
                            async def transmit():
                                with mss.mss() as capture:
                                    self.monitor=capture.monitors[1]
                                    while not self.stop.is_set() and not ws.closed:
                                        channel=state['channel']
                                        if channel and channel.key:
                                            shot=capture.grab(self.monitor)
                                            im=Image.frombytes('RGB',shot.size,shot.rgb)
                                            im.thumbnail((1280,800))
                                            out=io.BytesIO(); im.save(out,'JPEG',quality=55)
                                            await ws.send_bytes(channel.send({'type':'frame','jpeg':base64.b64encode(out.getvalue()).decode()}))
                                            while not self.commands.empty():
                                                await ws.send_bytes(channel.send(self.commands.get_nowait()))
                                        await asyncio.sleep(.22)
                                await ws.close()
                            tasks=[asyncio.create_task(receive()),asyncio.create_task(transmit())]
                            try:
                                done,pending=await asyncio.wait(tasks,return_when=asyncio.FIRST_COMPLETED)
                                for task in pending:task.cancel()
                                await asyncio.gather(*pending,return_exceptions=True)
                                for task in done:task.result()
                            finally:
                                for task in tasks:task.cancel()
                                await asyncio.gather(*tasks,return_exceptions=True)
                    except Exception as e:
                        self.emit('status','Нет соединения: '+str(e)[:170])
                    self.emit('phone_off',None)
                    for _ in range(20):
                        if self.stop.is_set():break
                        await asyncio.sleep(.1)
        finally:
            self.emit('status','Доступ выключен');self.emit('ended',None)

if __name__=='__main__':
    agent=Agent()
    if '--smoke-test' in sys.argv:
        agent.root.update();agent.root.destroy()
    else:
        agent.root.mainloop()
