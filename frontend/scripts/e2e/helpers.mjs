import assert from 'node:assert/strict'
import { spawn } from 'node:child_process'
import { createServer, request } from 'node:http'
import { mkdtemp, readFile, writeFile, rm } from 'node:fs/promises'
import { tmpdir } from 'node:os'
import { join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

export const root = fileURLToPath(new URL('../../../', import.meta.url))
export const python = process.env.E2E_PYTHON || join(root, 'backend', '.venv', process.platform === 'win32' ? 'Scripts/python.exe' : 'bin/python')
export const password = user => `e2e-${user}-password`

export async function until(check, description, timeout = 15000) {
  const end = Date.now() + timeout
  let last
  while (Date.now() < end) {
    try { last = await check(); if (last) return last } catch (error) { last = error.message }
    await new Promise(resolve => setTimeout(resolve, 100))
  }
  throw new Error(`Timed out: ${description}; last result: ${JSON.stringify(last)}`)
}

export async function environment() {
  if (process.env.E2E_CONTAINER === 'true') return (await import('./container.mjs')).containerEnvironment()
  const directory = await mkdtemp(join(tmpdir(), 'ozon-e2e-'))
  const reserve = createServer()
  await new Promise(resolve => reserve.listen(0, '127.0.0.1', resolve))
  const port = reserve.address().port
  await new Promise(resolve => reserve.close(resolve))
  const env = { ...process.env, APP_ENV: 'test', DATABASE_URL: `sqlite:///${join(directory, 'app.db').replaceAll('\\', '/')}`,
    OZON_MOCK_MODE: 'true', OZON_WEBHOOK_ENABLED: 'true', OZON_RECONCILIATION_ENABLED: 'false',
    UPLOAD_DIR: join(directory, 'uploads'), OZON_API_KEY: '', OZON_CLIENT_ID: '',
    TELEGRAM_BOT_TOKEN: '', TELEGRAM_BOT_USERNAME: '', TELEGRAM_WEBHOOK_SECRET: '',
    VAPID_PUBLIC_KEY: '', VAPID_PRIVATE_KEY: '', VAPID_SUBJECT: '', PYTHONUTF8: '1' }
  let logs = ''
  const backend = spawn(python, ['-m', 'tests.e2e_server', '--directory', directory, '--port', String(port)], { cwd: join(root, 'backend'), env, windowsHide: true })
  backend.stdout.on('data', chunk => { logs += chunk })
  backend.stderr.on('data', chunk => { logs += chunk })
  backend.on('error', error => { logs += error.message })
  let unavailable = false
  let eventsOffline = false
  let beforeClaim = null
  const server = createServer(async (req, res) => {
    if (req.url.startsWith('/api/')) {
      if (unavailable) { res.writeHead(503); res.end(); return }
      if (eventsOffline && req.url === '/api/orders/events') { res.writeHead(503); res.end(); return }
      if (beforeClaim && req.method === 'POST' && /^\/api\/orders\/\d+\/claim$/.test(req.url)) {
        const barrier = beforeClaim; beforeClaim = null
        try { await barrier() } catch { res.writeHead(500); res.end(); return }
      }
      const upstream = request({ hostname: '127.0.0.1', port, path: req.url, method: req.method, headers: req.headers }, response => {
        res.writeHead(response.statusCode, response.headers); response.pipe(res)
      })
      upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end() })
      res.on('close', () => upstream.destroy())
      req.pipe(upstream)
      return
    }
    const path = new URL(req.url, 'http://localhost').pathname
    const file = /^\/(assets\/[\w.-]+|[\w.-]+)$/.test(path) ? path.slice(1) : 'index.html'
    try {
      const body = await readFile(join(root, 'frontend/dist', file))
      res.setHeader('Content-Type', file.endsWith('.js') ? 'text/javascript' : file.endsWith('.css') ? 'text/css' : file.endsWith('.svg') ? 'image/svg+xml' : file.endsWith('.png') ? 'image/png' : file.endsWith('.webmanifest') ? 'application/manifest+json' : 'text/html')
      res.end(body)
    } catch { res.writeHead(404); res.end() }
  })
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const origin = `http://127.0.0.1:${server.address().port}`
  async function close() {
    server.closeAllConnections()
    await new Promise(resolve => server.close(resolve))
    if (backend.exitCode === null) {
      const exited = new Promise(resolve => backend.once('exit', resolve))
      backend.stdin.end('stop\n'); await exited
    }
    await rm(directory, { recursive: true, force: true, maxRetries: 10, retryDelay: 100 })
  }
  try {
    await until(async () => {
      if (backend.exitCode !== null) throw new Error(logs)
      return (await fetch(`${origin}/api/health/ready`)).ok
    }, 'migrated backend readiness', 30000)
    assert.equal((await (await fetch(`${origin}/api/health`)).json()).mock_mode, true)
  } catch (error) { await close(); throw new Error(`${error.message}\n${logs}`) }
  return { directory, origin, env, logs: () => logs, close,
    outage: value => { unavailable = value },
    disconnectEvents: value => { eventsOffline = value },
    raceBeforeClaim: barrier => { beforeClaim = barrier },
    changeOzon: changes => writeFile(join(directory, 'ozon-changes.json'), JSON.stringify(changes)),
    reconcile: async () => {
      await new Promise((resolve, reject) => {
        const child = spawn(python, ['-c', 'from app.main import app; from app.ozon import MockOzonClient; from app.ozon_reconciliation import reconcile; reconcile(app.state.engine, MockOzonClient(), app.state.settings, app.state.order_events)'], { cwd: join(root, 'backend'), env, windowsHide: true })
        child.stderr.on('data', chunk => { logs += chunk }); child.on('error', reject)
        child.on('exit', code => code === 0 ? resolve() : reject(new Error(`Reconciliation exit ${code}: ${logs}`)))
      })
    } }
}

