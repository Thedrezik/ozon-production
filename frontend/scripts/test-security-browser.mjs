import assert from 'node:assert/strict'
import { createServer } from 'node:http'
import { readFile, readdir } from 'node:fs/promises'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const payload = '<img src=x onerror="window.__xss=1"><script>window.__xss=1</script>'
const user = { id: 1, display_name: payload, roles: ['ADMIN'], permissions: ['audit.view', 'analytics.view'], csrf_token: 'mock' }
const caddy = await readFile(new URL('../../deployment/Caddyfile', import.meta.url), 'utf8')
const csp = caddy.match(/Content-Security-Policy "([^"]+)"/)[1]
assert.ok(!csp.includes("script-src 'self' 'unsafe-inline'"))
// Backend environment variables must not become public bundle values.
for (const file of await readdir(new URL('../dist/assets/', import.meta.url))) {
  const source = await readFile(new URL(`../dist/assets/${file}`, import.meta.url), 'utf8')
  assert.ok(!source.includes('security-backend-secret-sentinel'), `Secret leaked into ${file}`)
}
const server = createServer(async (req, res) => {
  const url = new URL(req.url, 'http://localhost')
  if (url.pathname.startsWith('/api/')) {
    res.setHeader('Content-Type', 'application/json')
    if (url.pathname === '/api/orders/events') { res.setHeader('Content-Type', 'text/event-stream'); res.write(': mock\n\n'); return }
    const audit = { total: 1, items: [{ id: 1, user_id: 1, action: 'security.test', entity_type: 'orders', entity_id: '1', timestamp: '2026-10-02T00:00:00Z', new_value: { label: payload }, old_value: null, ip: '127.0.0.1', user_agent: payload }] }
    const dashboard = { as_of: '2026-10-02T00:00:00Z', critical: 0, blocked: 0, ready: 0, overdue: 0, manager_tasks: 0, attention: [], tasks: [], workload: [] }
    res.end(JSON.stringify(url.pathname === '/api/auth/me' ? user : url.pathname === '/api/health' ? { mock_mode: true } : url.pathname === '/api/audit' ? audit : dashboard)); return
  }
  res.setHeader('Content-Security-Policy', csp)
  res.setHeader('X-Content-Type-Options', 'nosniff')
  const file = /^\/(assets\/[\w.-]+|[\w.-]+)$/.test(url.pathname) ? url.pathname.slice(1) : 'index.html'
  try {
    const body = await readFile(new URL(`../dist/${file}`, import.meta.url))
    res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.png') ? 'image/png' : file.endsWith('.svg') ? 'image/svg+xml' : 'text/html')
    res.end(body)
  } catch { res.writeHead(404); res.end() }
})
await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
const browser = await chromium.launch({ channel: 'msedge', headless: true })
try {
  const page = await browser.newPage()
  let dialogs = 0
  page.on('dialog', async dialog => { dialogs++; await dialog.dismiss() })
  await page.goto(`http://127.0.0.1:${server.address().port}`)
  await page.getByRole('button', { name: 'Аудит', exact: true }).click()
  await page.getByText('security.test', { exact: true }).waitFor()
  await page.getByText('Изменения', { exact: true }).click()
  await page.getByText(payload, { exact: true }).waitFor()
  assert.equal(await page.locator('article img, article script').count(), 0)
  assert.equal(await page.evaluate(() => window.__xss), undefined)
  // Verify deployed CSP blocks inline scripts even outside React's text escaping.
  await page.evaluate(() => { const element = document.createElement('script'); element.textContent = 'window.__xss=1'; document.body.append(element) })
  assert.equal(await page.evaluate(() => window.__xss), undefined)
  assert.equal(dialogs, 0)
  console.log('Security browser: actual React text escaping, CSP inline-script rejection, PWA build loading and bundle sentinel scan passed')
} finally { await browser.close(); server.closeAllConnections(); await new Promise(resolve => server.close(resolve)) }
