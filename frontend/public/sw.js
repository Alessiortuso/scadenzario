/* Service worker dello Scadenzario: riceve i Web Push e mostra la notifica
   desktop anche quando l'applicazione non è aperta in nessuna scheda. */

const ICON = '/favicon.ico';

self.addEventListener('install', (event) => {
  self.skipWaiting();
});

self.addEventListener('activate', (event) => {
  event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
  let payload = {};
  try {
    payload = event.data ? event.data.json() : {};
  } catch {
    payload = { title: 'Scadenzario', body: event.data ? event.data.text() : '' };
  }

  const title = payload.title || 'Scadenzario';
  const options = {
    body: payload.body || '',
    icon: ICON,
    badge: ICON,
    tag: payload.tag || `scadenzario-${Date.now()}`,
    renotify: Boolean(payload.tag),
    requireInteraction: payload.severity === 'danger' || payload.severity === 'critical',
    data: { url: payload.url || '/', notificationId: payload.notificationId },
    actions: [{ action: 'open', title: 'Apri scadenza' }],
  };

  event.waitUntil(self.registration.showNotification(title, options));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const target = (event.notification.data && event.notification.data.url) || '/';

  event.waitUntil(
    self.clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
      for (const client of clientList) {
        if ('focus' in client) {
          client.postMessage({ type: 'navigate', url: target });
          return client.focus();
        }
      }
      return self.clients.openWindow(target);
    }),
  );
});
