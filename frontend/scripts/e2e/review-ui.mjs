import assert from 'node:assert/strict'
import { mkdir, writeFile } from 'node:fs/promises'
import { join } from 'node:path'
import { environment, login, api, openOrder, until, text, root } from './helpers.mjs'

const { chromium } = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const browser = await chromium.launch({ headless: true, ...(process.platform === 'win32' ? { channel: 'msedge' } : {}) })
const directory = join(root, 'frontend/e2e-results/ui-review', process.env.UI_REVIEW_PHASE || 'after')
await mkdir(directory, { recursive: true })
const results = []
const posting = '0210000001-0001-1'
const longText = 'Нужна белая кромка для длинного фасада. '.repeat(20) + 'Артикул_' + 'А'.repeat(100)

async function incoming(page, env) {
  await env.changeOzon({ status: 'awaiting_packaging', in_process_at: new Date().toISOString(), shipment_date: new Date(Date.now() + 6 * 3600000).toISOString(),
    products: [{ sku: 1904686181, offer_id: 'TUMBA-WHITE-' + 'A'.repeat(90), name: 'Тумба с длинным названием, белый фасад и дубовая столешница '.repeat(3), quantity: 2, price: '12990.10', currency_code: 'RUB' }] })
  const response = await page.request.post('/api/ozon/webhook', { data: { message_type: 'TYPE_NEW_POSTING', posting_number: posting, seller_id: 42, warehouse_id: 123,
    products: [{ sku: 1904686181, quantity: 2 }], in_process_at: new Date().toISOString(), shipment_date: new Date(Date.now() + 6 * 3600000).toISOString() } })
  assert.equal(response.status(), 200)
  await until(async () => (await api(page, `/orders?q=${posting}`)).items[0], 'incoming review fixture', 20000)
}
async function cancel(page, env) {
  await env.changeOzon({ status: 'cancelled' })
  const response = await page.request.post('/api/ozon/webhook', { data: { message_type: 'TYPE_POSTING_CANCELLED', posting_number: posting,
    seller_id: 42, warehouse_id: 123, old_state: 'awaiting_packaging', new_state: 'cancelled', changed_state_date: new Date().toISOString(),
    products: [{ sku: 1904686181, quantity: 2 }], reason: { id: 1, message: 'Synthetic review cancellation' } } })
  assert.equal(response.status(), 200)
  await until(async () => (await api(page, '/orders/feed')).items.find(row => row.posting_number === posting)?.cancelled, 'cancellation review', 20000)
}
async function capture(page, name) {
  const width = page.viewportSize().width
  await page.evaluate(() => window.scrollTo(0, 0))
  await page.screenshot({ path: join(directory, `${name}-${width}.png`), fullPage: true })
  await page.screenshot({ path: join(directory, `${name}-${width}-viewport.png`) })
  assert.equal(await page.locator('body').evaluate(el => el.scrollWidth > innerWidth), false, `${name}: overflow at ${width}`)
  // Basic screen reader names, operational touch targets and reduced-motion support.
  const issues = await page.evaluate(() => {
    const visible = el => el.getClientRects().length && getComputedStyle(el).visibility !== 'hidden'
    const issues = []
    for (const el of document.querySelectorAll('button, input, textarea, select')) {
      if (!visible(el)) continue
      const named = el.getAttribute('aria-label') || el.getAttribute('aria-labelledby') || el.textContent.trim() || el.labels?.length
      if (!named) issues.push(`unnamed ${el.tagName}`)
    }
    for (const el of document.querySelectorAll('.btn, .nav-button, summary')) {
      if (visible(el) && el.getBoundingClientRect().height < 43.5) issues.push(`small target: ${el.textContent}`)
    }
    const button = document.querySelector('.btn')
    if (button && getComputedStyle(button).transitionDuration !== '0s') issues.push('reduced motion ignored')
    const rgb = color => color.match(/[\d.]+/g)?.map(Number)
    const luminance = channels => channels.slice(0, 3).map(v => v / 255).map(v => v <= .04045 ? v / 12.92 : ((v + .055) / 1.055) ** 2.4).reduce((sum, v, i) => sum + v * [.2126, .7152, .0722][i], 0)
    for (const el of document.querySelectorAll('.muted, .badge, .btn, .nav-button, .environment-note, .nav-count')) {
      if (!visible(el) || el.disabled) continue
      let node = el
      let background
      while (node && !background) {
        const color = rgb(getComputedStyle(node).backgroundColor)
        if (color && (color.length === 3 || color[3] === 1)) background = color
        node = node.parentElement
      }
      const foreground = luminance(rgb(getComputedStyle(el).color))
      const back = luminance(background || [255, 255, 255])
      const contrast = (Math.max(foreground, back) + .05) / (Math.min(foreground, back) + .05)
      if (contrast < 4.5) issues.push(`low contrast ${contrast.toFixed(2)}: ${el.textContent}`)
    }
    return issues
  })
  assert.deepEqual(issues, [], `${name}: accessibility smoke`)
  results.push({ screen: name, width, overflow: false, accessibility: 'pass' })
}
async function session(viewport, work) {
  const env = await environment()
  // Fault-state review intercepts transport; the separate 12-case E2E uses actual SW.
  const context = await browser.newContext({ viewport, baseURL: env.origin, serviceWorkers: 'block', timezoneId: 'Europe/Moscow', reducedMotion: 'reduce', ...(viewport.width === 390 ? { isMobile: true, hasTouch: true } : {}) })
  const page = await context.newPage()
  const errors = []
  page.on('pageerror', e => errors.push(e.message))
  try { await login(page, env.origin); await work(page, env, context); assert.deepEqual(errors, []) }
  finally { await context.close(); await env.close() }
}
try {
  for (const viewport of [{ width: 1440, height: 1000 }, { width: 1024, height: 768 }, { width: 390, height: 844 }]) {
    await session(viewport, async (page, env, context) => {
      for (const [name, button, expected] of [['home', 'Главная', 'Что делать сейчас'], ['queue', 'Заказы', 'MOCK-NORMAL'], ['feed', 'Лента заказов', 'MOCK-NORMAL'], ['problems', 'Проблемы (0)', 'Активных проблем нет']]) {
        await page.getByRole('button', { name: button, exact: true }).click()
        await text(page.locator('main'), expected)
        await capture(page, name)
        if (name === 'home' && viewport.width > 390) {
          const box = await page.locator('.dashboard-grid').boundingBox()
          assert.ok(box.y + box.height < viewport.height, `Home priorities/metrics must fit ${viewport.width}x${viewport.height}`)
        }
        if (name === 'home' && viewport.width === 390) {
          const priority = await page.locator('.focus-order').boundingBox()
          const navigation = await page.locator('.primary-nav').boundingBox()
          assert.ok(priority.y + priority.height < navigation.y, 'first mobile priority/action is visible above bottom navigation')
        }
      }
      await page.getByRole('button', { name: 'Главная', exact: true }).click()
      await page.locator('.focus-open').click()
      await text(page.locator('main'), 'MOCK-OVERDUE')
      await capture(page, 'p0-detail')
      await page.getByRole('button', { name: 'Главная', exact: true }).click()
      const syncRoute = '**/api/ozon/sync-state'
      for (const [name, status, stale] of [['sync-fresh', 'OK', false], ['sync-error', 'ERROR', true]]) {
        await page.route(syncRoute, route => route.fulfill({ json: { enabled: true, status, stale,
          last_successful_sync: new Date().toISOString(), age_seconds: 1, last_attempt_at: new Date().toISOString(), error_code: status === 'ERROR' ? 'NETWORK_ERROR' : null } }))
        await page.reload()
        await page.getByRole('button', { name: 'Главная', exact: true }).click()
        await page.locator('.focus-order').waitFor()
        await text(page.locator('.sync-status'), status === 'ERROR' ? 'Ошибка синхронизации' : 'данные актуальны')
        await capture(page, name)
        await page.unroute(syncRoute)
      }
      await page.reload()
      await page.getByRole('button', { name: 'Главная', exact: true }).click()
      await page.locator('.focus-order').waitFor()
      await page.locator('.sync-status summary').click()
      await capture(page, 'sync-stale-expanded')
      await page.locator('.sync-status summary').click()
      await page.route('**/api/dashboard', async route => {
        const data = await (await route.fetch()).json()
        await route.fulfill({ json: { ...data, attention: [], critical: 0, blocked: 0, ready: 0, overdue: 0,
          money_at_risk: { total: '0', unpriced_count: 0, buckets: [] } } })
      }, { times: 1 })
      await page.getByRole('button', { name: 'Обновить', exact: true }).click()
      await text(page.locator('main'), 'Срочных заказов нет')
      await capture(page, 'home-empty')
      await page.getByRole('button', { name: 'Обновить', exact: true }).click()
      await page.locator('.focus-order').waitFor()
      // Actual search empty state, transport error and held initial load.
      await page.getByRole('button', { name: 'Заказы', exact: true }).click()
      await page.getByLabel('Поиск заказов').fill('REVIEW-NO-SUCH-ORDER')
      await page.getByRole('button', { name: 'Найти', exact: true }).click()
      await text(page.locator('main'), 'Ничего не найдено')
      await capture(page, 'empty')
      await page.getByRole('button', { name: 'Главная', exact: true }).click()
      let release
      const barrier = new Promise(resolve => { release = resolve })
      const ordersRoute = '**/api/orders?*'
      await page.route(ordersRoute, async route => { await barrier; await route.continue() }, { times: 1 })
      await page.getByRole('button', { name: 'Заказы', exact: true }).click()
      await text(page.locator('main'), 'Загружаем заказы')
      await capture(page, 'loading')
      release()
      await text(page.locator('main'), 'MOCK-NORMAL')
      await page.route(ordersRoute, route => route.fulfill({ status: 400, body: '{}' }), { times: 1 })
      await page.getByRole('button', { name: 'Обновить очередь', exact: true }).click()
      await text(page.getByRole('alert'), 'Ошибка 400')
      await capture(page, 'error')
      await page.getByRole('button', { name: 'Обновить очередь', exact: true }).click()
      await until(async () => await page.getByRole('alert').count() === 0, 'error recovery')
      await page.locator('.skip-link').focus()
      await page.keyboard.press('Enter')
      assert.equal(await page.locator('#workspace').evaluate(el => document.activeElement === el), true)
      await incoming(page, env)
      const card = await openOrder(page, posting)
      await capture(page, 'normal-long-product')
      await card.locator('summary').filter({ hasText: 'Полный товар' }).click()
      await capture(page, 'expanded-product')
      await card.locator('.expandable-text summary').first().click()
      await card.getByRole('button', { name: 'Взять в работу', exact: true }).click()
      await text(card, 'В работе')
      await card.getByRole('button', { name: 'Есть проблема', exact: true }).click()
      await until(() => card.getByLabel('Что случилось').evaluate(el => el === document.activeElement), 'problem autofocus')
      await card.getByLabel('Что случилось').fill('   ')
      assert.equal(await card.getByRole('button', { name: 'Сообщить о проблеме', exact: true }).isDisabled(), true)
      await card.getByLabel('Что случилось').fill(longText)
      let problemPosts = 0
      page.on('request', req => { if (req.method() === 'POST' && new URL(req.url()).pathname === '/api/blockers') problemPosts++ })
      await card.getByLabel('Что случилось').evaluate(el => { el.form.requestSubmit(); el.form.requestSubmit() })
      await text(card, longText)
      assert.equal(problemPosts, 1, 'double-submit problem sends one mutation')
      await capture(page, 'problem-long')
      await card.locator('summary').filter({ hasText: 'Полное описание' }).click()
      await capture(page, 'expanded-problem')
      await card.locator('.problem .expandable-text summary').click()
      await page.getByRole('button', { name: 'Проблемы (1)', exact: true }).click()
      await text(page.locator('main'), longText)
      await capture(page, 'problems-active')
      await card.locator('summary').filter({ hasText: 'История и комментарии' }).focus()
      await page.keyboard.press('Enter')
      await card.getByLabel('Комментарий', { exact: true }).fill(longText)
      let commentPosts = 0
      page.on('request', req => { if (req.method() === 'POST' && new URL(req.url()).pathname.endsWith('/comments')) commentPosts++ })
      await card.locator('.timeline form').evaluate(form => { form.requestSubmit(); form.requestSubmit() })
      await text(card.locator('.timeline ol'), longText)
      assert.equal(commentPosts, 1, 'double-submit comment sends one mutation')
      await capture(page, 'comments-timeline')
      await cancel(page, env)
      await text(card, 'КРИТИЧЕСКАЯ ОТМЕНА OZON', 20000)
      await capture(page, 'critical-cancellation-order')
      await page.getByRole('button', { name: 'Главная', exact: true }).click()
      await text(page.locator('main'), 'КРИТИЧЕСКАЯ ОТМЕНА OZON')
      await capture(page, 'critical-cancellation-home')
      await page.locator('summary').filter({ hasText: 'Администрирование и профиль' }).click()
      await page.getByRole('button', { name: 'Пользователи', exact: true }).click()
      await page.getByRole('heading', { name: 'Новый пользователь', exact: true }).waitFor()
      assert.equal(await page.locator('.secondary-nav').evaluate(el => el.open), false, 'profile closes after navigation')
      await capture(page, 'admin')
      await page.locator('.secondary-nav summary').click()
      await page.keyboard.press('Escape')
      assert.equal(await page.locator('.secondary-nav').evaluate(el => el.open), false, 'Escape closes profile')
      assert.equal(await page.locator('.secondary-nav summary').evaluate(el => el === document.activeElement), true)
      await page.locator('.secondary-nav summary').click()
      await page.getByRole('button', { name: 'Ozon', exact: true }).click()
      await page.getByText('Заменить credentials', { exact: true }).waitFor()
      await capture(page, 'admin-ozon')
      await page.getByRole('button', { name: 'Заказы', exact: true }).click()
      await text(page.locator('main'), 'MOCK-NORMAL')
      await context.setOffline(true)
      await page.evaluate(() => window.dispatchEvent(new Event('offline')))
      await text(page.locator('main'), 'OFFLINE')
      assert.equal(await page.locator('.secondary-nav').count(), 0, 'offline controls are not covered by profile')
      await capture(page, 'offline')
      let resumeConnection
      const connection = new Promise(resolve => { resumeConnection = resolve })
      await page.route('**/api/auth/me', async route => { await connection; await route.continue() }, { times: 1 })
      await context.setOffline(false)
      await page.evaluate(() => window.dispatchEvent(new Event('online')))
      await text(page.locator('main'), 'Проверяем соединение…')
      await capture(page, 'reconnect')
      resumeConnection()
      await until(async () => await page.getByText('OFFLINE · Нет связи с сервером', { exact: true }).count() === 0, 'online recovery')
      await text(page.locator('main'), 'MOCK-NORMAL')
    })
    await session(viewport, async (page, env) => {
      await incoming(page, env)
      await cancel(page, env)
      await page.getByRole('button', { name: 'Лента заказов', exact: true }).click()
      await text(page.locator('main'), posting)
      await text(page.locator('main'), 'Отменён Ozon')
      assert.equal(await page.getByText('КРИТИЧЕСКАЯ ОТМЕНА OZON', { exact: true }).count(), 0)
      await capture(page, 'cancelled-before-start')
    })
    console.log(`UI review passed ${viewport.width}x${viewport.height}`)
  }
  await writeFile(join(directory, 'review.json'), JSON.stringify(results, null, 2))
  console.log(`UI review: ${results.length} captures, overflow/accessibility/keyboard/validation/double-submit checks passed; ${directory}`)
} finally { await browser.close() }
