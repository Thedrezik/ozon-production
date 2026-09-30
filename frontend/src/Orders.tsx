import { useCallback, useEffect, useState, type FormEvent } from 'react'

type User = { id: number; csrf_token?: string; permissions: string[] }
type Order = { id: number; posting_number: string; shipment_deadline: string; internal_status: string; ozon_status: string; items: { product_name: string; quantity: number }[]; assigned_user: { id: number; display_name: string } | null }
type Page = { items: Order[]; total: number }
type Assignee = { id: number; display_name: string; is_active: boolean; permissions: string[] }
type Status = { code: string; display_name: string; sort_order: number }
type TimelineItem = { id: string; kind: 'comment' | 'system'; body: string; author: string | null; created_at: string }

const labels: Record<string, string> = {
  NEW: 'Новый', QUEUED: 'В очереди', SENT_TO_PRODUCTION: 'Передан в производство',
  IN_PRODUCTION: 'В производстве', BLOCKED: 'Проблема', PRODUCED: 'Произведён',
  QUALITY_CHECK: 'Проверка качества', PACKING: 'Упаковка', READY_TO_SHIP: 'Готов к отгрузке', HANDED_TO_SHIPPING: 'Передан в доставку', DONE: 'Завершён', CANCELLED: 'Отменён',
}

