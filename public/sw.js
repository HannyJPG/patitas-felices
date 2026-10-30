const CACHE_NAME = "patitas-felices-pwa-v2";
const RECURSOS_BASE = ["/", "/login", "/tienda", "/doctor", "/admin", "/agendar-cita", "/img/logotipoveterinaria.jpg"];

self.addEventListener("install", evento => {
    evento.waitUntil(
        caches.open(CACHE_NAME).then(cache => cache.addAll(RECURSOS_BASE)).catch(() => {})
    );
    self.skipWaiting();
});

self.addEventListener("activate", evento => {
    evento.waitUntil(
        caches.keys().then(claves =>
            Promise.all(claves.filter(c => c !== CACHE_NAME).map(c => caches.delete(c)))
        )
    );
    self.clients.claim();
});

self.addEventListener("fetch", evento => {
    if (evento.request.method !== "GET" || evento.request.url.includes("/api/")) return;
    evento.respondWith(
        fetch(evento.request).catch(() => caches.match(evento.request))
    );
});
