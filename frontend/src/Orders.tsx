import { Photos, OrderQR, Scanner } from './Files'
import { useCallback, useEffect, useRef, useState, type FormEvent } from 'react'
import { clearQueueSnapshot, reportUnavailable, saveQueueSnapshot } from './offline'

type User = { id: number; csrf_token?: string; permissions: string[] }
type Priority = { level: string; label: string; score: number; reasons: string[]; blocked: boolean; feasible: boolean | null; pinned: boolean; manual_override: string | null }
type PrioritySettings = { deadline_weight: number; tariff_weight: number; finance_weight: number; feasibility_weight: number; high_impact_rub: string; high_value_rub: string }
type TariffStep = { starts_at: string | null; tariff_type: string; rate_percent: string | null; cost: string | null; currency: string | null }
type Tariff = { current: TariffStep | null; next: TariffStep | null; timeline: TariffStep[]; delta_to_next_tariff: string | null; potential_saving: string | null; potential_loss: string | null }
type Order = { id: number; posting_number: string; shipment_deadline: string; internal_status: string; ozon_status: string; priority: Priority | null; tariff: Tariff | null; items: { product_name: string; quantity: number; production_profile: { production_minutes: number; packing_minutes: number; complexity: string; production_group: string | null } | null }[]; assigned_user: { id: number; display_name: string } | null }
type Page = { items: Order[]; total: number }
type Assignee = { id: number; display_name: string; is_active: boolean; permissions: string[] }
type Status = { code: string; display_name: string; sort_order: number }
type TimelineItem = { id: string; kind: 'comment' | 'system'; body: string; author: string | null; author_user_id?: number; created_at: string }
type Blocker = { id: number; order_id: number; type_code: string; description: string; severity: string; status: string; expected_resolution_at: string | null }
type BlockerType = { code: string; display_name: string }

const labels: Record<string, string> = {
  NEW: 'Новый', QUEUED: 'В очереди', SENT_TO_PRODUCTION: 'Передан в производство',
  IN_PRODUCTION: 'В производстве', BLOCKED: 'Проблема', PRODUCED: 'Произведён',
  QUALITY_CHECK: 'Проверка качества', PACKING: 'Упаковка', READY_TO_SHIP: 'Готов к отгрузке', HANDED_TO_SHIPPING: 'Передан в доставку', DONE: 'Завершён', CANCELLED: 'Отменён',
}

function TariffTimeline({ tariff }: { tariff: Tariff }) {
  const signed = (value: string, currency: string | null) => `${value.startsWith('-') ? '' : '+'}${value} ${currency === 'RUB' ? '₽' : currency ?? ''}`
  return <details className="mt-3 rounded-xl border border-slate-200 bg-white p-3 text-sm">
    <summary className="font-semibold">Тариф: {tariff.current?.tariff_type ?? 'неизвестен'}{tariff.next?.starts_at ? ` · следующая ступень ${new Date(tariff.next.starts_at).toLocaleString('ru-RU')}` : ''}</summary>
    {tariff.delta_to_next_tariff !== null && <p className="mt-2">Изменение стоимости: {signed(tariff.delta_to_next_tariff, tariff.next?.currency ?? null)}</p>}
    {tariff.delta_to_next_tariff === null && tariff.next && <p className="mt-2">Денежный эффект неизвестен</p>}
    <ol className="mt-2 space-y-1">{tariff.timeline.map((step, index) => <li key={index}>{step.starts_at ? new Date(step.starts_at).toLocaleString('ru-RU') : 'Сначала'}: {step.tariff_type}{step.rate_percent !== null ? ` · ${step.rate_percent}%` : ''}{step.cost !== null ? ` · ${signed(step.cost, step.currency)}` : ''}</li>)}</ol>
  </details>
}

class RequestError extends Error {
  constructor(message: string, public status: number) { super(message) }
}

