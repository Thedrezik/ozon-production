import { useEffect, useState } from 'react'

type Record = { id: number; user_id: number | null; action: string; entity_type: string | null; entity_id: string | null; old_value: unknown; new_value: unknown; timestamp: string; ip: string | null; user_agent: string | null }
const fields = [['user_id', 'ID пользователя'], ['action', 'Действие'], ['entity_type', 'Тип объекта'], ['entity_id', 'ID объекта'], ['since', 'С'], ['until', 'По']] as const

export function AuditLog() {
  const [filters, setFilters] = useState<{ [key: string]: string }>({})
  const [offset, setOffset] = useState(0)
  const [data, setData] = useState<{ items: Record[]; total: number }>({ items: [], total: 0 })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const query = new URLSearchParams({ limit: '25', offset: String(offset) })
    for (const [key, val] of Object.entries(filters)) if (val) query.set(key, key === 'since' || key === 'until' ? new Date(val).toISOString() : val)
    setLoading(true); setError('')
    fetch(`/api/audit?${query}`, { signal: controller.signal, cache: 'no-store', credentials: 'same-origin' })
      .then(async res => { if (!res.ok) throw new Error('Не удалось загрузить журнал'); return res.json() as Promise<{ items: Record[]; total: number }> })
      .then(result => { setData(result); setLoading(false) })
      .catch(cause => { if (!controller.signal.aborted) { setError(String(cause)); setLoading(false) } })
    return () => controller.abort()
  }, [filters, offset, revision])
  return <section className="space-y-4"><h2 className="text-xl font-semibold">Журнал аудита</h2>
    <div className="grid gap-3 sm:grid-cols-2">{fields.map(([key, label]) => <label key={key} className="text-sm">{label}<input type={key === 'since' || key === 'until' ? 'datetime-local' : key === 'user_id' ? 'number' : 'text'} min={key === 'user_id' ? 1 : undefined} value={filters[key] ?? ''} onChange={e => { setFilters(prev => ({ ...prev, [key]: e.target.value })); setOffset(0) }} className="block w-full rounded-lg border bg-white p-3" /></label>)}</div>
    <button onClick={() => setRevision(v => v + 1)} className="rounded-lg border bg-white p-3">Обновить</button>
    {error && <p role="alert">{error}</p>}{loading ? <p role="status">Загрузка…</p> : !error && <>
      <p>Всего: {data.total} · Страница {offset / 25 + 1}</p>
      {data.items.length === 0 && <p>Нет записей</p>}
      {data.items.map(row => <article key={row.id} className="space-y-2 rounded-xl bg-white p-4 shadow-sm"><p className="break-words font-semibold">{row.action}</p><p>{new Date(row.timestamp).toLocaleString()} · {row.user_id === null ? 'Система' : `Пользователь #${row.user_id}`}</p><p className="break-words">{row.entity_type} {row.entity_id} · {row.ip}</p><details><summary className="cursor-pointer py-2">Изменения</summary><pre className="overflow-auto whitespace-pre-wrap break-all text-xs">{JSON.stringify({ old: row.old_value, new: row.new_value }, null, 2)}</pre><p className="break-all text-xs">{row.user_agent}</p></details></article>)}
      <div className="flex gap-3"><button disabled={offset === 0} onClick={() => setOffset(v => v - 25)} className="rounded-lg border p-3 disabled:opacity-40">Назад</button><button disabled={offset + 25 >= data.total} onClick={() => setOffset(v => v + 25)} className="rounded-lg border p-3 disabled:opacity-40">Далее</button></div>
    </>}
  </section>
}
