import { useEffect, useState } from 'react'

type Current = { id: number; csrf_token?: string; permissions: string[] }
type Task = { id: number; source_type: string; order_id: number | null; posting_number: string | null;
  title: string; description: string; severity: string; status: string; assigned_to: number | null;
  assignee_name: string | null; created_at: string; due_at: string | null }
type Assignee = { id: number; display_name: string; is_active: boolean; permissions: string[] }

const sources = ['BLOCKER', 'DEADLINE_RISK', 'STALLED_ORDER', 'UNASSIGNED_ORDER', 'PROCUREMENT_OVERDUE',
  'OZON_CANCELLED_AFTER_START', 'OZON_SYNC_ERROR', 'API_KEY_EXPIRING']
const sourceNames: Record<string, string> = {
  BLOCKER: 'Проблема', DEADLINE_RISK: 'Риск срока', STALLED_ORDER: 'Заказ без движения',
  UNASSIGNED_ORDER: 'Нет ответственного', PROCUREMENT_OVERDUE: 'Просрочена закупка',
  OZON_CANCELLED_AFTER_START: 'Отмена после начала', OZON_SYNC_ERROR: 'Ошибка Ozon', API_KEY_EXPIRING: 'Ключ Ozon',
}
const severityNames: Record<string, string> = { LOW: 'Низкая', MEDIUM: 'Средняя', HIGH: 'Высокая', CRITICAL: 'Критическая' }
const statusNames: Record<string, string> = { OPEN: 'Открыта', IN_PROGRESS: 'В работе', RESOLVED: 'Решена', DISMISSED: 'Отклонена' }

async function request<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', cache: 'no-store',
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) } })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail ?? `Ошибка ${response.status}`)
  }
  return response.json() as Promise<T>
}

