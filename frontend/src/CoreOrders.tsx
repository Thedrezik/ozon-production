import { useCallback, useEffect, useRef, useState, type FormEvent, type ReactNode } from 'react'
import { clearQueueSnapshot, reportUnavailable, saveQueueSnapshot } from './offline'
import { dateTime, useFeatures } from './features'
import { button, Loading, StatusBadge } from './ui'
import { money } from './format'

type User = { id: number; csrf_token?: string; permissions: string[] }
type Problem = { id: number; description: string; severity: string; creator_user_id: number; creator: string; created_at: string }
type Row = {
  id: number; posting_number: string; order_number: string | null; internal_status: string; ozon_status: string;
  received_at: string; shipment_deadline: string; critical_cancellation: boolean; cancelled: boolean;
  assigned_user: { id: number; display_name: string } | null;
  priority: { level: string; label: string; reasons: string[] } | null;
  tariff: { next: { starts_at: string; tariff_type: string; currency: string | null; rate_percent: string | null } | null; delta_to_next_tariff: string | null } | null;
  items: { product_name: string; offer_id: string | null; sku: string | null; quantity: number; price: string | null; currency: string | null }[];
  problems?: Problem[];
}
type Page = { items: Row[]; total: number }
type Event = { id: string; kind: string; body: string; author: string | null; created_at: string }
const labels: Record<string, string> = { NEW: 'Новый', QUEUED: 'Новый', SENT_TO_PRODUCTION: 'Новый', IN_PRODUCTION: 'В работе', BLOCKED: 'Есть проблема', PRODUCED: 'Произведён', QUALITY_CHECK: 'Произведён', PACKING: 'Произведён', READY_TO_SHIP: 'Упакован', HANDED_TO_SHIPPING: 'Отгружен', DONE: 'Отгружен', CANCELLED: 'Отменён' }

function ExpandableText({ children, label }: { children: ReactNode; label: string }) {
  return <details className="expandable-text"><summary><div className="text-preview">{children}</div><span className="collapsed-toggle muted">{label} ↓</span><span className="expanded-toggle muted">Свернуть ↑</span></summary><div className="expanded-body">{children}</div></details>
}

function Product({ item }: { item: Row['items'][number] }) {
  const article = item.offer_id ?? item.sku ?? '—'
  const contents = <><p className="font-medium">{item.product_name} · {item.quantity} шт.</p><p className="muted">Артикул: {article}</p></>
  return <div className="order-product"><div>{item.product_name.length > 90 || article.length > 40 ? <ExpandableText label="Полный товар">{contents}</ExpandableText> : contents}</div><p className="item-price">{item.price === null ? 'Цена неизвестна' : money(item.price, item.currency ?? '')}</p></div>
}

async function request<T>(path: string, csrf?: string, body?: unknown, method = 'POST'): Promise<T> {
  if (body !== undefined && !navigator.onLine) throw new Error('OFFLINE: изменения недоступны')
  let response: Response
  try { response = await fetch(`/api${path}`, { cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(12_000),
    ...(body !== undefined ? { method, body: JSON.stringify(body), headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf ?? '' } } : {}) }) }
  catch (error) { reportUnavailable(); throw error }
  if (response.status === 401) { clearQueueSnapshot(); window.dispatchEvent(new Event('session-invalid')) }
  if (response.status >= 500) reportUnavailable()
  if (!response.ok) throw new Error(response.status === 409 ? 'Заказ изменился или переход уже недоступен. Состояние обновлено с сервера.' : `Ошибка ${response.status}`)
  return response.json() as Promise<T>
}

