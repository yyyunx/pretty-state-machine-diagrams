"use strict";
importScripts("./offline-manifest.js");
const root = self.registration.scope;
const prefix = "pretty-smd-" + root + "-";
const version = prefix + self.PRETTY_OFFLINE.version;
const routes = new Set(self.PRETTY_OFFLINE.files.map(path=>new URL(path,root).href));

self.addEventListener("install",event=>event.waitUntil((async ()=>{
  const cache = await caches.open(version);
  await cache.addAll([...routes].map(url=>new Request(url,{cache:"reload"})));
})()));

self.addEventListener("activate",event=>event.waitUntil((async ()=>{
  await Promise.all((await caches.keys()).filter(key=>key.startsWith(prefix) && key!==version).map(key=>caches.delete(key)));
  await self.clients.claim();
})()));

self.addEventListener("fetch",event=>{
  if (event.request.method!=="GET") return;
  const url = new URL(event.request.url);
  if (!url.href.startsWith(root)) return;
  url.search = ""; url.hash = "";
  if (url.pathname.endsWith("/")) url.pathname += "index.html";
  if (!routes.has(url.href)) return;
  event.respondWith((async ()=>{
    const cache = await caches.open(version);
    return (await cache.match(url.href)) || fetch(event.request);
  })());
});
