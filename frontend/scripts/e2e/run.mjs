import assert from 'node:assert/strict'
import { join } from 'node:path'
import { environment, login, api, order, openOrder, until, text, artifacts } from './helpers.mjs'
const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const browser = await chromium.launch({ ...(process.env.E2E_BROWSER_CHANNEL ? { channel: process.env.E2E_BROWSER_CHANNEL } : process.platform === 'win32' ? { channel: 'msedge' } : {}), headless: true })

const scenarios = {
  async 'production workflow'({ admin, worker, manager, env }) {
    await login(admin, env.origin)
    await text(admin.locator('main'), 'Деньги под угрозой')
    const initial = await api(admin, '/dashboard')
    const risk = await api(admin, '/money-at-risk')
    assert.equal(risk.total, '470.00')
    const target = await order(admin)
    assert.ok(target.priority.reasons.length)
    const bucket = risk.buckets.find(row => row.order_count > 0)
    const drill = await api(admin, `/money-at-risk/orders?bucket=${bucket.key}`)
    assert.ok(drill.items.some(row => row.id === target.id))
    await admin.getByRole('button', { name: 'Деньги под угрозой', exact: true }).click()
    await admin.getByRole('button').filter({ hasText: bucket.label }).click()
    await text(admin.locator('main'), `Заказ ${target.posting_number}`)
    await login(manager, env.origin, 'manager')
    await manager.getByRole('button', { name: 'Задачи руководителя', exact: true }).click()
    await text(manager.locator('main'), 'Нет задач')
    await login(worker, env.origin, 'worker')
    const workerCard = await openOrder(worker)
    await workerCard.getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await workerCard.getByRole('button', { name: 'Начать производство', exact: true }).click()
    await text(workerCard, 'В производстве')
    await workerCard.getByRole('button', { name: 'Проблема', exact: true }).click()
    const eventsBefore = await manager.evaluate(() => window.__e2eOrderEvents.length)
    await workerCard.getByLabel('Что случилось').fill('E2E: нужна белая кромка')
    await workerCard.getByRole('button', { name: 'Сообщить о проблеме', exact: true }).click()
    await text(workerCard, 'Заблокирован')
    // The other context stays on its screen: event/fallback must refresh it.
    await text(manager.locator('article'), 'E2E: нужна белая кромка')
    await until(() => manager.evaluate(before => window.__e2eOrderEvents.slice(before).length > 0, eventsBefore), 'real SSE event in manager session')
    const tasks = await api(manager, '/manager-tasks?source_type=BLOCKER')
    assert.equal(tasks.total, 1)
    const task = tasks.items[0]
    const blocker = (await api(admin, `/blockers?order_id=${target.id}`)).items[0]
    assert.equal(task.source_id, blocker.id)
    assert.equal((await api(admin, '/dashboard')).blocked, initial.blocked + 1)
    assert.equal((await api(admin, '/money-at-risk')).categories.BLOCKED_RISK, '470.00')
    await manager.locator('article').getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await until(async () => (await api(manager, `/manager-tasks?task_id=${task.id}`)).items[0].status === 'IN_PROGRESS', 'manager claims task')
    await api(manager, `/manager-tasks/${task.id}`, 'PATCH', { status: 'RESOLVED' }, 409)
    await manager.getByRole('button', { name: 'Уведомления', exact: true }).click()
    const notice = manager.locator('article').filter({ hasText: 'E2E: нужна белая кромка' })
    await notice.waitFor()
    await notice.getByRole('button', { name: 'Прочитано', exact: true }).click()
    await until(async () => (await api(manager, '/notifications')).items.find(row => row.body === 'E2E: нужна белая кромка')?.read_at, 'notification read receipt')
    const adminCard = await openOrder(admin)
    const prompts = ['Белая кромка E2E', '2', 'м']
    const answer = dialog => dialog.accept(prompts.shift())
    admin.on('dialog', answer)
    await adminCard.getByRole('button', { name: 'Создать закупку', exact: true }).click()
    await until(async () => (await api(admin, '/procurement')).items.some(row => row.material_name === 'Белая кромка E2E'), 'procurement created by UI')
    admin.off('dialog', answer)
    const purchase = (await api(admin, '/procurement')).items[0]
    assert.deepEqual(purchase.blocker_ids, [blocker.id])
    assert.deepEqual(purchase.order_ids, [target.id])
    await manager.getByRole('button', { name: 'Закупки', exact: true }).click()
    const purchaseCard = manager.locator('article').filter({ hasText: 'Белая кромка E2E' })
    for (const [label, status] of [['Заказана', 'ORDERED'], ['Куплена', 'PURCHASED'], ['Доставлена', 'DELIVERED']]) {
      await purchaseCard.getByRole('button', { name: label, exact: true }).click()
      await until(async () => (await api(admin, `/procurement/${purchase.id}`)).status === status, `procurement ${status}`)
    }
    assert.deepEqual((await api(admin, `/procurement/${purchase.id}/history`)).items.map(row => row.new_status), ['NEW', 'ORDERED', 'PURCHASED', 'DELIVERED'])
    // Delivery does not resolve the production blocker without verification.
    assert.equal((await order(admin)).internal_status, 'BLOCKED')
    await adminCard.getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await until(async () => (await api(admin, `/blockers?order_id=${target.id}`)).items[0].status === 'IN_PROGRESS', 'blocker in progress')
    await adminCard.getByRole('button', { name: 'Решить', exact: true }).click()
    await text(workerCard, 'В производстве')
    assert.equal((await api(manager, `/manager-tasks?task_id=${task.id}`)).items[0].status, 'RESOLVED')
    assert.equal((await order(admin)).priority.blocked, false)
    assert.match((await api(admin, '/money-at-risk')).categories.BLOCKED_RISK, /^0(?:\.0+)?$/)
    for (const [label, status] of [['Произведено', 'PRODUCED'], ['Проверка качества', 'QUALITY_CHECK'], ['На упаковку', 'PACKING'], ['Готово', 'READY_TO_SHIP']]) {
      await workerCard.getByRole('button', { name: label, exact: true }).click()
      await until(async () => (await order(admin)).internal_status === status, `production ${status}`)
    }
    const current = await order(admin)
    assert.equal(current.ozon_status, target.ozon_status)
    assert.ok(current.production_started_at && current.production_completed_at && current.ready_to_ship_at)
    const history = await api(admin, `/orders/${target.id}/history`)
    assert.deepEqual(history.slice(-7).map(row => row.new_status), ['IN_PRODUCTION', 'BLOCKED', 'IN_PRODUCTION', 'PRODUCED', 'QUALITY_CHECK', 'PACKING', 'READY_TO_SHIP'])
    await adminCard.locator('summary').filter({ hasText: 'История заказа' }).click()
    await text(adminCard, 'Готов к отгрузке')
    const timeline = await api(admin, `/orders/${target.id}/timeline`)
    assert.ok(timeline.items.some(row => row.body.includes('RESOLVED')))
    const finalDashboard = await api(admin, '/dashboard')
    assert.equal(finalDashboard.ready, initial.ready + 1)
    assert.equal(finalDashboard.blocked, initial.blocked)
    // READY still has shipment tariff exposure until external shipment.
    assert.equal((await api(admin, '/money-at-risk')).total, '470.00')
    await admin.getByRole('button', { name: 'Главная', exact: true }).click()
    await text(admin.locator('main'), 'Готовы к отгрузке')
    await admin.getByRole('button', { name: 'Аудит', exact: true }).click()
    await admin.getByLabel('Действие', { exact: true }).fill('blocker.updated')
    await text(admin.locator('main'), 'blocker.updated')
    assert.ok((await api(admin, '/audit?action=blocker.updated')).total >= 2)
    await admin.getByRole('button', { name: 'Аналитика', exact: true }).click()
    await text(admin.locator('main'), 'Throughput за период')
    // Cover the organization date even when UTC/Moscow cross midnight mid-test.
    const [start, end] = [-86400000, 86400000].map(delta => new Date(Date.now() + delta).toISOString().slice(0, 10))
    const analytics = await api(admin, `/analytics?start=${start}&end=${end}`)
    assert.ok(analytics.throughput.ready >= 1)
  },

  async 'auth and RBAC'({ admin, worker, env }) {
    await login(admin, env.origin)
    await admin.getByRole('button', { name: 'Выйти', exact: true }).click()
    await admin.getByRole('button', { name: 'Войти', exact: true }).waitFor()
    await api(admin, '/orders', 'GET', undefined, 401)
    await login(worker, env.origin, 'worker')
    for (const name of ['Задачи руководителя', 'Закупки', 'Пользователи', 'Аудит', 'Аналитика', 'Ozon', 'Деньги под угрозой'])
      assert.equal(await worker.getByRole('button', { name, exact: true }).count(), 0, name)
    for (const path of ['/users', '/manager-tasks', '/procurement', '/audit', '/analytics', '/money-at-risk', '/dashboard'])
      await api(worker, path, 'GET', undefined, 403)
    const row = await order(worker, 'MOCK-NORMAL')
    for (const [path, method, data] of [[`/orders/${row.id}/assignment`, 'PUT', { user_id: null }], ['/orders/bulk', 'POST', { order_ids: [row.id], action: 'status', status: 'IN_PRODUCTION' }], ['/users', 'POST', { username: 'intruder', display_name: 'Intruder', password: 'e2e-intruder-password', roles: ['ADMIN'] }]])
      await api(worker, path, method, data, 403)
    assert.equal((await order(worker, 'MOCK-NORMAL')).internal_status, 'QUEUED')
    await worker.getByRole('button', { name: 'Выйти', exact: true }).click()
    await api(worker, '/auth/me', 'GET', undefined, 401)
    assert.equal(await worker.evaluate(() => sessionStorage.getItem('production.queue.v1')), null)
  },

  async 'queue bulk comments files and manual QR'({ admin, env }) {
    await login(admin, env.origin)
    await admin.getByRole('button', { name: 'Очередь', exact: true }).click()
    await admin.getByLabel('Поиск заказов').fill('MOCK-NORMAL')
    await until(async () => await admin.locator('article[id^="order-"]').count() === 1, 'queue search')
    await admin.locator('select').first().selectOption('IN_PRODUCTION')
    await text(admin.locator('main'), 'Заказов нет.')
    await admin.locator('select').first().selectOption('QUEUED')
    await admin.getByLabel('Поиск заказов').fill('MOCK-')
    await until(async () => await admin.locator('article[id^="order-"]').count() === 2, 'combined filter')
    await admin.getByLabel('Выбрать страницу', { exact: true }).check()
    admin.once('dialog', dialog => dialog.accept())
    await admin.getByLabel('Массовое назначение').selectOption({ label: 'E2E worker' })
    await until(async () => (await api(admin, '/orders?status=QUEUED')).items.every(row => row.assigned_user?.display_name === 'E2E worker'), 'bulk assignment')
    assert.equal((await api(admin, '/audit?action=order.bulk_assign')).total, 1)
    const card = await openOrder(admin, 'MOCK-NORMAL')
    await card.locator('summary').filter({ hasText: 'История заказа' }).click()
    await card.getByLabel('Комментарий', { exact: true }).fill('E2E comment from real UI')
    await card.getByRole('button', { name: 'Добавить комментарий', exact: true }).click()
    await text(card, 'E2E comment from real UI')
    const photoDetails = card.locator('details').filter({ has: admin.locator('summary', { hasText: 'Фотографии' }) }).first()
    await photoDetails.locator('summary').click()
    await photoDetails.locator('input[type=file]').setInputFiles(join(env.directory, 'photo.png'))
    await photoDetails.getByRole('img', { name: /^Фото / }).waitFor()
    const row = await order(admin, 'MOCK-NORMAL')
    const photo = (await api(admin, `/files/orders/${row.id}/photos`)).items[0]
    assert.equal(photo.mime_type, 'image/jpeg')
    assert.equal(photo.width, 64)
    assert.equal(photo.height, 48)
    assert.equal((await admin.request.get(photo.url)).status(), 200)
    await card.locator('summary').filter({ hasText: 'QR заказа' }).click()
    const qr = card.getByRole('img', { name: 'QR для открытия заказа' })
    await until(() => qr.evaluate(img => img.complete && img.naturalWidth > 0), 'QR PNG')
    await admin.getByLabel('Номер отправления или QR payload').fill('missing-code')
    await admin.getByRole('button', { name: 'Открыть заказ', exact: true }).click()
    await text(admin.locator('main'), 'Заказ с этим кодом не найден')
    assert.ok(await admin.evaluate(() => document.documentElement.scrollWidth <= innerWidth))
  },

  async 'offline PWA and live fallback'({ admin, worker, env, contexts }) {
    await login(admin, env.origin)
    await login(worker, env.origin, 'worker')
    await openOrder(worker, 'MOCK-NORMAL')
    await worker.evaluate(async () => { await navigator.serviceWorker.ready; if (!navigator.serviceWorker.controller) await new Promise(resolve => navigator.serviceWorker.addEventListener('controllerchange', resolve, { once: true })) })
    const snapshot = await worker.evaluate(() => sessionStorage.getItem('production.queue.v1'))
    assert.ok(snapshot)
    assert.ok(!snapshot.includes('csrf_token') && !snapshot.includes('tariff_steps'))
    await contexts[1].setOffline(true)
    await worker.reload()
    await text(worker.locator('main'), 'OFFLINE · Нет связи с сервером')
    await text(worker.locator('main'), 'MOCK-NORMAL')
    await text(worker.locator('main'), 'Данные могут быть устаревшими')
    assert.equal(await worker.getByRole('button', { name: 'Взять в работу', exact: true }).count(), 0)
    const target = await order(admin, 'MOCK-NORMAL')
    await api(admin, `/orders/${target.id}/status`, 'POST', { status: 'IN_PRODUCTION' })
    await contexts[1].setOffline(false)
    // Recovery has an existing 30-second polling fallback if online fires while
    // the offline reload is still mounting. Bound the wait to that contract.
    await text(worker.locator('main'), 'Очередь загружена с сервера', 45000)
    await text(worker.locator(`#order-${target.id}`), 'В производстве')
    assert.equal((await api(admin, `/orders/${target.id}/history`)).filter(row => row.new_status === 'IN_PRODUCTION').length, 1)
    // Explicitly drop SSE: focus reconciliation must still load the real API.
    env.disconnectEvents(true)
    await worker.reload()
    await worker.getByRole('button', { name: 'Очередь', exact: true }).click()
    await text(worker.locator(`#order-${target.id}`), 'В производстве')
    await api(admin, `/orders/${target.id}/status`, 'POST', { status: 'PRODUCED' })
    await worker.evaluate(() => window.dispatchEvent(new Event('focus')))
    await text(worker.locator(`#order-${target.id}`), 'Произведён')
    assert.deepEqual(await worker.evaluate(() => window.__e2eOrderEvents), [])
    const cached = await worker.evaluate(async () => { const keys = await caches.keys(); return (await Promise.all(keys.map(async key => (await (await caches.open(key)).keys()).map(req => req.url)))).flat() })
    assert.ok(cached.length > 0)
    assert.ok(cached.every(url => !new URL(url).pathname.startsWith('/api/')))
  },

  async 'mock import reconciliation change and cancellation'({ admin, env }) {
    await login(admin, env.origin)
    const window = { since: '2026-10-01T00:00:00Z', to: '2026-10-04T00:00:00Z' }
    const first = await api(admin, '/ozon/fbs/import', 'POST', window)
    assert.ok(first.changed > 0)
    const second = await api(admin, '/ozon/fbs/import', 'POST', window)
    assert.equal(second.changed, 0)
    const posting = '0210000001-0001-1'
    const target = await order(admin, posting)
    await api(admin, `/orders/${target.id}/status`, 'POST', { status: 'QUEUED' })
    await api(admin, `/orders/${target.id}/status`, 'POST', { status: 'IN_PRODUCTION' })
    const card = await openOrder(admin, posting)
    const deadline = '2026-10-04T18:00:00Z'
    await env.changeOzon({ shipment_date: deadline, shipment_date_without_delay: deadline })
    const event = { message_type: 'TYPE_CUTOFF_DATE_CHANGED', posting_number: posting, seller_id: 1, warehouse_id: 1, old_cutoff_date: target.shipment_deadline, new_cutoff_date: deadline }
    await api(admin, '/ozon/webhook', 'POST', event)
    await until(async () => (await order(admin, posting)).shipment_deadline.startsWith('2026-10-04T18:00:00'), 'webhook deadline update', 20000)
    await env.changeOzon({ status: 'cancelled', shipment_date: deadline, shipment_date_without_delay: deadline })
    const cancelled = { message_type: 'TYPE_STATE_CHANGED', posting_number: posting, seller_id: 1, warehouse_id: 1, new_state: 'cancelled', changed_state_date: '2026-10-02T14:00:00Z' }
    await api(admin, '/ozon/webhook', 'POST', cancelled)
    await api(admin, '/ozon/webhook', 'POST', cancelled)
    await until(async () => (await api(admin, '/orders?ozon_status=cancelled')).items.some(row => row.id === target.id), 'webhook cancellation', 20000)
    await text(card, 'Заказ вышел из производственной очереди')
    const archive = (await api(admin, `/orders?order_id=${target.id}`)).items[0]
    assert.equal(archive.internal_status, 'IN_PRODUCTION')
    assert.equal(archive.priority.level, 'P4')
    assert.equal((await api(admin, '/manager-tasks?source_type=OZON_CANCELLED_AFTER_START')).total, 1)
    await api(admin, `/orders/${target.id}/status`, 'POST', { status: 'PRODUCED' }, 409)
    assert.ok((await api(admin, `/orders/${target.id}/timeline`)).items.some(row => row.body.includes('cancelled')))
    await admin.getByRole('button', { name: 'Задачи руководителя', exact: true }).click()
    const cancellationTask = admin.locator('article').filter({ hasText: posting })
    await cancellationTask.getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await cancellationTask.getByRole('button', { name: 'Решено', exact: true }).click()
    await until(async () => (await api(admin, '/manager-tasks?source_type=OZON_CANCELLED_AFTER_START')).items[0].status === 'RESOLVED', 'cancellation task resolved')
    await env.changeOzon({})
    await env.reconcile()
    const sync = await api(admin, '/ozon/sync-state')
    assert.ok(sync.last_successful_sync)
    await admin.getByRole('button', { name: 'Ozon', exact: true }).click()
    await text(admin.locator('main'), 'Mock')
  },

  async 'conflict outage offline deletion and revoked session'({ admin, worker, env, contexts }) {
    await login(admin, env.origin)
    await login(worker, env.origin, 'worker')
    const card = await openOrder(worker, 'MOCK-NORMAL')
    const target = await order(admin, 'MOCK-NORMAL')
    const administrator = await api(admin, '/auth/me')
    env.raceBeforeClaim(() => api(admin, `/orders/${target.id}/assignment`, 'PUT', { user_id: administrator.id }))
    await card.getByRole('button', { name: 'Взять в работу', exact: true }).click()
    await text(worker.locator('main'), 'Заказ изменился или переход уже недоступен')
    assert.equal((await order(admin, 'MOCK-NORMAL')).assigned_user.id, administrator.id)
    env.outage(true)
    await worker.getByRole('button', { name: 'Обновить очередь', exact: true }).click()
    await text(worker.locator('main'), 'OFFLINE · Нет связи с сервером')
    assert.equal(await worker.evaluate(() => navigator.onLine), true)
    await worker.getByRole('button', { name: 'Закрыть и удалить offline-данные', exact: true }).click()
    await text(worker.locator('main'), 'Нет сохранённой очереди')
    assert.equal(await worker.evaluate(() => sessionStorage.getItem('production.queue.v1')), null)
    env.outage(false)
    await worker.getByRole('button', { name: 'Проверить соединение', exact: true }).click()
    await text(worker.locator('main'), 'Очередь загружена с сервера', 45000)
    await contexts[1].setOffline(true)
    await text(worker.locator('main'), 'OFFLINE · Нет связи с сервером')
    await worker.evaluate(() => {
      const key = 'production.queue.v1'
      const snapshot = JSON.parse(sessionStorage.getItem(key))
      snapshot.savedAt = new Date(Date.now() - 3600001).toISOString()
      sessionStorage.setItem(key, JSON.stringify(snapshot))
    })
    await worker.reload()
    await text(worker.locator('main'), 'Нет сохранённой очереди')
    assert.equal(await worker.evaluate(() => sessionStorage.getItem('production.queue.v1')), null)
    const users = await api(admin, '/users')
    const user = users.items.find(row => row.username === 'worker')
    await api(admin, `/users/${user.id}/deactivate`, 'POST')
    await contexts[1].setOffline(false)
    await worker.getByRole('button', { name: 'Войти', exact: true }).waitFor({ timeout: 45000 })
    await api(worker, '/orders', 'GET', undefined, 401)
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
            ...(viewportName === 'mobile' ? { isMobile: true, hasTouch: true } : {}) })
          await context.tracing.start({ screenshots: true, snapshots: true, sources: true })
          await context.addInitScript(() => {
            window.__e2eOrderEvents = []
            const NativeEventSource = window.EventSource
            window.EventSource = class extends NativeEventSource {
              constructor(...args) {
                super(...args)
                this.addEventListener('orders', event => window.__e2eOrderEvents.push(event.data))
              }
            }
          })
          contexts.push(context)
        }
        const pages = await Promise.all(contexts.map(context => context.newPage()))
        for (const page of pages) { page.setDefaultTimeout(15000); page.on('pageerror', error => errors.push(error.message)) }
        await scenario({ admin: pages[0], worker: pages[1], manager: pages[2], contexts, env })
        assert.deepEqual(errors, [], 'uncaught browser errors')
        passed++
        console.log(`PASS ${viewportName}: ${name}`)
      } catch (error) {
        failed++
        console.error(`FAIL ${viewportName}: ${name}\n${error.stack}`)
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
