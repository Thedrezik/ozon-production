import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile } from 'node:fs/promises'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const user = { id: 1, display_name: 'Mock auditor', roles: ['MANAGER'], permissions: ['analytics.view', 'audit.view'], csrf_token: 'mock' }
let query = ''
let denied = false
const data = () => ({ total: query.includes('entity_id=missing') ? 0 : 26, items: query.includes('entity_id=missing') ? [] : [{ id: 1, user_id: 1, action: 'orders.updated', entity_type: 'orders', entity_id: '42', timestamp: '2026-10-02T00:00:00Z', old_value: { internal_status: 'QUEUED' }, new_value: { internal_status: 'IN_PRODUCTION' }, ip: '127.0.0.1', user_agent: 'browser' }] })
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  if (url.pathname.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json')
    if (url.pathname === '/api/orders/events') { res.setHeader('Content-Type', 'text/event-stream'); res.write(': mock\n\n'); return }
    if (url.pathname === '/api/audit') query = url.search
    res.end(JSON.stringify(url.pathname === '/api/auth/me' ? { ...user, permissions: denied ? ['analytics.view'] : user.permissions } : url.pathname === '/api/health' ? { mock_mode: true } : url.pathname === '/api/audit' ? data() : { as_of: '2026-01-02T00:00:00Z', critical: 0, blocked: 0, ready: 0, overdue: 0, manager_tasks: 0, attention: [], tasks: [], workload: [] })); return
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
  await page.getByRole('button', { name: 'Аудит', exact: true }).click()
  await page.getByText('orders.updated', { exact: true }).waitFor()
  await page.getByText('Изменения', { exact: true }).click()
  await page.getByText('IN_PRODUCTION', { exact: false }).waitFor()
  await page.getByRole('button', { name: 'Далее', exact: true }).click()
  await page.getByText('Всего: 26 · Страница 2', { exact: true }).waitFor()
  assert.ok(query.includes('offset=25'))
  for (const [label, val] of [['ID пользователя', '1'], ['Действие', 'orders.updated'], ['Тип объекта', 'orders'], ['ID объекта', '42'], ['С', '2026-01-01T00:00'], ['По', '2026-12-31T00:00']]) await page.getByLabel(label, { exact: true }).fill(val)
  await page.waitForFunction(() => !document.body.innerText.includes('Загрузка…'))
  assert.ok(query.includes('action=orders.updated') && query.includes('user_id=1') && query.includes('since=') && query.includes('until=') && query.includes('offset=0'))
  await page.getByLabel('ID объекта', { exact: true }).fill('missing')
  await page.getByText('Нет записей', { exact: true }).waitFor()
  assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth))
  denied = true
  await page.reload()
  await page.getByRole('button', { name: 'Очередь', exact: true }).waitFor()
  assert.equal(await page.getByRole('button', { name: 'Аудит', exact: true }).count(), 0)
  console.log('Audit mobile mock UI: filters, pagination, old/new detail, empty state and permission visibility passed')
} finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
