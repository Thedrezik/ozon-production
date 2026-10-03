import assert from 'node:assert/strict'
import { join } from 'node:path'
import { readFile, mkdir } from 'node:fs/promises'
import { environment, login, api, order, openOrder, until, text, artifacts } from './helpers.mjs'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const browser = await chromium.launch({ ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : process.platform === 'win32' ? { channel: 'msedge' } : {}), headless: true,
  ...(process.env.E2E_CONTAINER === 'true' ? { args: ['--ignore-certificate-errors'] } : {}) })

const posting = '0210000001-0001-1'
async function webhook(page, kind = 'TYPE_NEW_POSTING') {
  const payload = kind === 'TYPE_NEW_POSTING' ? { message_type: kind, posting_number: posting, seller_id: 42, warehouse_id: 123,
    products: [{ sku: 1904686181, quantity: 1 }], in_process_at: new Date().toISOString(), shipment_date: new Date(Date.now() + 6 * 3600000).toISOString() }
    : { message_type: kind, posting_number: posting, seller_id: 42, warehouse_id: 123,
      new_state: kind === 'TYPE_POSTING_CANCELLED' ? 'cancelled' : 'delivering', changed_state_date: new Date().toISOString(),
      ...(kind === 'TYPE_POSTING_CANCELLED' ? { old_state: 'awaiting_packaging', products: [{ sku: 1904686181, quantity: 1 }], reason: { id: 1, message: 'Synthetic cancellation' } } : {}) }
  const response = await page.request.post('/api/ozon/webhook', { data: payload })
  assert.equal(response.status(), 200)
  return payload
}
async function incoming(admin, env) {
  await env.changeOzon({ in_process_at: new Date().toISOString(), shipment_date: new Date(Date.now() + 6 * 3600000).toISOString(),
    tariffication: { current_tariff_type: 'discount', current_tariff_charge: '120', current_tariff_charge_currency_code: 'RUB', next_tariff_type: 'commission',
      next_tariff_charge: '50', next_tariff_charge_currency_code: 'RUB', next_tariff_starts_at: new Date(Date.now() + 3600000).toISOString() }, tariffication_steps: [] })
  await webhook(admin)
  return until(async () => (await api(admin, `/orders?q=${posting}`)).items[0], 'automatic webhook order discovery', 20000)
}
async function telegram(env) {
  try { return (await readFile(join(env.directory, 'telegram.jsonl'), 'utf8')).trim().split('\n').filter(Boolean).map(line => JSON.parse(line)) }
  catch { return [] }
}
async function screenshot(page, label) {
  const directory = new URL('../../e2e-results/core-visuals/', import.meta.url)
  await mkdir(directory, { recursive: true })
  await page.screenshot({ path: join(directory.pathname.replace(/^\/(\w:)/, '$1'), `${label}-${page.viewportSize().width}.png`), fullPage: true })
}
const scenarios = {
  async 'core production workflow'({ admin, worker, manager, env }) {
    await login(admin, env.origin)
    const target = await incoming(admin, env)
    assert.equal(Number(target.tariff.delta_to_next_tariff), 170)
    await admin.getByRole('button', { name: 'Лента заказов', exact: true }).click()
    await text(admin.locator('main'), posting)
    await text(admin.locator('main'), 'TUMBA-WHITE')
    await text(admin.locator('main'), '12\u00a0990,10 ₽')
    await screenshot(admin, 'feed')
    await login(manager, env.origin, 'manager')
    await manager.getByRole('button', { name: 'Проблемы (0)', exact: true }).click()
    await login(worker, env.origin, 'worker')
    const card = await openOrder(worker, posting)
    await card.getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await text(card, 'В работе')
    assert.equal((await order(admin, posting)).internal_status, 'IN_PRODUCTION')
    await card.locator('summary').filter({ hasText: 'История и комментарии' }).click()
    await card.getByLabel('Комментарий', { exact: true }).fill('E2E: начал изготовление')
    await card.getByRole('button', { name: 'Добавить комментарий', exact: true }).click()
    await text(card, 'E2E: начал изготовление')
    await card.getByRole('button', { name: 'Есть проблема', exact: true }).click()
    await card.getByLabel('Что случилось').fill('E2E: нужна белая кромка')
    const before = await manager.evaluate(() => window.__e2eOrderEvents.length)
    await card.getByRole('button', { name: 'Сообщить о проблеме', exact: true }).click()
    await text(manager.locator('main'), 'E2E: нужна белая кромка', 20000)
    await manager.getByRole('button', { name: 'Проблемы (1)', exact: true }).waitFor()
    await until(() => manager.evaluate(n => window.__e2eOrderEvents.length > n, before), 'SSE problem broadcast')
    await until(async () => (await telegram(env)).length === 1, 'Telegram problem delivery', 25000)
    await screenshot(worker, 'problem')
    await card.getByRole('button', { name: 'Решена', exact: true }).click()
    await card.getByLabel('Комментарий к решению').fill('Кромка получена')
    await card.getByRole('button', { name: 'Сохранить решение', exact: true }).click()
    await text(card, 'В работе')
    await manager.getByRole('button', { name: 'Проблемы (0)', exact: true }).waitFor()
    for (const [label, status] of [['Произведено', 'PRODUCED'], ['Упаковано', 'READY_TO_SHIP']]) {
      await card.getByRole('button', { name: label, exact: true }).click()
      await until(async () => (await order(admin, posting)).internal_status === status, status)
    }
    await api(worker, `/orders/${target.id}/status`, 'POST', { status: 'HANDED_TO_SHIPPING' }, 409)
    await env.changeOzon({ status: 'delivering', delivering_date: new Date().toISOString() })
    const event = await webhook(admin, 'TYPE_STATE_CHANGED')
    await until(async () => (await api(admin, `/orders?order_id=${target.id}`)).items[0].internal_status === 'HANDED_TO_SHIPPING', 'external shipment', 20000)
    await admin.request.post('/api/ozon/webhook', { data: event })
    const timeline = await api(worker, `/orders/${target.id}/timeline`)
    assert.ok(timeline.items.some(row => row.body === 'Заказ получен'))
    assert.ok(timeline.items.some(row => row.body.includes('Кромка получена') && row.author === 'E2E worker'))
    assert.ok(timeline.items.some(row => row.body.includes('Отгружен')))
    const problem = (await api(admin, `/blockers?order_id=${target.id}`)).items[0]
    assert.equal(problem.status, 'RESOLVED')
    assert.ok(problem.resolved_by_user_id && problem.resolved_at)
    assert.equal((await telegram(env)).length, 1, 'no regular status Telegram spam')
    await admin.getByRole('button', { name: 'Главная', exact: true }).click()
    await text(admin.locator('main'), 'Что делать сейчас')
    assert.ok((await api(admin, '/money-at-risk')).total)
    await screenshot(admin, 'home')
    assert.equal(await worker.locator('body').evaluate(el => el.scrollWidth > window.innerWidth), false)
  },
  async 'cancellation after production started'({ admin, worker, env }) {
    await login(admin, env.origin)
    const target = await incoming(admin, env)
    await login(worker, env.origin, 'worker')
    const card = await openOrder(worker, posting)
    await card.getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await text(card, 'В работе')
    await env.changeOzon({ status: worker.viewportSize().width < 500 ? 'cancelled_from_split_pending' : 'cancelled' })
    const event = await webhook(admin, 'TYPE_POSTING_CANCELLED')
    await text(card, 'КРИТИЧЕСКАЯ ОТМЕНА OZON', 20000)
    await text(admin.locator('main'), 'КРИТИЧЕСКАЯ ОТМЕНА OZON', 20000)
    assert.equal(await card.getByRole('button', { name: 'Произведено', exact: true }).count(), 0)
    await api(worker, `/orders/${target.id}/status`, 'POST', { status: 'PRODUCED' }, 409)
    await admin.request.post('/api/ozon/webhook', { data: event })
    await until(async () => (await telegram(env)).length === 1, 'one Telegram cancellation alert', 25000)
    const alert = (await telegram(env))[0].text
    assert.ok(alert.includes(posting) && alert.includes('TUMBA-WHITE') && alert.includes('IN_PRODUCTION') && alert.includes('E2E worker'))
    await admin.getByRole('button', { name: 'Лента заказов', exact: true }).click()
    await text(admin.locator(`#order-${target.id}`), 'ОТМЕНА')
    await screenshot(admin, 'critical-cancellation')
    assert.equal((await telegram(env)).length, 1)
    const cancelled = await openOrder(admin, posting)
    admin.once('dialog', dialog => dialog.accept())
    await cancelled.getByRole('button', { name: 'Закрыть производство', exact: true }).click()
    await until(async () => (await api(admin, `/orders?order_id=${target.id}`)).items[0].internal_status === 'CANCELLED', 'admin cancellation disposition')
    assert.equal((await api(admin, '/notifications')).items.filter(row => row.type === 'ORDER_CANCELLED').length, 1, 'closing production does not repeat alert')
    assert.equal((await api(admin, '/dashboard')).cancelled_after_start.length, 0)
  },
  async 'cancellation before production'({ admin, worker, env }) {
    await login(admin, env.origin)
    const target = await incoming(admin, env)
    await env.changeOzon({ status: admin.viewportSize().width < 500 ? 'cancelled_from_split_pending' : 'cancelled' })
    const event = await webhook(admin, 'TYPE_POSTING_CANCELLED')
    await until(async () => (await api(admin, `/orders?order_id=${target.id}`)).items[0].cancelled, 'early cancellation', 20000)
    await admin.request.post('/api/ozon/webhook', { data: event })
    assert.equal((await api(admin, `/orders?q=${posting}`)).total, 0)
    assert.equal((await api(admin, '/dashboard')).cancelled_after_start.length, 0)
    await login(worker, env.origin, 'worker')
    await worker.getByRole('button', { name: 'Лента заказов', exact: true }).click()
    const card = worker.locator(`#order-${target.id}`)
    await text(card, 'Отменён Ozon')
    assert.equal(await card.getByRole('button', { name: 'Взять в работу', exact: true }).count(), 0)
    assert.equal((await telegram(env)).length, 0)
    assert.equal((await api(admin, '/notifications')).items.filter(row => row.type === 'ORDER_CANCELLED').length, 0)
  },
  async 'auth RBAC optional routes and request budget'({ admin, worker, env }) {
    await login(admin, env.origin)
    await login(worker, env.origin, 'worker')
    assert.equal(await worker.getByRole('button', { name: 'Аудит', exact: true }).count(), 0)
    for (const path of ['/audit', '/users', '/money-at-risk']) await api(worker, path, 'GET', undefined, 403)
    for (const path of ['/manager-tasks', '/procurement', '/analytics', '/push/config', '/files/photos', '/notifications/preferences']) await api(admin, path, 'GET', undefined, 404)
    assert.deepEqual((await api(admin, '/features')).optional, [])
    const paths = []
    worker.on('request', req => { const url = new URL(req.url()); if (url.pathname.startsWith('/api/')) paths.push(url.pathname) })
    await worker.getByRole('button', { name: 'Заказы', exact: true }).click()
    await text(worker.locator('main'), 'MOCK-NORMAL')
    assert.equal(paths.filter(path => path === '/api/orders').length, 1, 'one queue request on navigation')
    assert.ok(!paths.some(path => /manager-tasks|procurement|analytics|photos|preferences|push/.test(path)))
    paths.length = 0
    await worker.getByRole('button', { name: 'Главная', exact: true }).click()
    await text(worker.locator('main'), 'Что делать сейчас')
    await until(() => paths.includes('/api/dashboard'), 'home request')
    assert.equal(paths.filter(path => path === '/api/dashboard').length, 1)
    paths.length = 0
    await worker.getByRole('button', { name: 'Проблемы (0)', exact: true }).click()
    await until(() => paths.includes('/api/orders'), 'problems request')
    assert.equal(paths.filter(path => path === '/api/orders').length, 1)
    console.log('CORE navigation HTTP: Home 1, Queue 1, Problems 1; shared summary/sync-state unchanged')
    await worker.getByRole('button', { name: 'Лента заказов', exact: true }).click()
    await text(worker.locator('main'), 'MOCK-CANCELLED')
    const rows = (await api(worker, '/orders/feed?limit=100')).items
    assert.deepEqual(rows.map(row => row.received_at), rows.map(row => row.received_at).sort())
    await worker.locator('.secondary-nav summary').click()
    await worker.getByRole('button', { name: 'Выйти', exact: true }).click()
    await worker.getByRole('button', { name: 'Войти', exact: true }).waitFor()
    assert.equal(await worker.evaluate(() => sessionStorage.getItem('production.queue.v1')), null)
    await api(worker, '/orders', 'GET', undefined, 401)
  },
  async 'PWA offline and SSE fallback'({ admin, worker, contexts, env }) {
    await login(admin, env.origin)
    await login(worker, env.origin, 'worker')
    const card = await openOrder(worker, 'MOCK-NORMAL')
    await worker.evaluate(() => navigator.serviceWorker.ready)
    await until(() => worker.evaluate(() => Boolean(navigator.serviceWorker.controller)), 'service worker controller')
    await contexts[1].setOffline(true)
    await worker.reload()
    await text(worker.locator('main'), 'OFFLINE')
    assert.equal(await worker.getByRole('button', { name: 'Взять в работу', exact: true }).count(), 0)
    await contexts[1].setOffline(false)
    await worker.getByRole('button', { name: 'Заказы', exact: true }).waitFor({ timeout: 20000 })
    const errorsBefore = await worker.evaluate(() => window.__e2eSseErrors)
    await env.disconnectEvents(true)
    await until(() => worker.evaluate(n => window.__e2eSseErrors > n, errorsBefore), 'actual SSE disconnect', 30000)
    const row = await order(admin, 'MOCK-NORMAL')
    await api(admin, `/orders/${row.id}/claim`, 'POST')
    await worker.evaluate(() => window.dispatchEvent(new Event('focus')))
    await text(worker.locator('main'), 'E2E Admin', 20000)
    await api(admin, `/orders/${row.id}/status`, 'POST', { status: 'PRODUCED' })
    await env.disconnectEvents(false)
    await text(card, 'Произведён', 20000)
    const cached = await worker.evaluate(async () => (await Promise.all((await caches.keys()).map(async key => (await (await caches.open(key)).keys()).map(request => request.url)))).flat())
    assert.ok(cached.every(url => !new URL(url).pathname.startsWith('/api/')))
  },
  async 'claim conflict and reconciliation recovery'({ admin, worker, env }) {
    await login(admin, env.origin)
    await login(worker, env.origin, 'worker')
    const card = await openOrder(worker, 'MOCK-NORMAL')
    const row = await order(admin, 'MOCK-NORMAL')
    await env.raceBeforeClaim(async () => { await api(admin, `/orders/${row.id}/claim`, 'POST') })
    await card.getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await text(worker.locator('main'), 'Заказ изменился или переход уже недоступен')
    assert.equal((await order(admin, 'MOCK-NORMAL')).internal_status, 'IN_PRODUCTION')
    await env.reconcile()
    assert.ok((await api(admin, `/orders?q=${posting}`)).items.length)
    assert.equal((await api(admin, '/ozon/sync-state')).status, 'SUCCESS')
  },
}