export function ManagerTasks({ current, initialStatus = 'OPEN', refreshToken = 0 }: { current: Current; initialStatus?: string; refreshToken?: number }) {
  const [items, setItems] = useState<Task[]>([])
  const [people, setPeople] = useState<Assignee[]>([])
  const [severity, setSeverity] = useState('')
  const [source, setSource] = useState('')
  const [assignee, setAssignee] = useState('')
  const [status, setStatus] = useState(initialStatus)
  const [total, setTotal] = useState(0)
  const [offset, setOffset] = useState(0)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState<number | null>(null)

  useEffect(() => {
    request<{ items: Assignee[] }>('/users?limit=100').then(result => setPeople(result.items.filter(
      user => user.is_active && user.permissions.includes('manager_tasks.manage')))).catch(() => setPeople([]))
  }, [])
  useEffect(() => {
    const params = new URLSearchParams({ limit: '20', offset: String(offset) })
    if (severity) params.set('severity', severity)
    if (source) params.set('source_type', source)
    if (assignee) params.set('assigned_to', assignee)
    if (status) params.set('status', status)
    request<{ items: Task[]; total: number }>(`/manager-tasks?${params}`).then(result => {
      setItems(result.items); setTotal(result.total); setNotice('')
    }).catch(() => setNotice('Не удалось загрузить задачи'))
  }, [severity, source, assignee, status, offset, refreshToken])

  async function update(task: Task, next: 'IN_PROGRESS' | 'RESOLVED' | 'DISMISSED') {
    setBusy(task.id)
    try {
      await request(`/manager-tasks/${task.id}`, { method: 'PATCH', body: JSON.stringify({ status: next }) }, current.csrf_token)
      setNotice('Задача обновлена')
      const params = new URLSearchParams({ limit: '20', offset: String(offset) })
      if (severity) params.set('severity', severity)
      if (source) params.set('source_type', source)
      if (assignee) params.set('assigned_to', assignee)
      if (status) params.set('status', status)
      const result = await request<{ items: Task[]; total: number }>(`/manager-tasks?${params}`)
      setItems(result.items); setTotal(result.total)
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
    finally { setBusy(null) }
  }

  return <section className="space-y-4"><h2 className="text-xl font-semibold">Задачи руководителя</h2>
    <div className="grid gap-2 rounded-2xl bg-white p-4 sm:grid-cols-2">
      <label className="text-sm">Статус<select aria-label="Статус задачи" value={status} onChange={e => { setStatus(e.target.value); setOffset(0) }} className="mt-1 w-full rounded-lg border p-3"><option value="">Все</option><option value="ACTIVE">Активные</option>{Object.entries(statusNames).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
      <label className="text-sm">Важность<select aria-label="Важность задачи" value={severity} onChange={e => { setSeverity(e.target.value); setOffset(0) }} className="mt-1 w-full rounded-lg border p-3"><option value="">Любая</option>{Object.entries(severityNames).map(([key, value]) => <option key={key} value={key}>{value}</option>)}</select></label>
      <label className="text-sm">Причина<select aria-label="Причина задачи" value={source} onChange={e => { setSource(e.target.value); setOffset(0) }} className="mt-1 w-full rounded-lg border p-3"><option value="">Любая</option>{sources.map(key => <option key={key} value={key}>{sourceNames[key]}</option>)}</select></label>
      <label className="text-sm">Ответственный<select aria-label="Ответственный за задачу" value={assignee} onChange={e => { setAssignee(e.target.value); setOffset(0) }} className="mt-1 w-full rounded-lg border p-3"><option value="">Все</option>{people.map(person => <option key={person.id} value={person.id}>{person.display_name}</option>)}</select></label>
    </div>
    {notice && <p role="status" className="rounded-lg bg-amber-50 p-3">{notice}</p>}
    <p className="text-sm text-slate-600">Задач: {total}</p>
    {items.map(task => <article key={task.id} className="rounded-2xl bg-white p-5 shadow-sm">
      <div className="flex flex-wrap items-start justify-between gap-2"><h3 className="font-semibold">{task.title}</h3><span className={task.severity === 'CRITICAL' ? 'font-bold text-red-700' : 'text-slate-700'}>{severityNames[task.severity]}</span></div>
      <p className="mt-1 text-sm text-slate-600">{sourceNames[task.source_type] ?? task.source_type} · {statusNames[task.status]}{task.posting_number ? ` · ${task.posting_number}` : ''}</p>
      <p className="mt-3 whitespace-pre-wrap">{task.description}</p>
      <p className="mt-2 text-sm text-slate-600">Ответственный: {task.assignee_name ?? 'Не назначен'}{task.due_at ? ` · Срок: ${new Date(task.due_at).toLocaleString('ru-RU')}` : ''}</p>
      {current.permissions.includes('manager_tasks.manage') && ['OPEN', 'IN_PROGRESS'].includes(task.status) && <div className="mt-4 flex flex-wrap gap-2">
        {task.status === 'OPEN' && <button disabled={busy === task.id} onClick={() => void update(task, 'IN_PROGRESS')} className="min-h-11 rounded-xl bg-blue-800 px-4 text-white">Взять в работу</button>}
        {task.source_type !== 'BLOCKER' && <button disabled={busy === task.id} onClick={() => void update(task, 'RESOLVED')} className="min-h-11 rounded-xl border px-4">Решено</button>}
        <button disabled={busy === task.id} onClick={() => void update(task, 'DISMISSED')} className="min-h-11 rounded-xl border px-4">Отклонить</button>
      </div>}
    </article>)}
    {!items.length && <p className="rounded-xl bg-white p-5">Нет задач по выбранным фильтрам.</p>}
    <div className="flex gap-2"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))} className="rounded-lg border bg-white px-4 py-2 disabled:opacity-40">Назад</button><button disabled={offset + items.length >= total} onClick={() => setOffset(offset + 20)} className="rounded-lg border bg-white px-4 py-2 disabled:opacity-40">Далее</button></div>
  </section>
}
