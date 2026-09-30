import { useCallback, useEffect, useState } from 'react'

type Bucket = { key: string; label: string; amount: string; order_count: number }
type Snapshot = { as_of: string; critical: number; blocked: number; ready: number; overdue: number;
  manager_tasks: number; money_at_risk?: { total: string; buckets: Bucket[] };
  attention: { id: number; posting_number: string; priority_level: string; reason: string }[];
  tasks: { id: number; title: string; severity: string; posting_number: string | null }[];
  workload: { id: number; name: string; active_orders: number }[] }
type Destination = 'queue' | 'manager-tasks' | 'money-at-risk'

function rubles(value: string) { return `${new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 2 }).format(Number(value))} ₽` }

export function Dashboard({ open }: { open: (destination: Destination, filter?: string) => void }) {
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/dashboard', { credentials: 'same-origin', cache: 'no-store' })
      if (!response.ok) throw new Error(`Ошибка ${response.status}`)
      setData(await response.json() as Snapshot); setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось загрузить сводку') }
  }, [])
  useEffect(() => { void refresh() }, [refresh])

  const card = (label: string, value: string | number, destination: Destination, filter?: string) =>
    <button onClick={() => open(destination, filter)} className="min-h-28 rounded-2xl border border-slate-200 bg-white p-5 text-left shadow-sm transition hover:border-blue-500 focus-visible:outline-2 focus-visible:outline-blue-700">
      <span className="block text-sm text-slate-600">{label}</span><strong className="mt-2 block text-3xl">{value}</strong><span className="mt-2 block text-xs text-blue-800">Открыть список →</span>
    </button>

  return <section className="space-y-6">
    <div className="flex items-center justify-between gap-3"><div><h2 className="text-2xl font-bold">Сейчас в производстве</h2><p className="text-sm text-slate-600">Сводка руководителя{data ? ` · ${new Date(data.as_of).toLocaleString('ru-RU')}` : ''}</p></div><button onClick={() => void refresh()} className="rounded-xl border bg-white px-4 py-3">Обновить</button></div>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}
    {!data && !error && <p role="status">Загрузка…</p>}
    {data && <>
      {data.money_at_risk && <div className="space-y-3 rounded-2xl bg-slate-900 p-5 text-white"><button onClick={() => open('money-at-risk')} className="w-full text-left"><span className="text-sm text-slate-300">Деньги под угрозой</span><strong className="mt-1 block text-3xl">{rubles(data.money_at_risk.total)}</strong><span className="text-xs text-slate-300">Открыть заказы →</span></button><div className="grid gap-2 sm:grid-cols-2">{data.money_at_risk.buckets.map(bucket => <button key={bucket.key} onClick={() => open('money-at-risk', bucket.key)} className="rounded-xl bg-slate-800 p-3 text-left hover:bg-slate-700"><span className="block text-sm">{bucket.label}</span><strong>{rubles(bucket.amount)}</strong><span className="block text-xs text-slate-300">{bucket.order_count} заказов →</span></button>)}</div></div>}
      <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">{card('Критические заказы', data.critical, 'queue', 'priority_level')}{card('Заблокированы', data.blocked, 'queue', 'blocked')}{card('Готовы к отгрузке', data.ready, 'queue', 'ready')}{card('Просрочены', data.overdue, 'queue', 'overdue')}</div>
      <div className="grid gap-4 lg:grid-cols-2"><div className="rounded-2xl bg-white p-5 shadow-sm"><div className="flex items-center justify-between gap-3"><h3 className="text-lg font-semibold">Требуют внимания сейчас</h3><button onClick={() => open('queue', 'priority_level')} className="text-sm text-blue-800">Очередь →</button></div>{data.attention.length ? <ul className="mt-3 space-y-2">{data.attention.map(order => <li key={order.id}><button onClick={() => open('queue', order.priority_level === 'P0' ? 'priority_level' : 'blocked')} className="w-full rounded-xl border p-3 text-left hover:border-blue-500"><strong>{order.posting_number} · {order.priority_level}</strong><span className="mt-1 block text-sm text-slate-600">{order.reason}</span></button></li>)}</ul> : <p className="mt-3 text-sm text-slate-600">Срочных заказов нет.</p>}</div>
      <div className="rounded-2xl bg-white p-5 shadow-sm"><button onClick={() => open('manager-tasks', 'ACTIVE')} className="w-full text-left"><h3 className="text-lg font-semibold">Задачи руководителя · {data.manager_tasks}</h3><span className="text-sm text-blue-800">Открыть активные задачи →</span></button>{data.tasks.length ? <ul className="mt-3 space-y-2">{data.tasks.map(task => <li key={task.id}><button onClick={() => open('manager-tasks', 'ACTIVE')} className="w-full rounded-xl border p-3 text-left hover:border-blue-500"><strong>{task.title}</strong><span className="block text-sm text-slate-600">{task.severity}{task.posting_number ? ` · ${task.posting_number}` : ''}</span></button></li>)}</ul> : <p className="mt-3 text-sm text-slate-600">Активных задач нет.</p>}</div></div>
      {data.workload.length > 0 && <div className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="font-semibold">Загрузка сотрудников</h3><div className="mt-3 grid gap-2 sm:grid-cols-2">{data.workload.map(person => <button key={person.id} onClick={() => open('queue', `assigned_user_id:${person.id}`)} className="rounded-xl bg-slate-50 p-3 text-left hover:bg-blue-50"><strong>{person.name}</strong><span className="block text-sm text-slate-600">Активных заказов: {person.active_orders} →</span></button>)}</div></div>}
    </>}
  </section>
}

