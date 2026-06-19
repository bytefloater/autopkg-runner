const CACHE_NAME = 'autopkg-runner-v4';

const STATIC_ASSETS = [
  '/dashboard/',
  '/runs/',
  '/schedule/',
  '/config/',
  '/api-tokens/',
];

// Install: pre-cache the manifest
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(['/manifest.json'])
    )
  );
});

// Activate: remove old caches
self.addEventListener('activate', (event) => {
  event.waitUntil(
    caches.keys().then((keys) =>
      Promise.all(keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k)))
    )
  );
  self.clients.claim();
});

// Fetch strategy:
// - Static assets (CSS/JS/SVG/PNG from CDN or /static/): cache-first
// - API calls (/api/): network-only
// - Pages: network-first, fall back to cache
self.addEventListener('fetch', (event) => {
  const url = new URL(event.request.url);

  // Skip non-GET and cross-origin requests
  if (event.request.method !== 'GET' || url.origin !== self.location.origin) return;

  // API: always network
  if (url.pathname.startsWith('/api/')) return;

  // Splash screens are large and only used by iOS at launch - skip caching.
  if (url.pathname.startsWith('/static/splash_screens/')) return;

  // Static assets: cache-first
  if (url.pathname.startsWith('/static/') || url.hostname.includes('cdn.')) {
    event.respondWith(
      caches.match(event.request).then((cached) => {
        if (cached) return cached;
        return fetch(event.request).then((response) => {
          if (response.ok) {
            const clone = response.clone();
            caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
          }
          return response;
        });
      })
    );
    return;
  }

  // Pages: network-first
  event.respondWith(
    fetch(event.request)
      .then((response) => {
        if (response.ok) {
          const clone = response.clone();
          caches.open(CACHE_NAME).then((c) => c.put(event.request, clone));
        }
        return response;
      })
      .catch(() => caches.match(event.request))
  );
});

// -- Web Push ------------------------------------------------------------------

// Receive a push message from the server and display a notification.
self.addEventListener('push', (event) => {
  let data = { title: 'AutoPkg Runner', body: 'A run has completed.' };
  if (event.data) {
    try { data = JSON.parse(event.data.text()); } catch (_) {}
  }

  const title   = data.title || 'AutoPkg Runner';
  const options = {
    body:  data.body  || '',
    icon:  '/static/logos/icon-192.png',
    badge: '/static/logos/icon-192.png',
    data:  { url: data.url || '/dashboard/' },
    vibrate: [200, 100, 200],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

// When the user taps the notification, open/focus the relevant page.
self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const targetUrl = (event.notification.data && event.notification.data.url)
    ? event.notification.data.url
    : '/dashboard/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((windowClients) => {
      // If there's already an open window at the same origin, focus it.
      for (const client of windowClients) {
        if (new URL(client.url).origin === self.location.origin && 'focus' in client) {
          client.navigate(targetUrl);
          return client.focus();
        }
      }
      // Otherwise open a new window.
      if (clients.openWindow) return clients.openWindow(targetUrl);
    })
  );
});
