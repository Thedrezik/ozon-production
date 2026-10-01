import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const user = { id: 1, display_name: 'Mock manager', roles: ['MANAGER'], permissions: ['analytics.view'], csrf_token: 'mock' }
let empty = false
let query = ''
const data = () => ({ timezone: 'Europe/Moscow', intervals: Object.fromEntries(['new_to_production', 'production', 'produced_to_ready', 'cycle'].map(key => [key, { count: empty ? 0 : 1, average_minutes: empty ? null : 120 }])), throughput: { received: 1, started: 1, produced: 1, ready: 1, overdue: 0 }, blockers: [], sku: { items: empty ? [] : [{ sku: 'MOCK-SKU', offer_id: 'A', orders: 1, average_minutes: 120, normative_minutes_per_unit: 45 }], total: 21 }, employees: { items: [{ user_id: 1, name: 'Worker', processed_orders: 1 }], total: 1 }, current_workload: { items: [], total: 0 } })
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  if (url.pathname.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json')
    if (url.pathname === '/api/orders/events') { res.setHeader('Content-Type', 'text/event-stream'); res.write(': mock\n\n'); return }
    if (url.pathname === '/api/analytics') query = url.search
    res.end(JSON.stringify(url.pathname === '/api/auth/me' ? user : url.pathname === '/api/health' ? { mock_mode: true } : url.pathname === '/api/analytics' ? data() : { as_of: '2026-01-02T00:00:00Z', critical: 0, blocked: 0, ready: 0, overdue: 0, manager_tasks: 0, attention: [], tasks: [], workload: [] })); return
  }
  const file = /^\/(assets\/[\w.-]+|[\w.-]+)$/.test(url.pathname) ? url.pathname.slice(1) : 'index.html'
  try { const body = await readFile(new URL(`../dist/${file}`, import.meta.url)); res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : 'text/html'); res.end(body) }
  catch { res.writeHead(404); res.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage({ viewport: { width: 390, height: 844 } })
  await page.goto(`http://127.0.0.1:${server.address().port}`)
  await page.getByRole('button', { name: 'Аналитика', exact: true }).click()
  await page.getByText('MOCK-SKU', { exact: false }).waitFor()
  assert.equal(await page.getByText('Предотвращённый финансовый риск', { exact: false }).count(), 0)
  await page.getByRole('button', { name: 'Далее', exact: true }).click()
  await page.getByText('Страница 2').waitFor()
  await page.waitForFunction(() => document.body.innerText.includes('MOCK-SKU'))
  assert.ok(query.includes('page=2'))
  empty = true
  await page.getByLabel('С', { exact: true }).fill('2025-01-01')
  await page.getByText('Нет данных', { exact: true }).first().waitFor()
  assert.ok(query.includes('start=2025-01-01'))
  assert.ok(query.includes('page=1'))
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
  console.log('Analytics mobile mock UI: metrics, period, pagination, empty state, finance visibility passed')
} finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
