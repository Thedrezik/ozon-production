import { useEffect, useState } from 'react'

type Metric = { count: number; average_minutes: number | null }
type Page<T> = { items: T[]; total: number }
type Data = { timezone: string; intervals: Record<string, Metric>; throughput: Record<string, number>;
  blockers: { type_code: string; name: string; count: number; currently_open: number }[];
  sku: Page<{ sku: string | null; offer_id: string | null; orders: number; normative_minutes_per_unit: number | null; average_minutes: number }>;
  employees: Page<{ user_id: number; name: string; processed_orders: number }>;
  current_workload: Page<{ user_id: number; name: string; active_orders: number }>;
  prevented_financial_risk?: { amount: null; reason: string } }
const labels: Record<string, string> = { new_to_production: 'NEW → IN_PRODUCTION', production: 'IN_PRODUCTION → PRODUCED', produced_to_ready: 'PRODUCED → READY_TO_SHIP', cycle: 'Полный цикл: NEW → READY_TO_SHIP' }
const counts: Record<string, string> = { received: 'Получено', started: 'Начато', produced: 'Произведено', ready: 'Готово к отгрузке', overdue: 'Просрочено по дедлайну' }

export function Analytics({ refreshToken = 0 }: { refreshToken?: number }) {
  const today = new Date().toLocaleDateString('en-CA')
  const [start, setStart] = useState(today)
  const [end, setEnd] = useState(today)
  const [page, setPage] = useState(1)
  const [data, setData] = useState<Data | null>(null)
  const [error, setError] = useState('')
  useEffect(() => {
    const controller = new AbortController()
    setData(null)
    void fetch(`/api/analytics?start=${start}&end=${end}&page=${page}`, { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
      .then(async response => { if (!response.ok) throw new Error(`Ошибка ${response.status}`); return response.json() as Promise<Data> })
      .then(value => { setData(value); setError('') })
      .catch((cause: Error) => { if (!controller.signal.aborted) setError(cause.message) })
    return () => controller.abort()
  }, [start, end, page, refreshToken])
  return <section className="space-y-5"><h2 className="text-2xl font-bold">Аналитика производства</h2>
    <div className="flex flex-wrap gap-4"><label>С <input type="date" value={start} onChange={e => { setStart(e.target.value); setPage(1) }} className="rounded border p-3" /></label><label>По <input type="date" value={end} onChange={e => { setEnd(e.target.value); setPage(1) }} className="rounded border p-3" /></label></div>
    {error && <p role="alert">{error}</p>}
    {!data && !error && <p>Загрузка…</p>}
    {data && <><p className="text-sm text-slate-600">Даты включительно, часовой пояс: {data.timezone}. Интервалы относятся к дате завершения этапа; среднее в минутах, включая ожидание и блокировки. Цикл завершается готовностью к отгрузке. Отсутствующие или обратные timestamps исключены.</p>
      <div className="grid gap-3 sm:grid-cols-2">{Object.entries(data.intervals).map(([key, value]) => <div key={key} className="rounded-xl bg-white p-4 shadow-sm"><strong>{labels[key]}</strong><p>{value.average_minutes === null ? 'Нет данных' : `${value.average_minutes.toFixed(1)} мин`} · заказов: {value.count}</p></div>)}</div>
      <h3 className="font-semibold">Throughput за период</h3><div className="flex flex-wrap gap-4">{Object.entries(data.throughput).map(([key, value]) => <p key={key}>{counts[key]}: <strong>{value}</strong></p>)}</div>
      <p className="text-sm text-slate-600">Просрочки: дедлайн в выбранном периоде уже наступил, заказ не готов или готов после дедлайна; отменённые исключены.</p>
      <h3 className="font-semibold">Причины проблем</h3>{data.blockers.length ? data.blockers.map(row => <p key={row.type_code}>{row.name}: {row.count} · сейчас открыто: {row.currently_open}</p>) : <p>Нет данных</p>}
      <h3 className="font-semibold">Среднее время производства по SKU / offer_id</h3><p className="text-sm text-slate-600">Время всего отправления, один образец на SKU/offer_id в заказе; не время единицы изделия. Нормативы не подставляются вместо фактического времени.</p>
      {data.sku.items.length ? data.sku.items.map((row, i) => <p key={i}>{row.sku || 'Без SKU'} / {row.offer_id || 'Без offer_id'}: {row.average_minutes.toFixed(1)} мин · заказов: {row.orders} · норматив единицы: {row.normative_minutes_per_unit ?? "нет данных"} мин</p>) : <p>Нет данных</p>}
      <h3 className="font-semibold">Обработано сотрудниками</h3><p className="text-sm text-slate-600">Уникальные заказы с переходом в PRODUCED или READY_TO_SHIP, выполненным сотрудником в периоде.</p>{data.employees.items.map(row => <p key={row.user_id}>{row.name}: {row.processed_orders}</p>)}
      <h3 className="font-semibold">Текущая загрузка (на момент запроса)</h3>{data.current_workload.items.map(row => <p key={row.user_id}>{row.name}: {row.active_orders} активных заказов</p>)}
      <div className="flex gap-3"><button disabled={page === 1} onClick={() => setPage(page - 1)} className="rounded border p-3 disabled:opacity-40">Назад</button><span className="p-3">Страница {page}</span><button disabled={page * 20 >= Math.max(data.sku.total, data.employees.total, data.current_workload.total)} onClick={() => setPage(page + 1)} className="rounded border p-3 disabled:opacity-40">Далее</button></div>
      {data.prevented_financial_risk && <p>Предотвращённый финансовый риск: нет данных. {data.prevented_financial_risk.reason}</p>}
    </>}
  </section>
}
