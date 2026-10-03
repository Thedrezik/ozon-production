import { useCallback, useEffect, useState } from 'react'
import { Loading } from './ui'
import { money } from './format'

type Bucket = { key: string; label: string; amount: string; order_count: number; starts_at?: string; ends_at?: string }
type Summary = { timezone: string; as_of: string; total: string; already_degraded: Bucket; buckets: Bucket[]; categories: Record<string, string>; unpriced_count: number }
type Order = { id: number; posting_number: string; internal_status: string; priority_level: string; amount: string; at: string; category?: string }
type OrderPage = { items: Order[]; total: number; amount: string }

const categories: Record<string, string> = {
  CAN_STILL_SAVE: 'Можно успеть', HIGH_RISK: 'Высокий риск',
  BLOCKED_RISK: 'Заблокировано', ALREADY_DEGRADED: 'Уже ухудшилось',
}

const rubles = money

async function get<T>(path: string): Promise<T> {
  const response = await fetch(`/api/money-at-risk${path}`, { credentials: 'same-origin', cache: 'no-store' })
  if (!response.ok) throw new Error(`Не удалось загрузить данные (${response.status})`)
  return response.json() as Promise<T>
}

export function MoneyAtRisk({ initialBucket = '', refreshToken = 0 }: { initialBucket?: string; refreshToken?: number }) {
  const [summary, setSummary] = useState<Summary | null>(null)
  const [selected, setSelected] = useState<string | null>(initialBucket || null)
  const [category, setCategory] = useState('')
  const [offset, setOffset] = useState(0)
  const [orders, setOrders] = useState<OrderPage | null>(null)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)

  const refresh = useCallback(async () => {
    try { setSummary(await get<Summary>('')); setError('') }
    catch (cause) { setError(cause instanceof Error ? cause.message : 'Ошибка загрузки') }
  }, [])
  useEffect(() => { void refresh() }, [refresh, refreshToken])
  useEffect(() => {
    if (!selected) return
    let active = true
    get<OrderPage>(`/orders?bucket=${encodeURIComponent(selected)}&category=${encodeURIComponent(category)}&offset=${offset}&as_of=${encodeURIComponent(summary?.as_of ?? '')}`.replace('&category=&', '&'))
      .then(result => { if (active) { setOrders(result); setError('') } })
      .catch(cause => { if (active) setError(cause instanceof Error ? cause.message : 'Ошибка загрузки') })
    return () => { active = false }
  }, [selected, category, offset, summary?.as_of])

  function open(key: string) { setSelected(key); setCategory(''); setOffset(0); setOrders(null) }
  async function reload() { setBusy(true); await refresh(); setBusy(false) }
  return <section className="space-y-4">
    <div className="page-heading"><h2>Деньги под угрозой</h2><button onClick={() => void reload()} disabled={busy} className="btn">Обновить</button></div>
    {error && <p role="alert" className="rounded-xl bg-red-50 p-3 text-red-800">{error}</p>}
    {!summary && !error && <Loading />}
    {summary && <>
      <div className="panel"><p className="muted">Предотвратимое ухудшение до конца завтрашнего дня</p><p className="mt-1 text-2xl font-semibold">{rubles(summary.total)}</p><p className="mt-2 muted">Часовой пояс: {summary.timezone} · на {new Date(summary.as_of).toLocaleString('ru-RU', { timeZone: summary.timezone })}</p></div>
      <div className="grid gap-3 sm:grid-cols-2">{summary.buckets.map(bucket => <button key={bucket.key} onClick={() => open(bucket.key)} className="min-h-24 rounded-2xl border border-slate-200 bg-white p-4 text-left shadow-sm hover:border-blue-500 focus-visible:outline-2 focus-visible:outline-blue-700" aria-expanded={selected === bucket.key}><span className="block text-sm text-slate-600">{bucket.label}</span><span className="mt-1 block text-xl font-bold">{rubles(bucket.amount)}</span><span className="text-sm text-slate-600">{bucket.order_count} заказов · открыть</span></button>)}</div>
      <div className="rounded-2xl bg-white p-4"><h3 className="font-semibold">По состоянию заказов</h3><div className="mt-3 grid gap-2 sm:grid-cols-2">{Object.entries(categories).map(([key, label]) => <div key={key} className="rounded-xl bg-slate-50 p-3"><span className="block text-sm text-slate-600">{label}</span><strong>{rubles(summary.categories[key])}</strong></div>)}</div><button onClick={() => open('already_degraded')} className="mt-3 min-h-11 w-full rounded-xl border border-amber-300 bg-amber-50 px-4 text-left font-medium text-amber-900">Уже ухудшилось: {rubles(summary.already_degraded.amount)} · {summary.already_degraded.order_count} заказов · открыть</button></div>
      {summary.unpriced_count > 0 && <p className="text-sm text-slate-600">Нет подтверждённой суммы для части тарифных ступеней ({summary.unpriced_count}). Они не включены в рублёвый показатель.</p>}
      {selected && <div className="rounded-2xl border border-blue-200 bg-white p-4"><div className="flex items-center justify-between gap-2"><h3 className="text-lg font-semibold">{[...summary.buckets, summary.already_degraded].find(bucket => bucket.key === selected)?.label}</h3><button onClick={() => setSelected(null)} className="min-h-11 rounded-lg border px-3">Закрыть</button></div>
        {selected !== 'already_degraded' && <label className="mt-3 block text-sm">Состояние<select value={category} onChange={event => { setCategory(event.target.value); setOffset(0); setOrders(null) }} className="mt-1 min-h-11 w-full rounded-lg border p-2"><option value="">Все</option>{Object.entries(categories).filter(([key]) => key !== 'ALREADY_DEGRADED').map(([key, label]) => <option key={key} value={key}>{label}</option>)}</select></label>}
        {!orders && <p role="status" className="mt-3">Загрузка заказов…</p>}
        {orders && <><p className="mt-3 text-sm text-slate-600">{orders.total} заказов · {rubles(orders.amount)}</p>{orders.items.length === 0 && <p className="mt-3">Заказов нет.</p>}<ul className="mt-3 space-y-2">{orders.items.map(order => <li key={order.id} className="rounded-xl border bg-slate-50 p-3"><strong>Заказ {order.posting_number}</strong><p className="text-sm">{categories[order.category ?? 'ALREADY_DEGRADED']} · {order.priority_level} · {rubles(order.amount)}</p><p className="text-xs text-slate-600">{new Date(order.at).toLocaleString('ru-RU', { timeZone: summary.timezone })}</p></li>)}</ul><div className="mt-3 flex items-center justify-between"><button disabled={offset === 0} onClick={() => setOffset(Math.max(0, offset - 20))} className="min-h-11 rounded-lg border px-3 disabled:opacity-40">Назад</button><button disabled={offset + 20 >= orders.total} onClick={() => setOffset(offset + 20)} className="min-h-11 rounded-lg border px-3 disabled:opacity-40">Далее</button></div></>}
      </div>}
    </>}
  </section>
}