export async function login(page, origin, user = 'admin') {
  await page.goto(origin)
  await page.getByLabel('Логин', { exact: true }).fill(user)
  await page.getByLabel('Пароль', { exact: true }).fill(password(user))
  await page.getByRole('button', { name: 'Войти', exact: true }).click()
  await page.getByRole('button', { name: 'Очередь', exact: true }).waitFor()
}

export async function api(page, path, method = 'GET', data, status = 200) {
  const me = await page.request.get('/api/auth/me')
  const csrf = me.ok() ? (await me.json()).csrf_token : ''
  const response = await page.request.fetch(`/api${path}`, { method, data, headers: { 'X-CSRF-Token': csrf } })
  assert.equal(response.status(), status, `${method} ${path}: ${await response.text()}`)
  return response.status() === 204 ? null : response.json()
}

export async function order(page, posting = 'MOCK-NEAR-DEADLINE') {
  const result = await api(page, `/orders?q=${posting}`)
  assert.equal(result.items.length, 1)
  return result.items[0]
}

export async function openOrder(page, posting = 'MOCK-NEAR-DEADLINE') {
  const row = await order(page, posting)
  await page.getByRole('button', { name: 'Очередь', exact: true }).click()
  await page.getByLabel('Номер отправления или QR payload').fill(`ozon-production:posting:${posting}`)
  await page.getByRole('button', { name: 'Открыть заказ', exact: true }).click()
  const card = page.locator(`#order-${row.id}`)
  await card.waitFor()
  await until(async () => (await page.locator('article[id^="order-"]').count()) === 1, 'exact order lookup')
  return card
}

export async function text(locator, expected, timeout) {
  await until(async () => (await locator.innerText()).includes(expected), `UI text ${expected}`, timeout)
}

export async function artifacts(contexts, directory, logs, error) {
  const output = resolve(root, 'frontend/e2e-results', directory)
  await import('node:fs/promises').then(fs => fs.mkdir(output, { recursive: true }))
  await writeFile(join(output, 'failure.txt'), `${error.stack}\n\nBackend:\n${logs}`)
  for (const [i, context] of contexts.entries()) {
    for (const [j, page] of context.pages().entries()) {
      await page.screenshot({ path: join(output, `${i}-${j}.png`), fullPage: true }).catch(() => {})
      await writeFile(join(output, `${i}-${j}.html`), await page.content()).catch(() => {})
    }
    await context.tracing.stop({ path: join(output, `${i}-trace.zip`) }).catch(() => {})
  }
}
