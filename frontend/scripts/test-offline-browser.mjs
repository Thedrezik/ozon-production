// Run after npm run build. Set PLAYWRIGHT_MODULE to a bundled playwright index.mjs if needed.
import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const user = { id: 1, username: 'mock', display_name: 'Mock worker', roles: ['PRODUCTION_WORKER'], permissions: ['orders.view', 'orders.change_status'], csrf_token: 'test-only' }
let revoked = false
let unavailable = false
let version = 1
let conflict = false
let delayQueue = false
let writes = 0
const row = () => ({ id: 1, posting_number: 'MOCK-OFFLINE', internal_status: version === 1 ? 'QUEUED' : 'IN_PRODUCTION', ozon_status: 'awaiting_packaging', assigned_user: { id: 1, display_name: 'Mock worker' }, shipment_deadline: '2026-10-03T12:00:00Z', priority: { level: 'P1', label: 'Срочный', reasons: ['Mock priority'], pinned: false, manual_override: null, blocked: false }, tariff: null, items: [{ product_name: `Стол mock v${version}`, quantity: 1, production_profile: null }] })
const server = createServer(async (request, response) => {
  const path = new URL(request.url, 'http://localhost').pathname
  if (path.startsWith('/api/')) {
    response.setHeader('Cache-Control', 'no-store')
    response.setHeader('Content-Type', 'application/json')
    if (unavailable) { response.destroy(); return }
    if (path === '/api/auth/me' && revoked) { response.writeHead(401); response.end('{}'); return }
    if (request.method !== 'GET') { writes++; if (conflict) { version = 2; response.writeHead(409); response.end('{"detail":"Conflict"}'); return } }
    if (path === '/api/orders/events') { response.setHeader('Content-Type', 'text/event-stream'); response.write(': mock\n\n'); return }
    if (path === '/api/orders' && delayQueue) await new Promise(resolve => setTimeout(resolve, 1500))
    const body = path === '/api/auth/me' ? user : path === '/api/health' ? { mock_mode: true } : path === '/api/orders' ? { items: [row()], total: 1 } : path === '/api/orders/statuses' || path === '/api/blockers/types' ? [] : { items: [] }
    response.end(JSON.stringify(body)); return
  }
  const allowed = /^\/(assets\/[\w.-]+|[\w.-]+)$/.test(path)
  const file = allowed ? path.slice(1) : 'index.html'
  try {
    const data = await readFile(new URL(`../dist/${file}`, import.meta.url))
    response.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.png') ? 'image/png' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html')
    response.end(data)
  } catch { response.writeHead(404); response.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const origin = `http://127.0.0.1:${server.address().port}`
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const context = await browser.newContext({ viewport: { width: 390, height: 844 }, serviceWorkers: 'allow' })
  const page = await context.newPage()
  await page.goto(origin)
  await page.getByText('Стол mock v1 × 1', { exact: true }).waitFor()
  await page.evaluate(async () => { await navigator.serviceWorker.ready; if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true })) })
  const savedAt = await page.evaluate(() => JSON.parse(sessionStorage.getItem('production.queue.v1')).savedAt)
  await context.setOffline(true)
  await page.getByText('OFFLINE · Нет связи с сервером', { exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Начать производство', exact: true }).count(), 0)
  await page.reload()
  await page.getByText('OFFLINE · Нет связи с сервером', { exact: true }).waitFor()
  await page.getByText('Стол mock v1 × 1', { exact: true }).waitFor()
  assert.ok((await page.locator('main').innerText()).includes('Данные могут быть устаревшими'))
  assert.equal(await page.evaluate(() => JSON.parse(sessionStorage.getItem('production.queue.v1')).savedAt), savedAt)
  version = 2; delayQueue = true
  await context.setOffline(false)
  await page.getByText('Данные могут быть устаревшими. Ожидаем успешное обновление с сервера.', { exact: false }).waitFor()
  await page.getByText('Стол mock v2 × 1', { exact: true }).waitFor()
  await page.getByText('Очередь загружена с сервера.', { exact: false }).waitFor()
  assert.equal(writes, 0)
  delayQueue = false; version = 1; conflict = true
  await page.getByRole('button', { name: 'Обновить очередь', exact: true }).click()
  await page.getByText('Стол mock v1 × 1', { exact: true }).waitFor()
  await page.getByRole('button', { name: 'Начать производство', exact: true }).click()
  await page.getByText('Заказ изменился или переход уже недоступен.', { exact: false }).waitFor()
  await page.getByText('Стол mock v2 × 1', { exact: true }).waitFor()
  assert.equal(writes, 1)
  unavailable = true
  await page.getByRole('button', { name: 'Обновить очередь', exact: true }).click()
  await page.getByText('OFFLINE · Нет связи с сервером', { exact: true }).waitFor()
  assert.equal(await page.evaluate(() => navigator.onLine), true)
  unavailable = false; revoked = true
  await page.getByRole('button', { name: 'Проверить соединение', exact: true }).click()
  await page.getByRole('heading', { name: 'Вход', exact: true }).waitFor()
  assert.equal(await page.evaluate(() => sessionStorage.getItem('production.queue.v1')), null)
  const entries = await page.evaluate(async () => (await Promise.all((await caches.keys()).map(async key => (await (await caches.open(key)).keys()).map(request => request.url)))).flat())
  assert.ok(entries.every(url => !url.includes('/api/')))
  revoked = false
  const freshContext = await browser.newContext({ serviceWorkers: 'allow' })
  const freshPage = await freshContext.newPage()
  await freshPage.goto(origin)
  await freshPage.getByText('Стол mock v2 × 1', { exact: true }).waitFor()
  await freshPage.evaluate(async () => { await navigator.serviceWorker.ready; if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true })) })
  await freshContext.setOffline(true)
  await freshPage.getByText('OFFLINE · Нет связи с сервером', { exact: true }).waitFor()
  await freshPage.getByRole('button', { name: 'Закрыть и удалить offline-данные', exact: true }).click()
  await freshPage.reload()
  await freshPage.getByText('Нет сохранённой очереди или срок хранения истёк.', { exact: false }).waitFor()
  assert.equal(await freshPage.getByText('Стол mock v2 × 1', { exact: true }).count(), 0)
  await freshContext.close()
  console.log('Edge PWA: offline reload/shell + queue, OFFLINE/stale/time, reconnect fresh read, no deferred writes, conflict refresh, backend outage, auth revocation and no API cache passed')
  await context.close()
} finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