async function request<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  if (!navigator.onLine && options.method && options.method !== 'GET') throw new Error('OFFLINE: изменения недоступны. Действие не сохранено.')
  let response: Response
  try {
    response = await fetch(`/api${path}`, { ...options, signal: options.signal ?? AbortSignal.timeout(12_000), credentials: 'same-origin', cache: 'no-store',
      headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) } })
  } catch (cause) { reportUnavailable(); throw cause }
  if (!response.ok) {
    if (response.status >= 500) reportUnavailable()
    if (response.status === 401 || response.status === 403) { clearQueueSnapshot(); window.dispatchEvent(new Event('session-invalid')) }
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new RequestError(body?.detail || `Ошибка ${response.status}`, response.status)
  }
  return response.json() as Promise<T>
}

function OrderTimeline({ orderId, current }: { orderId: number; current: User }) {
  const [items, setItems] = useState<TimelineItem[]>([])
  const [body, setBody] = useState('')
  const [error, setError] = useState('')
  const canComment = current.permissions.includes('comments.create')
  const refresh = useCallback(async () => {
    try { const result = await request<{ items: TimelineItem[] }>(`/orders/${orderId}/timeline`); setItems(result.items); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось загрузить историю') }
  }, [orderId])
  useEffect(() => { void refresh() }, [refresh])
  async function submit(event: FormEvent) {
    event.preventDefault()
    try {
      await request(`/orders/${orderId}/comments`, { method: 'POST', body: JSON.stringify({ body }) }, current.csrf_token)
      setBody(''); await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось отправить комментарий') }
  }
  return <details className="mt-4 rounded-xl border bg-slate-50 p-3" onToggle={event => { if (event.currentTarget.open) void refresh() }}>
    <summary className="cursor-pointer font-semibold">История заказа ({items.length})</summary>
    {error && <p role="alert" className="mt-2 text-sm text-red-700">{error}</p>}
    <ol className="mt-3 space-y-2">{items.map(item => <li key={item.id} className={`rounded-lg p-3 text-sm ${item.kind === 'system' ? 'border border-slate-200 bg-slate-100 text-slate-600' : 'border border-blue-100 bg-white'}`}>
      <p>{item.body}</p>{item.kind === 'comment' && <Photos orderId={orderId} commentId={Number(item.id.replace('comment-', ''))} current={{ ...current, permissions: item.author_user_id === current.id || current.permissions.includes('comments.delete') ? current.permissions : current.permissions.filter(permission => permission !== 'comments.create') }}/>}<p className="mt-1 text-xs text-slate-500">{item.kind === 'system' ? 'Событие системы' : item.author} · {new Date(item.created_at).toLocaleString('ru-RU')}</p>
    </li>)}</ol>
    {canComment && <form onSubmit={event => void submit(event)} className="mt-3 space-y-2"><label className="sr-only" htmlFor={`comment-${orderId}`}>Комментарий</label><textarea id={`comment-${orderId}`} value={body} onChange={event => setBody(event.target.value)} maxLength={5000} required placeholder="Написать комментарий…" className="w-full rounded-xl border bg-white p-3"/><button disabled={!body.trim()} className="min-h-11 rounded-xl bg-blue-800 px-4 py-2 font-semibold text-white disabled:opacity-50">Добавить комментарий</button></form>}
  </details>
}

export function Orders({ current, mine, initialFilter = '', refreshToken = 0 }: { current: User; mine: boolean; initialFilter?: string; refreshToken?: number }) {
  const [page, setPage] = useState<Page>({ items: [], total: 0 })
  const [status, setStatus] = useState('')
  const [priorityLevel, setPriorityLevel] = useState('')
  const [special, setSpecial] = useState(initialFilter)
  const [search, setSearch] = useState('')
  const [ozonStatus, setOzonStatus] = useState('')
  const [product, setProduct] = useState('')
  const [warehouse, setWarehouse] = useState('')
  const [selected, setSelected] = useState<number[]>([])
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [lastUpdated, setLastUpdated] = useState<string | null>(null)
  const [stale, setStale] = useState(true)
  const requestVersion = useRef(0)
  const [assignees, setAssignees] = useState<Assignee[]>([])
  const [statuses, setStatuses] = useState<Status[]>([])
  const [blockers, setBlockers] = useState<Blocker[]>([])
  const [blockerTypes, setBlockerTypes] = useState<BlockerType[]>([])
  const [prioritySettings, setPrioritySettings] = useState<PrioritySettings | null>(null)
  const [problemOrder, setProblemOrder] = useState<number | null>(null)
  const [problemType, setProblemType] = useState('OTHER')
  const [problemDescription, setProblemDescription] = useState('')
  const [nextBusy, setNextBusy] = useState(false)
  const canAssign = current.permissions.includes('orders.assign')
  const shopWorker = current.permissions.includes('orders.change_status') && !current.permissions.includes('orders.assign')

  const refresh = useCallback(async () => {
    const version = ++requestVersion.current
    setStale(true)
    const params = new URLSearchParams({ limit: '20', offset: String(offset) })
    if (mine && !special.startsWith('order_id:')) params.set('assigned_user_id', String(current.id))
    if (status) params.set('status', status)
    if (priorityLevel) params.set('priority_level', priorityLevel)
    if (search.trim()) params.set('q', search.trim())
    if (ozonStatus) params.set('ozon_status', ozonStatus)
    if (product.trim()) params.set('product', product.trim())
    if (warehouse.trim()) params.set('warehouse', warehouse.trim())
    if (special.startsWith('assigned_user_id:')) params.set('assigned_user_id', special.split(':')[1])
    else if (special.startsWith('order_id:')) params.set('order_id', special.split(':')[1])
    else if (special) params.set(special, special === 'priority_level' ? 'P0' : 'true')
    try {
      const [loaded, result] = await Promise.all([request<Page>(`/orders?${params}`), request<{ items: Blocker[] }>('/blockers?limit=100')])
      if (version !== requestVersion.current || !navigator.onLine) return
      setPage(loaded); setBlockers(result.items); setError('')
      saveQueueSnapshot(current.id, mine ? 'Мои задачи (сохранённые фильтры)' : 'Очередь (сохранённые фильтры)', offset, loaded)
      setLastUpdated(new Date().toISOString()); setStale(false)
    }
    catch (cause) {
      if (version !== requestVersion.current) return
      setError(cause instanceof Error ? cause.message : 'Не удалось загрузить очередь')
      if (cause instanceof TypeError || (cause instanceof DOMException && cause.name === 'TimeoutError')) reportUnavailable()
    }
  }, [mine, current.id, offset, status, priorityLevel, special, search, ozonStatus, product, warehouse])

  useEffect(() => {
    const version = requestVersion
    void refresh()
    return () => { version.current++ }
  }, [refresh, refreshToken])
  const refreshStatuses = useCallback(() => { void request<Status[]>('/orders/statuses').then(setStatuses).catch(() => {}) }, [])
  useEffect(() => { refreshStatuses() }, [refreshStatuses])
  useEffect(() => { void request<BlockerType[]>('/blockers/types').then(setBlockerTypes).catch(() => {}) }, [])
  useEffect(() => { if (current.permissions.includes('settings.manage')) void request<PrioritySettings>('/orders/priority-settings').then(setPrioritySettings).catch(() => {}) }, [current.permissions])
  useEffect(() => {
    if (!canAssign) return
    request<{ items: Assignee[] }>('/users?limit=100').then(result => setAssignees(result.items.filter(user => user.is_active && user.permissions.includes('orders.change_status')))).catch(() => setAssignees([]))
  }, [canAssign])
  useEffect(() => { refreshStatuses() }, [refreshToken, refreshStatuses])

  async function editStatus(entry: Status) {
    const display_name = window.prompt('Название статуса', entry.display_name)
    if (display_name === null) return
    const order = window.prompt('Порядок отображения', String(entry.sort_order))
    if (order === null) return
    try {
      await request(`/orders/statuses/${entry.code}`, { method: 'PUT', body: JSON.stringify({ display_name, sort_order: Number(order) }) }, current.csrf_token)
      refreshStatuses()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось сохранить статус') }
  }

  async function act(order: Order, kind: 'claim' | 'status' | 'assignment', value?: string | number | null) {
    setBusy(order.id)
    try {
      const path = `/orders/${order.id}/${kind}`
      const body = kind === 'status' ? { status: value } : { user_id: value }
      await request(path, { method: kind === 'assignment' ? 'PUT' : 'POST', ...(kind === 'claim' ? {} : { body: JSON.stringify(body) }) }, current.csrf_token)
      await refresh()
    } catch (cause) {
      if (cause instanceof RequestError && cause.status === 409) {
        await refresh(); setError('Заказ изменился или переход уже недоступен. Состояние обновлено с сервера. Проверьте заказ перед повторным действием.')
      } else setError(cause instanceof Error ? cause.message : 'Не удалось обновить заказ')
    }
    finally { setBusy(null) }
  }

  async function bulk(action: 'assign' | 'status', value: string | number | null) {
    if (!selected.length) return
    const actionLabel = action === 'assign' ? 'назначение сотрудника' : `переход в статус «${statuses.find(s => s.code === value)?.display_name ?? value}»`
    if (!window.confirm(`Подтвердить ${actionLabel} для ${selected.length} заказов?`)) return
    try {
      await request('/orders/bulk', { method: 'POST', body: JSON.stringify({ order_ids: selected, action, ...(action === 'assign' ? { user_id: value === -1 ? null : value } : { status: value }) }) }, current.csrf_token)
      setSelected([]); await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Массовое действие не выполнено') }
  }

  async function changePriority(order: Order, level: string | null, pinned: boolean) {
    setBusy(order.id)
    try {
      await request(`/orders/${order.id}/priority`, { method: 'PUT', body: JSON.stringify({ level, pinned }) }, current.csrf_token)
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось изменить приоритет') }
    finally { setBusy(null) }
  }

  async function savePrioritySettings(event: FormEvent) {
    event.preventDefault()
    if (!prioritySettings) return
    try {
      await request('/orders/priority-settings', { method: 'PUT', body: JSON.stringify(prioritySettings) }, current.csrf_token)
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось сохранить настройки приоритета') }
  }

  async function createProblem(event: FormEvent) {
    event.preventDefault()
    if (problemOrder === null) return
    setBusy(problemOrder)
    try {
      await request('/blockers', { method: 'POST', body: JSON.stringify({ order_id: problemOrder, type_code: problemType, description: problemDescription }) }, current.csrf_token)
      setProblemOrder(null); setProblemDescription(''); await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось создать проблему') }
    finally { setBusy(null) }
  }

  async function updateProblem(blocker: Blocker, status: 'IN_PROGRESS' | 'RESOLVED' | 'CANCELLED') {
    setBusy(blocker.order_id)
    try { await request(`/blockers/${blocker.id}`, { method: 'PATCH', body: JSON.stringify({ status }) }, current.csrf_token); await refresh() }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось обновить проблему') }
    finally { setBusy(null) }
  }

  async function nextTask() {
    setNextBusy(true); setError('')
    try {
      const result = await request<Page>('/orders?limit=100&offset=0')
      const candidate = result.items.find(order => {
        if (order.internal_status === 'BLOCKED' || ['DONE', 'CANCELLED', 'HANDED_TO_SHIPPING', 'READY_TO_SHIP'].includes(order.internal_status)) return false
        const owned = order.assigned_user?.id === current.id
        const canTake = !order.assigned_user && current.permissions.includes('orders.change_status')
        return owned || canTake
      })
      if (!candidate) { setError('Подходящих задач сейчас нет. Проверьте «Мои задачи» или очередь.'); return }
      if (!candidate.assigned_user) await request(`/orders/${candidate.id}/claim`, { method: 'POST' }, current.csrf_token)
      const mineNow = await request<Page>(`/orders?assigned_user_id=${current.id}&limit=100&offset=0`)
      const selected = mineNow.items.find(order => order.id === candidate.id) ?? candidate
      setPage({ items: [selected], total: 1 }); setOffset(0)
      window.setTimeout(() => document.getElementById(`order-${candidate.id}`)?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 0)
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось найти следующую задачу') }
    finally { setNextBusy(false) }
  }

  async function createProcurement(blocker: Blocker, order: Order) {
    const material = window.prompt('Какой материал нужен?', blocker.description)
    if (!material?.trim()) return
    const quantity = window.prompt('Количество', '1')
    if (quantity === null) return
    const unit = window.prompt('Единица измерения', 'шт.')
    if (!unit?.trim()) return
    setBusy(blocker.order_id)
    try {
      await request('/procurement', { method: 'POST', body: JSON.stringify({
        material_name: material, quantity, unit, description: blocker.description,
        severity: blocker.severity, blocker_ids: [blocker.id], order_ids: [blocker.order_id],
        needed_by: blocker.expected_resolution_at ?? order.shipment_deadline,
      }) }, current.csrf_token)
      setError('Закупка создана. Отслеживайте её на экране «Закупки».')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось создать закупку') }
    finally { setBusy(null) }
  }

  function actions(order: Order): { label: string; status: string }[] {
    const own = order.assigned_user?.id === current.id
    if (!canAssign && !own) return []
    if (order.internal_status === 'NEW' && canAssign) return [{ label: 'В очередь', status: 'QUEUED' }]
    if (order.internal_status === 'QUEUED' || order.internal_status === 'SENT_TO_PRODUCTION') return [{ label: 'Начать производство', status: 'IN_PRODUCTION' }]
    if (order.internal_status === 'IN_PRODUCTION') return [{ label: 'Произведено', status: 'PRODUCED' }]
    if (order.internal_status === 'PRODUCED') return [{ label: 'Проверка качества', status: 'QUALITY_CHECK' }]
    if (order.internal_status === 'QUALITY_CHECK') return [{ label: 'На упаковку', status: 'PACKING' }]
    if (order.internal_status === 'PACKING') return [{ label: 'Готово', status: 'READY_TO_SHIP' }]
    if (order.internal_status === 'READY_TO_SHIP' && canAssign) return [{ label: 'Передан в доставку', status: 'HANDED_TO_SHIPPING' }]
    if (order.internal_status === 'HANDED_TO_SHIPPING' && canAssign) return [{ label: 'Завершить', status: 'DONE' }]
    return []
  }

  return <section className="space-y-4">
    <p role="status" className={`rounded-xl p-3 ${stale ? 'bg-amber-100 text-amber-950' : 'bg-slate-100'}`}>
      {stale ? 'Данные могут быть устаревшими. Ожидаем успешное обновление с сервера.' : 'Очередь загружена с сервера.'}
      {' '}Последнее успешное обновление: {lastUpdated ? new Date(lastUpdated).toLocaleString('ru-RU') : 'ещё не было'}
    </p>
    <button onClick={() => void refresh()} className="min-h-12 rounded-xl border bg-white px-4 py-3">Обновить очередь</button>
    <fieldset disabled={stale} className="min-w-0 space-y-4 disabled:opacity-70">
    <Scanner onOrder={id => { setSpecial(`order_id:${id}`); setStatus(''); setPriorityLevel(''); setSearch(''); setOzonStatus(''); setProduct(''); setWarehouse(''); setOffset(0); setError('') }}/><div className="flex items-center justify-between"><h2 className="text-2xl font-bold">{initialFilter === 'blocked' ? 'Проблемы' : mine ? 'Мои задачи' : 'Очередь'}</h2><button onClick={() => void refresh()} className="min-h-11 rounded-xl border bg-white px-4 py-3">Обновить</button></div>
    {shopWorker && <button disabled={nextBusy} onClick={() => void nextTask()} className="min-h-14 w-full rounded-2xl bg-blue-800 px-5 py-4 text-lg font-bold text-white shadow-sm disabled:opacity-50">{nextBusy ? 'Ищем задачу…' : 'Следующая задача'}</button>}
    <div className="grid gap-2 sm:grid-cols-2"><label className="text-sm sm:col-span-2">Поиск<input aria-label="Поиск заказов" placeholder="Отправление, заказ, SKU, offer_id, товар" value={search} onChange={event => { setSearch(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3" /></label><label className="text-sm">Статус<select value={status} onChange={event => { setStatus(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3"><option value="">Все</option>{statuses.map(entry => <option value={entry.code} key={entry.code}>{entry.display_name}</option>)}</select></label>
      <label className="text-sm">Приоритет<select value={priorityLevel} onChange={event => { setPriorityLevel(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3"><option value="">Все</option>{['P0', 'P1', 'P2', 'P3'].map(level => <option key={level}>{level}</option>)}</select></label><label className="text-sm">Показать<select value={special} onChange={event => { setSpecial(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3"><option value="">Все</option><option value="blocked">Проблемы</option><option value="ready">Готовые</option><option value="overdue">Просроченные</option></select></label>
      <label className="text-sm">Статус Ozon<input value={ozonStatus} onChange={event => { setOzonStatus(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3" /></label><label className="text-sm">Товар<input value={product} onChange={event => { setProduct(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3" /></label><label className="text-sm">Склад<input value={warehouse} onChange={event => { setWarehouse(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3" /></label>
      <label className="text-sm">Ответственный<select value={special.startsWith('assigned_user_id:') ? special.split(':')[1] : ''} onChange={event => { setSpecial(event.target.value ? `assigned_user_id:${event.target.value}` : ''); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3"><option value="">Все</option>{assignees.map(person => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label>
    </div>
    {canAssign && !mine && selected.length > 0 && <div className="flex flex-wrap items-end gap-2 rounded-xl bg-blue-50 p-3"><strong className="self-center">Выбрано: {selected.length}</strong><label className="text-sm">Назначить<select aria-label="Массовое назначение" defaultValue="" onChange={event => { if (event.target.value) void bulk('assign', Number(event.target.value)); event.target.value = '' }} className="ml-2 min-h-11 rounded border bg-white p-2"><option value="">Выбрать сотрудника</option><option value="-1">Снять назначение</option>{assignees.map(person => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label><label className="text-sm">Статус<select aria-label="Массовый статус" defaultValue="" onChange={event => { if (event.target.value) void bulk('status', event.target.value); event.target.value = '' }} className="ml-2 min-h-11 rounded border bg-white p-2"><option value="">Выбрать статус</option>{statuses.filter(s => s.code !== 'BLOCKED').map(s => <option key={s.code} value={s.code}>{s.display_name}</option>)}</select></label><button onClick={() => setSelected([])} className="min-h-11 rounded border px-3">Снять выбор</button></div>}
    {!shopWorker && current.permissions.includes('settings.manage') && <details className="rounded-xl bg-white p-3"><summary>Настроить статусы</summary><div className="mt-2 grid gap-2">{statuses.map(entry => <button key={entry.code} onClick={() => void editStatus(entry)} className="rounded border p-2 text-left">{entry.display_name} ({entry.code}) · {entry.sort_order}</button>)}</div></details>}
    {!shopWorker && current.permissions.includes('settings.manage') && prioritySettings && <details className="rounded-xl bg-white p-3"><summary>Настроить приоритет</summary><form onSubmit={event => void savePrioritySettings(event)} className="mt-3 grid gap-3 sm:grid-cols-2">{([
      ['deadline_weight', 'Срок отгрузки, %'], ['tariff_weight', 'Срок тарифа, %'], ['finance_weight', 'Денежный эффект и стоимость, %'], ['feasibility_weight', 'Возможность успеть, %'], ['high_impact_rub', 'Высокий эффект тарифа, ₽'], ['high_value_rub', 'Высокая стоимость заказа, ₽'],
    ] as const).map(([key, label]) => <label key={key} className="text-sm">{label}<input type="number" min={key.endsWith('_weight') ? 0 : 1} max={key.endsWith('_weight') ? 100 : undefined} step={key.endsWith('_weight') ? 1 : '0.01'} required value={prioritySettings[key]} onChange={event => setPrioritySettings({ ...prioritySettings, [key]: key.endsWith('_weight') ? Number(event.target.value) : event.target.value })} className="mt-1 w-full rounded-lg border p-3" /></label>)}<p className="self-center text-sm">Сумма весов: {prioritySettings.deadline_weight + prioritySettings.tariff_weight + prioritySettings.finance_weight + prioritySettings.feasibility_weight}%</p><button className="min-h-11 rounded-lg bg-blue-800 px-3 text-white">Сохранить</button></form></details>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}
    {!page.items.length && <p className="rounded-xl bg-white p-5">Заказов нет.</p>}
    {canAssign && !mine && page.items.length > 0 && <label className="flex items-center gap-2 rounded-lg bg-white p-3 text-sm"><input type="checkbox" checked={page.items.every(order => selected.includes(order.id))} onChange={event => setSelected(event.target.checked ? [...new Set([...selected, ...page.items.map(order => order.id)])] : selected.filter(id => !page.items.some(order => order.id === id)))} />Выбрать страницу</label>}
    {page.items.map(order => <article id={`order-${order.id}`} key={order.id} className="scroll-mt-4 rounded-2xl border bg-white p-4 shadow-sm sm:p-5"><div className="flex items-start justify-between gap-3"><div className="flex items-start gap-3">{canAssign && !mine && <input aria-label={`Выбрать заказ ${order.posting_number}`} type="checkbox" checked={selected.includes(order.id)} onChange={event => setSelected(event.target.checked ? [...selected, order.id] : selected.filter(id => id !== order.id))} className="mt-2 h-5 w-5" />}<div><h3 className="text-lg font-semibold">{order.items.map(item => `${item.product_name} × ${item.quantity}`).join(', ')}</h3><p className="mt-1 text-sm text-slate-600">{order.posting_number}</p>{!shopWorker && order.items.some(item => item.production_profile) && <p className="mt-2 text-sm text-slate-600">Норматив: {order.items.filter(item => item.production_profile).map(item => `${item.production_profile!.production_minutes} мин производство + ${item.production_profile!.packing_minutes} мин упаковка${item.quantity > 1 ? ` × ${item.quantity}` : ''}`).join('; ')}</p>}</div></div><span className="shrink-0 rounded-lg bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-900">{statuses.find(entry => entry.code === order.internal_status)?.display_name ?? labels[order.internal_status]}</span></div>
      {order.priority && <div className={`mt-3 rounded-xl border p-3 ${order.priority.blocked ? 'border-red-300 bg-red-50' : order.priority.level === 'P0' ? 'border-red-300 bg-red-50' : order.priority.level === 'P1' ? 'border-amber-300 bg-amber-50' : 'border-slate-200 bg-slate-50'}`}><p className="font-bold">{order.priority.level} · {order.priority.label}{order.priority.blocked ? ' · Заблокирован' : ''}{order.priority.pinned ? ' · Закреплён' : ''}</p><ul className="mt-2 list-disc pl-5 text-sm">{order.priority.reasons.map((reason, index) => <li key={index}>{reason}</li>)}</ul></div>}
      {!shopWorker && current.permissions.includes('finance.view') && order.tariff && <TariffTimeline tariff={order.tariff} />}
      <p className="mt-3 text-sm">Отгрузить до: <strong>{new Date(order.shipment_deadline).toLocaleString('ru-RU')}</strong></p>{!shopWorker && <p className="mt-1 text-sm">Ответственный: {order.assigned_user?.display_name || 'Не назначен'}</p>}
      {current.permissions.includes('orders.change_priority') && order.priority && !['DONE', 'CANCELLED', 'HANDED_TO_SHIPPING'].includes(order.internal_status) && <div className="mt-3 flex flex-wrap gap-3"><label className="text-sm">Ручной приоритет<select aria-label={`Приоритет ${order.posting_number}`} value={order.priority.manual_override ?? ''} disabled={busy === order.id} onChange={event => void changePriority(order, event.target.value || null, order.priority!.pinned)} className="ml-2 min-h-11 rounded-lg border p-2"><option value="">Автоматический</option>{['P0', 'P1', 'P2', 'P3', 'P4'].map(level => <option key={level} value={level}>{level}</option>)}</select></label><button disabled={busy === order.id} onClick={() => void changePriority(order, order.priority!.manual_override, !order.priority!.pinned)} className="min-h-11 rounded-lg border px-3">{order.priority.pinned ? 'Открепить' : 'Закрепить'}</button></div>}
      <div className="mt-4 grid gap-2 sm:grid-cols-2">{!order.assigned_user && ['NEW', 'QUEUED', 'SENT_TO_PRODUCTION'].includes(order.internal_status) && <button disabled={busy === order.id} onClick={() => void act(order, 'claim')} className="min-h-12 rounded-xl bg-blue-800 px-4 py-3 font-semibold text-white disabled:opacity-50">Взять в работу</button>}
        {actions(order).map(action => <button key={action.status} disabled={busy === order.id} onClick={() => void act(order, 'status', action.status)} className="min-h-12 rounded-xl bg-emerald-700 px-4 py-3 font-semibold text-white disabled:opacity-50">{action.label}</button>)}
        {current.permissions.includes('blockers.create') && ['QUEUED', 'SENT_TO_PRODUCTION', 'IN_PRODUCTION', 'QUALITY_CHECK', 'BLOCKED'].includes(order.internal_status) && <button onClick={() => setProblemOrder(order.id)} className="min-h-12 rounded-xl border border-red-300 px-4 py-3 font-semibold text-red-800">Проблема</button>}
      </div>{problemOrder === order.id && <form onSubmit={event => void createProblem(event)} className="mt-3 space-y-2 rounded-xl bg-red-50 p-3"><label className="block text-sm">Тип проблемы<select value={problemType} onChange={event => setProblemType(event.target.value)} className="mt-1 w-full rounded-xl border p-3">{blockerTypes.map(type => <option key={type.code} value={type.code}>{type.display_name}</option>)}</select></label><label className="block text-sm">Что случилось<textarea required maxLength={5000} value={problemDescription} onChange={event => setProblemDescription(event.target.value)} className="mt-1 w-full rounded-xl border p-3" /></label><button disabled={busy === order.id || !problemDescription.trim()} className="min-h-12 rounded-xl bg-red-700 px-4 py-3 font-semibold text-white">Сообщить о проблеме</button></form>}
      {blockers.filter(blocker => blocker.order_id === order.id).map(blocker => <div key={blocker.id} className="mt-3 rounded-xl border border-red-200 bg-red-50 p-3"><p className="font-semibold">Проблема #{blocker.id} · {blockerTypes.find(type => type.code === blocker.type_code)?.display_name ?? blocker.type_code} · {blocker.status}</p><p>{blocker.description}</p><Photos orderId={order.id} blockerId={blocker.id} current={current}/>{current.permissions.includes('procurement.create') && ['OPEN', 'IN_PROGRESS'].includes(blocker.status) && <button disabled={busy === order.id} onClick={() => void createProcurement(blocker, order)} className="mt-2 min-h-11 rounded-xl border border-blue-700 px-3 text-blue-800">Создать закупку</button>}{current.permissions.includes('blockers.resolve') && ['OPEN', 'IN_PROGRESS'].includes(blocker.status) && <div className="mt-2 flex gap-2">{blocker.status === 'OPEN' && <button disabled={busy === order.id} onClick={() => void updateProblem(blocker, 'IN_PROGRESS')} className="min-h-11 rounded-xl border p-2">Взять в работу</button>}<button disabled={busy === order.id} onClick={() => void updateProblem(blocker, 'RESOLVED')} className="min-h-11 rounded-xl bg-emerald-700 p-2 text-white">Решить</button><button disabled={busy === order.id} onClick={() => void updateProblem(blocker, 'CANCELLED')} className="min-h-11 rounded-xl border p-2">Отменить</button></div>}</div>)}
      {canAssign && !['DONE', 'CANCELLED'].includes(order.internal_status) && <label className="mt-4 block text-sm">Назначить сотрудника<select value={order.assigned_user?.id ?? ''} disabled={busy === order.id} onChange={event => void act(order, 'assignment', event.target.value ? Number(event.target.value) : null)} className="mt-1 w-full rounded-xl border p-3"><option value="">Не назначен</option>{assignees.map(user => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>}<Photos orderId={order.id} current={current}/><OrderQR orderId={order.id}/>{!shopWorker && <OrderTimeline orderId={order.id} current={current}/>}
    </article>)}
    <div className="flex items-center justify-between"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))} className="rounded-xl border bg-white px-4 py-3 disabled:opacity-40">Назад</button><span className="text-sm">{page.total ? `${offset + 1}–${Math.min(offset + 20, page.total)} из ${page.total}` : '0 заказов'}</span><button disabled={offset + 20 >= page.total} onClick={() => setOffset(offset + 20)} className="rounded-xl border bg-white px-4 py-3 disabled:opacity-40">Далее</button></div>
    </fieldset>
  </section>
}
