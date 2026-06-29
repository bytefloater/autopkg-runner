const CACHE_NAME = 'autopkg-runner-1777891200';
const FETCH_TIMEOUT = 3000; // 3 seconds before showing error page

const STATIC_ASSETS = [
  '/dashboard/',
  '/runs/',
  '/schedule/',
  '/config/',
  '/api-tokens/',
];

// Install: pre-cache the manifest, offline error page, and Tailwind CSS
self.addEventListener('install', (event) => {
  self.skipWaiting();
  event.waitUntil(
    caches.open(CACHE_NAME).then((cache) =>
      cache.addAll(['/manifest.json', '/static/offline-error.html', '/static/css/tailwind.css'])
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

// -- Helpers -------------------------------------------------------------------

function _getErrorPage(errorType, errorCode) {
  return caches.match('/static/offline-error.html')
    .then((errorPage) => {
      if (!errorPage) return new Response('Offline', { status: 503 });

      // Clone and build error URL with query parameters
      const url = new URL('/static/offline-error.html', self.location.origin);
      url.searchParams.set('type', errorType);
      if (errorCode) url.searchParams.set('code', errorCode);
      url.searchParams.set('timestamp', new Date().toISOString());

      return new Response(errorPage.body, {
        status: errorPage.status,
        statusText: errorPage.statusText,
        headers: errorPage.headers
      });
    });
}

// Fetch strategy:
// - Static assets (CSS/JS/SVG/PNG from CDN or /static/): cache-first
// - API calls (/api/): network-only
// - Pages: network-first with 3s timeout, never cache pages
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

  // Pages: network-first with fast timeout, never cache pages
  event.respondWith(
    Promise.race([
      fetch(event.request),
      new Promise((_, reject) =>
        setTimeout(() => reject(new Error('timeout')), FETCH_TIMEOUT)
      )
    ])
      .then((response) => {
        // Return all responses without caching pages
        // (pages can change, only cache static assets)
        if (response.status >= 500) {
          // 5xx errors: show error page
          return _getErrorPage('gateway', response.status);
        }
        return response;
      })
      .catch((err) => {
        // Network error or timeout: show error page
        const errorType = err.message === 'timeout' ? 'timeout' : 'offline';
        return _getErrorPage(errorType);
      })
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