async function request<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', cache: 'no-store',
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) } })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Ошибка ${response.status}`)
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
      <p>{item.body}</p><p className="mt-1 text-xs text-slate-500">{item.kind === 'system' ? 'Событие системы' : item.author} · {new Date(item.created_at).toLocaleString('ru-RU')}</p>
    </li>)}</ol>
    {canComment && <form onSubmit={event => void submit(event)} className="mt-3 space-y-2"><label className="sr-only" htmlFor={`comment-${orderId}`}>Комментарий</label><textarea id={`comment-${orderId}`} value={body} onChange={event => setBody(event.target.value)} maxLength={5000} required placeholder="Написать комментарий…" className="w-full rounded-xl border bg-white p-3"/><button disabled={!body.trim()} className="min-h-11 rounded-xl bg-blue-800 px-4 py-2 font-semibold text-white disabled:opacity-50">Добавить комментарий</button></form>}
  </details>
}

export function Orders({ current, mine }: { current: User; mine: boolean }) {
  const [page, setPage] = useState<Page>({ items: [], total: 0 })
  const [status, setStatus] = useState('')
  const [special, setSpecial] = useState('')
  const [offset, setOffset] = useState(0)
  const [busy, setBusy] = useState<number | null>(null)
  const [error, setError] = useState('')
  const [assignees, setAssignees] = useState<Assignee[]>([])
  const [statuses, setStatuses] = useState<Status[]>([])
  const canAssign = current.permissions.includes('orders.assign')

  const refresh = useCallback(async () => {
    const params = new URLSearchParams({ limit: '20', offset: String(offset) })
    if (mine) params.set('assigned_user_id', String(current.id))
    if (status) params.set('status', status)
    if (special) params.set(special, 'true')
    try { setPage(await request<Page>(`/orders?${params}`)); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось загрузить очередь') }
  }, [mine, current.id, offset, status, special])

  useEffect(() => { void refresh() }, [refresh])
  const refreshStatuses = useCallback(() => { void request<Status[]>('/orders/statuses').then(setStatuses).catch(() => {}) }, [])
  useEffect(() => { refreshStatuses() }, [refreshStatuses])
  useEffect(() => {
    if (!canAssign) return
    request<{ items: Assignee[] }>('/users?limit=100').then(result => setAssignees(result.items.filter(user => user.is_active && user.permissions.includes('orders.change_status')))).catch(() => setAssignees([]))
  }, [canAssign])
  useEffect(() => {
    const source = new EventSource('/api/orders/events')
    source.addEventListener('orders', () => { void refresh(); refreshStatuses() })
    return () => source.close()
  }, [refresh, refreshStatuses])

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
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось обновить заказ') }
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

  return <section className="space-y-4"><div className="flex items-center justify-between"><h2 className="text-2xl font-bold">{mine ? 'Мои задачи' : 'Очередь'}</h2><button onClick={() => void refresh()} className="rounded-xl border bg-white px-4 py-3">Обновить</button></div>
    <div className="grid grid-cols-2 gap-2"><label className="text-sm">Статус<select value={status} onChange={event => { setStatus(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3"><option value="">Все</option>{statuses.map(entry => <option value={entry.code} key={entry.code}>{entry.display_name}</option>)}</select></label>
      <label className="text-sm">Показать<select value={special} onChange={event => { setSpecial(event.target.value); setOffset(0) }} className="mt-1 w-full rounded-xl border bg-white p-3"><option value="">Все</option><option value="blocked">Проблемы</option><option value="ready">Готовые</option><option value="overdue">Просроченные</option></select></label></div>
    {current.permissions.includes('settings.manage') && <details className="rounded-xl bg-white p-3"><summary>Настроить статусы</summary><div className="mt-2 grid gap-2">{statuses.map(entry => <button key={entry.code} onClick={() => void editStatus(entry)} className="rounded border p-2 text-left">{entry.display_name} ({entry.code}) · {entry.sort_order}</button>)}</div></details>}
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}
    {!page.items.length && <p className="rounded-xl bg-white p-5">Заказов нет.</p>}
    {page.items.map(order => <article key={order.id} className="rounded-2xl border bg-white p-5 shadow-sm"><div className="flex items-start justify-between gap-3"><div><h3 className="text-lg font-semibold">{order.items.map(item => `${item.product_name} × ${item.quantity}`).join(', ')}</h3><p className="mt-1 text-sm text-slate-600">{order.posting_number}</p></div><span className="rounded-lg bg-blue-50 px-2 py-1 text-xs font-semibold text-blue-900">{statuses.find(entry => entry.code === order.internal_status)?.display_name ?? labels[order.internal_status]}</span></div>
      <p className="mt-3 text-sm">Отгрузить до: <strong>{new Date(order.shipment_deadline).toLocaleString('ru-RU')}</strong></p><p className="mt-1 text-sm">Ответственный: {order.assigned_user?.display_name || 'Не назначен'}</p>
      <div className="mt-4 grid gap-2 sm:grid-cols-2">{!order.assigned_user && ['NEW', 'QUEUED', 'SENT_TO_PRODUCTION'].includes(order.internal_status) && <button disabled={busy === order.id} onClick={() => void act(order, 'claim')} className="min-h-12 rounded-xl bg-blue-800 px-4 py-3 font-semibold text-white disabled:opacity-50">Взять в работу</button>}
        {actions(order).map(action => <button key={action.status} disabled={busy === order.id} onClick={() => void act(order, 'status', action.status)} className="min-h-12 rounded-xl bg-emerald-700 px-4 py-3 font-semibold text-white disabled:opacity-50">{action.label}</button>)}
        {['QUEUED', 'SENT_TO_PRODUCTION', 'IN_PRODUCTION'].includes(order.internal_status) && <button onClick={() => window.alert('Сообщение о проблеме появится в следующей версии. Обратитесь к руководителю.')} className="min-h-12 rounded-xl border border-red-300 px-4 py-3 font-semibold text-red-800">Проблема</button>}
      </div>{canAssign && !['DONE', 'CANCELLED'].includes(order.internal_status) && <label className="mt-4 block text-sm">Назначить сотрудника<select value={order.assigned_user?.id ?? ''} disabled={busy === order.id} onChange={event => void act(order, 'assignment', event.target.value ? Number(event.target.value) : null)} className="mt-1 w-full rounded-xl border p-3"><option value="">Не назначен</option>{assignees.map(user => <option key={user.id} value={user.id}>{user.display_name}</option>)}</select></label>}<OrderTimeline orderId={order.id} current={current}/>
    </article>)}
    <div className="flex items-center justify-between"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))} className="rounded-xl border bg-white px-4 py-3 disabled:opacity-40">Назад</button><span className="text-sm">{page.total ? `${offset + 1}–${Math.min(offset + 20, page.total)} из ${page.total}` : '0 заказов'}</span><button disabled={offset + 20 >= page.total} onClick={() => setOffset(offset + 20)} className="rounded-xl border bg-white px-4 py-3 disabled:opacity-40">Далее</button></div>
  </section>
}