let passed = 0
let failed = 0
try {
  for (const [viewportName, viewport] of Object.entries({ desktop: { width: 1440, height: 1000 }, mobile: { width: 390, height: 844 } })) {
    for (const [name, scenario] of Object.entries(scenarios)) {
      if (process.env.E2E_FILTER && !`${viewportName}: ${name}`.includes(process.env.E2E_FILTER)) continue
      const env = await environment()
      const contexts = []
      const errors = []
      try {
        for (let i = 0; i < 3; i++) {
          const context = await browser.newContext({ viewport, baseURL: env.origin, serviceWorkers: 'allow', timezoneId: 'Europe/Moscow',
            ...(process.env.E2E_CONTAINER === 'true' ? { ignoreHTTPSErrors: true } : {}),
            ...(viewportName === 'mobile' ? { isMobile: true, hasTouch: true } : {}) })
          await context.tracing.start({ screenshots: true, snapshots: true, sources: true })
          await context.addInitScript(() => {
            window.__e2eOrderEvents = []
            window.__e2eSseErrors = 0
            const NativeEventSource = window.EventSource
            window.EventSource = class extends NativeEventSource {
              constructor(...args) {
                super(...args)
                this.addEventListener('orders', event => window.__e2eOrderEvents.push(event.data))
                this.addEventListener('ready', event => window.__e2eOrderEvents.push(event.data))
                this.addEventListener('error', () => window.__e2eSseErrors++)
              }
            }
          })
          contexts.push(context)
        }
        const pages = await Promise.all(contexts.map(context => context.newPage()))
        for (const page of pages) { page.setDefaultTimeout(15000); page.on('pageerror', error => errors.push(error.message)) }
        await scenario({ admin: pages[0], worker: pages[1], manager: pages[2], contexts, env })
        assert.deepEqual(errors, [], 'uncaught browser errors')
        await env.verifyDeployment?.()
        passed++
        console.log(`PASS ${viewportName}: ${name}`)
      } catch (error) {
        failed++
        console.error(`FAIL ${viewportName}: ${name}\n${error.stack}`)
        await env.captureLogs?.().catch(() => {})
        await artifacts(contexts, `${viewportName}-${name.replaceAll(' ', '-')}`, env.logs(), error)
      } finally {
        for (const context of contexts) { await context.tracing.stop().catch(() => {}); await context.close() }
        await env.close()
      }
    }
  }
} finally { await browser.close() }
console.log(`E2E: ${passed} passed, ${failed} failed; desktop 1440x1000, mobile 390x844; retries: 0`)
if (failed) process.exitCode = 1
