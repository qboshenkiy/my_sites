const CACHE='app-static-v2';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE)));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>(key.startsWith('app-static-')||key==='pulse-static-v1')&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting();});
self.addEventListener('fetch',event=>{
 const request=event.request,url=new URL(request.url);
 if(request.method!=='GET'||url.origin!==location.origin)return;
 if(request.mode==='navigate'){
  event.respondWith(fetch(request).catch(()=>new Response('<!doctype html><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Нет соединения</title><body style="font:18px/1.6 system-ui;padding:10vh 8vw;background:#f7f7f2;color:#26382f"><h1>Нет соединения</h1><p>Подключитесь к интернету и откройте приложение снова. Ваши записи хранятся на сервере.</p><button onclick="location.reload()" style="font:inherit;padding:12px 20px">Повторить</button>',{headers:{'Content-Type':'text/html; charset=utf-8'}})));return;
 }
 if(url.pathname.endsWith('.php')||url.pathname.startsWith('/api/')||url.pathname.startsWith('/storage/')||!/\.(?:css|js|png|jpe?g|svg|webp|ico|woff2?)$/i.test(url.pathname))return;
 event.respondWith(fetch(request).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(request,copy));}return response;}).catch(()=>caches.match(request)));
});
