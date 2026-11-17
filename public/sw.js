// Service worker da Semente: faz o app abrir mesmo sem internet.
//
// Estratégia: sempre tenta a rede primeiro (o cliente vê a versão mais nova) e só
// usa a cópia guardada quando está offline. Cotações, notícias e login nunca são
// guardados: sem internet, essas partes simplesmente não atualizam.

const CACHE = 'semente-v1';
const SHELL = [
  '/semente.html',
  '/privacidade.html',
  '/config.js',
  '/manifest.webmanifest',
  '/icons/icon-192.png',
  '/icons/icon-512.png',
  '/icons/apple-touch-icon.png',
];

self.addEventListener('install', (event) => {
  event.waitUntil(
    caches.open(CACHE)
      // Um arquivo faltando não pode impedir a instalação dos outros.
      .then((cache) => Promise.allSettled(SHELL.map((url) => cache.add(url))))
      .then(() => self.skipWaiting())
  );
});

self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim())
  );
});

self.addEventListener('fetch', (event) => {
  const req = event.request;
  const url = new URL(req.url);
  // Só cuida de leituras do próprio site; APIs e outros domínios passam direto.
  if (req.method !== 'GET' || url.origin !== self.location.origin || url.pathname.startsWith('/api/')) return;

  event.respondWith(
    fetch(req)
      .then((res) => {
        if (res.ok) {
          const copy = res.clone();
          caches.open(CACHE).then((cache) => cache.put(req, copy));
        }
        return res;
      })
      .catch(async () => {
        const cached = await caches.match(req, { ignoreSearch: true });
        if (cached) return cached;
        // Abrindo o app offline pelo endereço raiz: entrega a página principal.
        if (req.mode === 'navigate') {
          const home = await caches.match('/semente.html');
          if (home) return home;
        }
        return new Response('Sem conexão.', { status: 503, headers: { 'content-type': 'text/plain; charset=utf-8' } });
      })
  );
});
