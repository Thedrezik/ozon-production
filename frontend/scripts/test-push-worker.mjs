import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'

const handlers = {}
const shown = []
const opened = []
const self = {
  location: { origin: 'https://production.example' },
  addEventListener: (name, handler) => { handlers[name] = handler },
  registration: { showNotification: async (...args) => { shown.push(args) } },
  clients: { matchAll: async () => [], openWindow: async url => { opened.push(url) } },
}
vm.runInNewContext(readFileSync(new URL('../public/push-worker.js', import.meta.url), 'utf8'), { self, URL })
const notice = { title: 'Проблема', body: 'Нет детали', tag: 'notification-1', url: '/manager-tasks/42' }
let pending
handlers.push({ data: { json: () => notice }, waitUntil: value => { pending = value } })
await pending
assert.equal(shown[0][1].tag, notice.tag)
assert.equal(shown[0][1].data.url, '/manager-tasks/42')
handlers.notificationclick({ notification: { close() {}, data: { url: '/manager-tasks/42' } }, waitUntil: value => { pending = value } })
await pending
assert.deepEqual(opened, ['https://production.example/manager-tasks/42'])
handlers.notificationclick({ notification: { close() {}, data: { url: 'https://evil.example/' } }, waitUntil: () => assert.fail('External URL opened') })
let navigated
let focused = false
self.clients.matchAll = async () => [{ navigate: async url => { navigated = url }, focus: async () => { focused = true } }]
handlers.notificationclick({ notification: { close() {}, data: { url: '/orders/123' } }, waitUntil: value => { pending = value } })
await pending
assert.equal(navigated, 'https://production.example/orders/123')
assert.equal(focused, true)
handlers.push({ data: null, waitUntil: () => assert.fail('Empty push displayed') })
console.log('Push worker: display, task/order links, focus and same-origin checks passed')
