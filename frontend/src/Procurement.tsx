import { useCallback, useEffect, useState, type FormEvent } from 'react'

type Current = { id: number; csrf_token?: string; permissions: string[] }
type Task = { id: number; material_name: string; quantity: string; unit: string; description: string;
  severity: string; status: string; responsible_user_id: number | null; responsible_name: string | null;
  needed_by: string | null; is_overdue: boolean; order_ids: number[]; blocker_ids: number[] }
type Person = { id: number; display_name: string; is_active: boolean; permissions: string[] }
type History = { old_status: string | null; new_status: string; description: string; created_at: string; actor_name: string | null }

const statuses: Record<string, string> = { NEW: 'Новая', ORDERED: 'Заказана', PURCHASED: 'Куплена', DELIVERED: 'Доставлена', CANCELLED: 'Отменена' }
const next: Record<string, string[]> = { NEW: ['ORDERED', 'PURCHASED', 'DELIVERED', 'CANCELLED'], ORDERED: ['PURCHASED', 'DELIVERED', 'CANCELLED'], PURCHASED: ['DELIVERED', 'CANCELLED'] }

async function request<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', cache: 'no-store',
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) } })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `Ошибка ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function Procurement({ current }: { current: Current }) {
  const [items, setItems] = useState<Task[]>([])
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [mine, setMine] = useState(false)
  const [status, setStatus] = useState('')
  const [overdue, setOverdue] = useState(false)
  const [people, setPeople] = useState<Person[]>([])
  const [material, setMaterial] = useState('')
  const [quantity, setQuantity] = useState('1')
  const [unit, setUnit] = useState('шт.')
  const [description, setDescription] = useState('')
  const [severity, setSeverity] = useState('MEDIUM')
  const [neededBy, setNeededBy] = useState('')
  const [responsible, setResponsible] = useState(String(current.id))
  const [orderIds, setOrderIds] = useState('')
  const [blockerIds, setBlockerIds] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState<number | null>(null)
  const [history, setHistory] = useState<Record<number, History[]>>({})

  const refresh = useCallback(async () => {
    const params = new URLSearchParams({ limit: '20', offset: String(offset) })
    if (mine) params.set('mine', 'true')
    if (status) params.set('status', status)
    if (overdue) params.set('overdue', 'true')
    const result = await request<{ items: Task[]; total: number }>(`/procurement?${params}`)
    setItems(result.items); setTotal(result.total)
  }, [mine, status, overdue, offset])
  useEffect(() => { void refresh().catch(() => setNotice('Не удалось загрузить закупки')) }, [refresh])
  useEffect(() => {
    if (!current.permissions.includes('users.view')) return
    void request<{ items: Person[] }>('/users?limit=100').then(result => setPeople(result.items.filter(
      person => person.is_active && person.permissions.includes('procurement.manage')))).catch(() => {})
  }, [current.permissions])

  function ids(value: string): number[] { return [...new Set(value.split(/[\s,]+/).filter(Boolean).map(Number))] }
  async function create(event: FormEvent) {
    event.preventDefault(); setNotice('')
    try {
      await request('/procurement', { method: 'POST', body: JSON.stringify({
        material_name: material, quantity, unit, description, severity,
        responsible_user_id: responsible ? Number(responsible) : null,
        needed_by: neededBy ? new Date(neededBy).toISOString() : null,
        order_ids: ids(orderIds), blocker_ids: ids(blockerIds),
      }) }, current.csrf_token)
      setMaterial(''); setDescription(''); setOrderIds(''); setBlockerIds(''); setNotice('Закупка создана')
      await refresh()
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка создания') }
  }
  async function update(task: Task, nextStatus: string) {
    setBusy(task.id)
    try {
      await request(`/procurement/${task.id}`, { method: 'PATCH', body: JSON.stringify({ status: nextStatus }) }, current.csrf_token)
      setNotice(nextStatus === 'DELIVERED' && task.blocker_ids.length ? 'Материал доставлен. Проверьте связанные проблемы и закройте их вручную.' : 'Закупка обновлена')
      await refresh()
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
    finally { setBusy(null) }
  }
  async function showHistory(id: number) {
    try { const result = await request<{ items: History[] }>(`/procurement/${id}/history`); setHistory(value => ({ ...value, [id]: result.items })) }
    catch { setNotice('Не удалось загрузить историю') }
  }
  async function addLinks(id: number) {
    const raw = window.prompt('Номера заказов через запятую (можно оставить пустым)')
    if (raw === null) return
    const blockers = window.prompt('Номера проблем через запятую (можно оставить пустым)')
    if (blockers === null) return
    try {
      await request(`/procurement/${id}/links`, { method: 'POST', body: JSON.stringify({ order_ids: ids(raw), blocker_ids: ids(blockers) }) }, current.csrf_token)
      setNotice('Связи добавлены'); await refresh()
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
  }
  async function assign(task: Task, userId: string) {
    try {
      await request(`/procurement/${task.id}/responsible`, { method: 'PUT', body: JSON.stringify({ responsible_user_id: userId ? Number(userId) : null }) }, current.csrf_token)
      setNotice('Ответственный изменён'); await refresh()
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
  }

  return <section className="space-y-4"><h2 className="text-xl font-semibold">Закупки</h2>
    {current.permissions.includes('procurement.create') && <details className="rounded-2xl bg-white p-5 shadow-sm"><summary className="cursor-pointer font-semibold">Новая закупка</summary>
      <form onSubmit={event => void create(event)} className="mt-4 grid gap-3">
        <label>Материал<input required maxLength={240} value={material} onChange={e => setMaterial(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
        <div className="grid grid-cols-2 gap-2"><label>Количество<input required type="number" min="0.001" max="999999999.999" step="0.001" value={quantity} onChange={e => setQuantity(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label><label>Единица<input required maxLength={40} value={unit} onChange={e => setUnit(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label></div>
        <label>Описание<textarea maxLength={5000} value={description} onChange={e => setDescription(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
        <label>Важность<select value={severity} onChange={e => setSeverity(e.target.value)} className="mt-1 w-full rounded-lg border p-3"><option value="LOW">Низкая</option><option value="MEDIUM">Средняя</option><option value="HIGH">Высокая</option><option value="CRITICAL">Критическая</option></select></label>
        <label>Нужно к<input type="datetime-local" value={neededBy} onChange={e => setNeededBy(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
        <label>Ответственный<select value={responsible} onChange={e => setResponsible(e.target.value)} className="mt-1 w-full rounded-lg border p-3"><option value="">Не назначен</option><option value={current.id}>Я</option>{people.filter(p => p.id !== current.id).map(p => <option key={p.id} value={p.id}>{p.display_name}</option>)}</select></label>
        <label>Номера заказов через запятую<input value={orderIds} onChange={e => setOrderIds(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
        <label>Номера проблем через запятую<input value={blockerIds} onChange={e => setBlockerIds(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
        <button className="min-h-12 rounded-xl bg-blue-800 px-4 text-white">Создать закупку</button>
      </form></details>}
    <div className="grid gap-2 rounded-2xl bg-white p-4 sm:grid-cols-3"><label>Статус<select value={status} onChange={e => { setStatus(e.target.value); setOffset(0) }} className="mt-1 w-full rounded-lg border p-3"><option value="">Все</option>{Object.entries(statuses).map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label><label className="flex items-center gap-2"><input type="checkbox" checked={mine} onChange={e => { setMine(e.target.checked); setOffset(0) }} />Мои закупки</label><label className="flex items-center gap-2"><input type="checkbox" checked={overdue} onChange={e => { setOverdue(e.target.checked); setOffset(0) }} />Просроченные</label></div>
    {notice && <p role="status" className="rounded-lg bg-amber-50 p-3">{notice}</p>}
    <p className="text-sm text-slate-600">Закупок: {total}</p>
    {items.map(task => <article key={task.id} className="rounded-2xl bg-white p-5 shadow-sm"><div className="flex flex-wrap justify-between gap-2"><h3 className="font-semibold">#{task.id} · {task.material_name}</h3>{task.is_overdue && <strong className="text-red-700">Просрочена</strong>}</div><p>{task.quantity} {task.unit} · {statuses[task.status]} · {task.severity}</p><p className="text-sm text-slate-600">Ответственный: {task.responsible_name ?? 'Не назначен'}{task.needed_by ? ` · Нужно к ${new Date(task.needed_by).toLocaleString('ru-RU')}` : ''}</p><p className="mt-2 whitespace-pre-wrap">{task.description}</p><p className="mt-2 text-sm text-slate-600">Заказы: {task.order_ids.join(', ') || '—'} · Проблемы: {task.blocker_ids.join(', ') || '—'}</p>
      {current.permissions.includes('procurement.manage') && <div className="mt-3 flex flex-wrap gap-2">{(next[task.status] ?? []).map(value => <button key={value} disabled={busy === task.id} onClick={() => void update(task, value)} className="min-h-11 rounded-xl border px-3">{statuses[value]}</button>)}{next[task.status] && <button onClick={() => void addLinks(task.id)} className="min-h-11 rounded-xl border px-3">Связать с заказом</button>}</div>}
      {current.permissions.includes('procurement.manage') && next[task.status] && <label className="mt-3 block text-sm">Ответственный<select value={task.responsible_user_id ?? ''} onChange={e => void assign(task, e.target.value)} className="mt-1 w-full rounded-lg border p-3"><option value="">Не назначен</option><option value={current.id}>Я</option>{people.filter(p => p.id !== current.id).map(p => <option key={p.id} value={p.id}>{p.display_name}</option>)}</select></label>}
      <button onClick={() => void showHistory(task.id)} className="mt-3 min-h-11 text-sm underline">История изменений</button>{history[task.id] && <ol className="space-y-1 text-sm">{history[task.id].map((entry, index) => <li key={index}>{new Date(entry.created_at).toLocaleString('ru-RU')} · {entry.actor_name ?? 'Система'} · {entry.description}</li>)}</ol>}
      {task.status === 'DELIVERED' && task.blocker_ids.length > 0 && <p className="mt-2 rounded-lg bg-amber-50 p-3 text-sm">Материал доставлен. Проверьте связанные проблемы в заказах и закройте их вручную.</p>}
    </article>)}
    {!items.length && <p className="rounded-xl bg-white p-5">Закупок нет.</p>}
    <div className="flex gap-2"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))} className="rounded-lg border bg-white px-4 py-2 disabled:opacity-40">Назад</button><button disabled={offset + items.length >= total} onClick={() => setOffset(offset + 20)} className="rounded-lg border bg-white px-4 py-2 disabled:opacity-40">Далее</button></div>
  </section>
}