function Timeline({ row, current, refreshToken }: { row: Row; current: User; refreshToken: number }) {
  const { timezone } = useFeatures()
  const [opened, setOpened] = useState(false)
  const [items, setItems] = useState<Event[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [body, setBody] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  const [loaded, setLoaded] = useState(false)
  const [notice, setNotice] = useState('')
  const refresh = useCallback(async () => {
    try { const page = await request<{ items: Event[]; total: number }>(`/orders/${row.id}/timeline?offset=${offset}&limit=50`); setItems(page.items); setTotal(page.total); setError('') }
    catch (e) { setError(String(e)) }
    finally { setLoaded(true) }
  }, [row.id, offset])
  useEffect(() => { if (opened) void refresh() }, [opened, refresh, refreshToken])
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (submitting.current || !body.trim()) return
    submitting.current = true; setBusy(true); setNotice('')
    try { await request(`/orders/${row.id}/comments`, current.csrf_token, { body }); setBody(''); setNotice('Комментарий добавлен'); await refresh() }
    catch (e) { setError(String(e)) } finally { submitting.current = false; setBusy(false) }
  }
  return <details className="timeline" onToggle={e => setOpened(e.currentTarget.open)}>
    <summary>История и комментарии</summary>
    {error && <p role="alert" className="state state-danger">{error}</p>}
    {!loaded && opened && <Loading label="Загружаем историю…" />}
    {loaded && !items.length && !error && <p className="muted">История пока пуста. Добавьте первый комментарий.</p>}
    <ol>{items.map(item => <li key={item.id} data-kind={item.kind}>
      <p className="muted">{item.author ?? 'Система'} · <time dateTime={item.created_at}>{dateTime(item.created_at, timezone)}</time></p><p className="whitespace-pre-wrap">{item.body}</p>
    </li>)}</ol>
    {total > 50 && <div className="my-3 flex justify-between"><button className={button} disabled={offset === 0} onClick={() => setOffset(v => Math.max(0, v - 50))}>Раньше</button><span>{offset + 1}–{Math.min(offset + 50, total)} / {total}</span><button className={button} disabled={offset + 50 >= total} onClick={() => setOffset(v => v + 50)}>Позже</button></div>}
    {notice && <p role="status" className="muted">{notice}</p>}
    {current.permissions.includes('comments.create') && <form onSubmit={submit} className="inline-form"><label>Комментарий<textarea aria-label="Комментарий" required maxLength={5000} value={body} onChange={e => setBody(e.target.value)} placeholder="Что важно знать по этому заказу?" /></label><button className={button} disabled={busy || !body.trim()} aria-busy={busy}>{busy ? 'Добавляем…' : 'Добавить комментарий'}</button></form>}
  </details>
}

