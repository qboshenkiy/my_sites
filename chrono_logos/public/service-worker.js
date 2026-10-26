const CACHE='pulse-static-v1';
self.addEventListener('install',event=>event.waitUntil(caches.open(CACHE)));
self.addEventListener('activate',event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener('message',event=>{if(event.data?.type==='SKIP_WAITING')self.skipWaiting();});
self.addEventListener('fetch',event=>{
  const request=event.request,url=new URL(request.url);
  if(request.method!=='GET'||url.origin!==location.origin||url.pathname.endsWith('.php')||url.pathname.startsWith('/api/')||url.pathname.startsWith('/storage/'))return;
  if(!/\.(?:css|js|png|jpe?g|svg|webp|ico|woff2?)$/i.test(url.pathname))return;
  event.respondWith(fetch(request).then(response=>{if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(request,copy));}return response;}).catch(()=>caches.match(request)));
});
