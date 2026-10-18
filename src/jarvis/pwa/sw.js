const CACHE="jarvis-shell-v10";
const SHELL=["/app/","/app/app.css","/app/app.js?v=10","/app/pcm-worklet.js?v=10","/app/manifest.webmanifest","/app/icon.svg"];
// Never restore an enabled microphone policy from a cached document.
function offlineDocument(response){if(!response)return response;const headers=new Headers(response.headers);headers.set("Permissions-Policy","camera=(), microphone=(), geolocation=()");return new Response(response.body,{status:response.status,headers});}
self.addEventListener("install",event=>event.waitUntil(caches.open(CACHE).then(cache=>cache.addAll(SHELL)).then(()=>self.skipWaiting())));
self.addEventListener("activate",event=>event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith("jarvis-shell-")&&key!==CACHE).map(key=>caches.delete(key)))).then(()=>self.clients.claim())));
self.addEventListener("fetch",event=>{
  const url=new URL(event.request.url);
  const shellKey=url.pathname+url.search;
  if(event.request.method!=="GET"||url.origin!==self.location.origin||!SHELL.includes(shellKey))return;
  if(url.pathname==="/app/"){
    event.respondWith(fetch(event.request,{cache:"no-store"}).catch(()=>caches.match("/app/").then(offlineDocument)));return;
  }
  event.respondWith(caches.match(event.request).then(cached=>cached||fetch(event.request).then(response=>{
    if(response.ok){const copy=response.clone();caches.open(CACHE).then(cache=>cache.put(event.request,copy));}
    return response;
  })));
});
self.addEventListener("message",event=>{
  if(event.data!=="JARVIS_LOGOUT")return;
  event.waitUntil(caches.keys().then(keys=>Promise.all(keys.filter(key=>key.startsWith("jarvis-shell-")).map(key=>caches.delete(key)))).then(()=>self.registration.unregister()));
});