export function CoreOrders({ current, mine = false, feed = false, initialFilter = '', refreshToken = 0 }: { current: User; mine?: boolean; feed?: boolean; initialFilter?: string; refreshToken?: number }) {
  const { timezone } = useFeatures()
  const [page, setPage] = useState<Page>({ items: [], total: 0 })
  const [query, setQuery] = useState('')
  const [search, setSearch] = useState('')
  const [offset, setOffset] = useState(0)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [problemId, setProblemId] = useState<number | null>(null)
  const [reason, setReason] = useState('')
  const [resolveId, setResolveId] = useState<number | null>(null)
  const [resolution, setResolution] = useState('')
  const [loaded, setLoaded] = useState(false)
  const [notice, setNotice] = useState('')
  const acting = useRef(false)
  const [now, setNow] = useState(Date.now())
  const version = useRef(0)
  const refresh = useCallback(async () => {
    const serial = ++version.current
    const params = new URLSearchParams({ limit: '20', offset: String(offset) })
    if (mine && !initialFilter.startsWith('order_id:')) params.set('assigned_user_id', String(current.id))
    if (initialFilter.startsWith('order_id:')) params.set('order_id', initialFilter.split(':')[1])
    else if (initialFilter) params.set(initialFilter, initialFilter === 'priority_level' ? 'P0' : 'true')
    if (search) params.set('q', search)
    try {
      const result = await request<Page>(`${feed ? '/orders/feed' : '/orders'}?${params}`)
      if (serial !== version.current) return
      setPage(result); setError('')
      if (!feed) saveQueueSnapshot(current.id, mine ? 'Мои задачи' : 'Очередь', offset, result)
    } catch (e) { if (serial === version.current) setError(String(e)) }
    finally { if (serial === version.current) setLoaded(true) }
  }, [current.id, feed, mine, initialFilter, offset, search])
  useEffect(() => { const currentVersion = version; void refresh(); return () => { currentVersion.current++ } }, [refresh, refreshToken])
  useEffect(() => { const tick = window.setInterval(() => setNow(Date.now()), 10_000); return () => clearInterval(tick) }, [])
  async function act(path: string, body: unknown, method = 'POST') {
    if (acting.current) return
    const focusTarget = document.activeElement?.closest('article')?.id
    acting.current = true; setBusy(true); setNotice('')
    try { await request(path, current.csrf_token, body, method); setProblemId(null); setReason(''); setResolveId(null); setResolution(''); setNotice('Изменения сохранены'); await refresh() }
    catch (e) { await refresh(); setError(e instanceof Error ? e.message : String(e)) } finally {
      acting.current = false; setBusy(false)
      if (focusTarget) requestAnimationFrame(() => (document.getElementById(focusTarget) ?? document.getElementById('workspace'))?.focus({ preventScroll: true }))
    }
  }
  async function next() {
    if (acting.current) return
    acting.current = true; setBusy(true)
    try {
      const result = await request<Page>('/orders?claimable=true&limit=1')
      if (!result.items.length) { setNotice('Подходящих новых заказов сейчас нет.'); return }
      acting.current = false
      await act(`/orders/${result.items[0].id}/claim`, {})
    } finally { acting.current = false; setBusy(false) }
  }
  function countdown(value: string) {
    const minutes = Math.ceil((Date.parse(value) - now) / 60_000)
    return minutes <= 0 ? 'Срок наступил' : `${Math.floor(minutes / 60)} ч ${minutes % 60} мин`
  }
  return <section className={`orders-workspace space-y-3 ${feed ? 'feed-workspace' : ''} ${initialFilter.startsWith('order_id:') ? 'detail-workspace' : ''}`}><div className="page-heading"><h2>{feed ? 'Лента заказов' : initialFilter === 'problems' ? 'Проблемы' : mine ? 'Мои задачи' : initialFilter.startsWith('order_id:') ? 'Карточка заказа' : 'Заказы'} <span className="muted">· {loaded ? page.total : '…'}</span></h2><button className={`${button} btn-ghost btn-refresh`} onClick={() => void refresh()} aria-label="Обновить очередь">Обновить</button></div>
    {feed ? <p className="muted">По времени поступления Ozon, сначала ранние. Если время отсутствует — по получению.</p> : !initialFilter.startsWith('order_id:') && <form className="order-search flex gap-2" onSubmit={e => { e.preventDefault(); setOffset(0); setSearch(query.trim()) }}><input aria-label="Поиск заказов" value={query} onChange={e => setQuery(e.target.value)} placeholder="Номер, артикул или название" className="min-w-0 flex-1 rounded-xl border px-3 py-2" /><button className={button}>Найти</button></form>}
    {mine && current.permissions.includes('orders.change_status') && <button className={`${button} btn-primary w-full`} disabled={busy} onClick={() => void next().catch(e => setError(String(e)))}>Взять следующий заказ</button>}
    {error && <p role="alert" className="state state-danger">{error}</p>}
    {notice && <p role="status" className="state state-success">{notice}</p>}
    {!loaded && !error && <Loading label="Загружаем заказы…" />}
    {loaded && !page.items.length && !error && <p className="state">{search ? 'Ничего не найдено. Попробуйте другой номер или артикул.' : initialFilter === 'problems' ? 'Активных проблем нет. Производство может продолжаться.' : feed ? 'Заказы ещё не поступили. Они появятся после синхронизации Ozon.' : mine ? 'У вас пока нет заказов. Возьмите следующий из очереди.' : 'Нет заказов по выбранным условиям.'}</p>}
    {page.items.map(row => {
      const owned = row.assigned_user?.id === current.id || current.permissions.includes('orders.assign')
      const workable = !row.cancelled && !['DONE', 'HANDED_TO_SHIPPING', 'CANCELLED'].includes(row.internal_status)
      const canAct = workable && owned && current.permissions.includes('orders.change_status')
      return <article id={`order-${row.id}`} tabIndex={-1} key={row.id} className={`order-card ${feed ? 'feed-card' : ''} ${row.cancelled ? 'is-cancelled' : ''} ${row.critical_cancellation ? 'is-critical' : ''}`} data-priority={row.priority?.level}>
        {feed && <p className="muted feed-time"><time dateTime={row.received_at}>{dateTime(row.received_at, timezone)}</time></p>}
        <div className="order-header"><h3>{row.posting_number}</h3>{!feed && <StatusBadge status={row.internal_status} label={labels[row.internal_status] ?? row.internal_status} />}{!feed && row.priority && <span className={`badge priority-${row.priority.level}`}>{row.priority.level} · {row.priority.label}</span>}</div>
        {row.cancelled && <div className="cancellation" role={row.critical_cancellation ? 'alert' : undefined}><strong>{row.critical_cancellation ? 'КРИТИЧЕСКАЯ ОТМЕНА OZON' : 'Отменён Ozon'}</strong>{row.critical_cancellation && <span>Производство остановлено. Требуется решение администратора.</span>}</div>}
        <div className="order-products">{row.items.map((item, index) => <Product key={index} item={item} />)}</div>
        <div className="order-meta">{!feed && <span>{row.assigned_user?.display_name ?? 'Ответственный не назначен'}</span>}<span>Ozon: {row.ozon_status}</span>{!feed && <span>Получен: {dateTime(row.received_at, timezone)}</span>}{row.order_number && <span>Заказ {row.order_number}</span>}</div>
        {!feed && <><div className="order-risk"><p>До отгрузки: <strong>{countdown(row.shipment_deadline)}</strong> <span className="muted">· {dateTime(row.shipment_deadline, timezone)}</span></p>
          {row.tariff?.next && <p className="text-amber-800">Следующий тариф через <strong>{countdown(row.tariff.next.starts_at)}</strong> · Финансовый эффект: {row.tariff.delta_to_next_tariff === null ? 'неизвестен' : `${row.tariff.delta_to_next_tariff} ${row.tariff.next.currency === 'RUB' ? '₽' : row.tariff.next.currency ?? ''}`}</p>}
          {!row.tariff && <p className="muted">Денежный эффект неизвестен</p>}</div>
          {row.problems?.map(problem => <div key={problem.id} className={`problem ${problem.severity === 'CRITICAL' ? 'problem-critical' : ''}`}><p className="font-semibold">{problem.severity === 'CRITICAL' ? 'Критическая проблема' : 'Есть проблема'}</p>{problem.description.length > 240 ? <ExpandableText label="Полное описание"><p className="whitespace-pre-wrap">{problem.description}</p></ExpandableText> : <p className="whitespace-pre-wrap">{problem.description}</p>}<p className="muted">{problem.creator} · {dateTime(problem.created_at, timezone)} · Активна {Math.max(0, Math.floor((now - Date.parse(problem.created_at)) / 3600000))} ч {Math.max(0, Math.floor((now - Date.parse(problem.created_at)) / 60000) % 60)} мин</p>{current.permissions.includes('blockers.resolve') && <button className={`${button} mt-2`} disabled={busy} onClick={() => { setResolveId(problem.id); setResolution('') }}>Решена</button>}
            {resolveId === problem.id && <form className="inline-form" onSubmit={e => { e.preventDefault(); void act(`/blockers/${problem.id}`, { status: 'RESOLVED', resolution_comment: resolution }, 'PATCH') }}><label>Как решена проблема<textarea aria-label="Комментарий к решению" autoFocus maxLength={5000} value={resolution} onChange={e => setResolution(e.target.value)} placeholder="Необязательно" /></label><div className="flex flex-wrap gap-2"><button className={`${button} btn-primary`} disabled={busy}>Сохранить решение</button><button type="button" className={button} disabled={busy} onClick={() => setResolveId(null)}>Отмена</button></div></form>}
          </div>)}
          <div className={`order-actions ${initialFilter.startsWith('order_id:') ? 'detail-actions' : ''}`}>
            {workable && (!row.assigned_user || row.assigned_user.id === current.id) && ['NEW', 'QUEUED', 'SENT_TO_PRODUCTION'].includes(row.internal_status) && current.permissions.includes('orders.change_status') && <button className={`${button} btn-primary`} disabled={busy} onClick={() => void act(`/orders/${row.id}/claim`, {})}>Взять в работу</button>}
            {canAct && row.internal_status === 'IN_PRODUCTION' && <button className={`${button} btn-primary`} disabled={busy} onClick={() => void act(`/orders/${row.id}/status`, { status: 'PRODUCED' })}>Произведено</button>}
            {canAct && ['PRODUCED', 'QUALITY_CHECK', 'PACKING'].includes(row.internal_status) && <button className={`${button} btn-primary`} disabled={busy} onClick={() => void act(`/orders/${row.id}/status`, { status: 'READY_TO_SHIP' })}>Упаковано</button>}
            {workable && current.permissions.includes('blockers.create') && <button className={button} disabled={busy} onClick={() => { setProblemId(row.id); setReason('') }}>Есть проблема</button>}
            {row.cancelled && row.critical_cancellation && current.permissions.includes('orders.assign') && row.internal_status !== 'CANCELLED' && <button className={`${button} btn-danger`} disabled={busy} onClick={() => { if (window.confirm('Закрыть отменённый заказ в производстве?')) void act(`/orders/${row.id}/status`, { status: 'CANCELLED' }) }}>Закрыть производство</button>}
          </div>
          {problemId === row.id && <form onSubmit={e => { e.preventDefault(); if (reason.trim()) void act('/blockers', { order_id: row.id, description: reason }) }} className="inline-form"><label>Что случилось<textarea aria-label="Что случилось" autoFocus required maxLength={5000} value={reason} onChange={e => setReason(e.target.value)} placeholder="Например, не хватает белой кромки" /></label><div className="flex flex-wrap gap-2"><button className={`${button} btn-primary`} disabled={busy || !reason.trim()} aria-busy={busy}>{busy ? 'Сохраняем…' : 'Сообщить о проблеме'}</button><button type="button" className={button} disabled={busy} onClick={() => setProblemId(null)}>Отмена</button></div></form>}
          {row.priority && <details className="priority-explanation"><summary>Почему {row.priority.level} · {row.priority.label}</summary><ul>{row.priority.reasons.map(reason => <li key={reason}>{reason}</li>)}</ul>{row.tariff?.next && <p>Следующая ступень: {row.tariff.next.tariff_type}{row.tariff.next.rate_percent !== null && ` ${row.tariff.next.rate_percent}%`}</p>}</details>}
        </>}
        <Timeline row={row} current={current} refreshToken={refreshToken} />
      </article>
    })}
    {page.total > 20 && <div className="pagination"><button className={button} disabled={offset === 0} onClick={() => setOffset(v => Math.max(0, v - 20))}>Назад</button><span>{offset + (page.total ? 1 : 0)}–{Math.min(offset + 20, page.total)} / {page.total}</span><button className={button} disabled={offset + 20 >= page.total} onClick={() => setOffset(v => v + 20)}>Далее</button></div>}
  </section>
}
