/* Imported by the PWA service worker; never caches API responses. */
self.addEventListener('push', event => {
  let data
  try { data = event.data.json() } catch { return }
  event.waitUntil(self.registration.showNotification(data.title || 'Ozon Production', {
    body: data.body, tag: data.tag, icon: '/icon-192.png', data: { url: data.url },
  }))
})
self.addEventListener('notificationclick', event => {
  event.notification.close()
  const target = new URL(event.notification.data?.url || '/notifications', self.location.origin)
  if (target.origin !== self.location.origin) return
  event.waitUntil((async () => {
    const windows = await self.clients.matchAll({ type: 'window', includeUncontrolled: true })
    for (const client of windows) {
      if ('focus' in client) { await client.navigate(target.href); return client.focus() }
    }
    return self.clients.openWindow(target.href)
  })())
})
