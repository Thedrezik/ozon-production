import { useFeatures, dateTime } from './features'
import { useCallback, useEffect, useState } from 'react'
import { Loading, StatusBadge } from './ui'
import { money } from './format'

type Bucket = { key: string; label: string; amount: string; order_count: number }
type Snapshot = { as_of: string; critical: number; blocked: number; ready: number; overdue: number;
  critical_problems: { id: number; order_id: number; posting_number: string; description: string }[];
  cancelled_after_start: { id: number; posting_number: string }[]; manager_tasks: number; money_at_risk?: { total: string; unpriced_count: number; buckets: Bucket[] };
  attention: { internal_status: string; items: { product_name: string; article: string | null; quantity: number }[]; assigned_user?: { display_name: string } | null; problems?: string[]; money_at_risk?: string | null; id: number; posting_number: string; priority_level: string; reason: string; shipment_deadline: string; next_tariff_at: string | null; financial_delta: string | null; currency: string | null }[];
  tasks: { id: number; title: string; severity: string; posting_number: string | null }[];
  workload: { id: number; name: string; active_orders: number }[] }
type Destination = 'queue' | 'manager-tasks' | 'money-at-risk'

const rubles = money

export function Dashboard({ open, refreshToken = 0 }: { open: (destination: Destination, filter?: string) => void; refreshToken?: number }) {
  const { optional, timezone } = useFeatures()
  const [data, setData] = useState<Snapshot | null>(null)
  const [error, setError] = useState('')
  const [now, setNow] = useState(Date.now())
  useEffect(() => { const timer = window.setInterval(() => setNow(Date.now()), 10_000); return () => clearInterval(timer) }, [])
  const remaining = (value: string) => { const minutes = Math.ceil((Date.parse(value) - now) / 60000); return minutes <= 0 ? 'срок наступил' : `${Math.floor(minutes / 60)} ч ${minutes % 60} мин` }
  const refresh = useCallback(async () => {
    try {
      const response = await fetch('/api/dashboard', { credentials: 'same-origin', cache: 'no-store' })
      if (!response.ok) throw new Error(`Ошибка ${response.status}`)
      setData(await response.json() as Snapshot); setError('')
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Не удалось загрузить сводку') }
  }, [])
  useEffect(() => { void refresh() }, [refresh, refreshToken])

  const card = (label: string, value: string | number, destination: Destination, filter?: string) =>
    <button onClick={() => open(destination, filter)} className="metric" data-active={value !== 0} data-tone={filter === 'ready' ? 'success' : filter === 'blocked' ? 'warning' : 'danger'}>
      <span>{label}</span><strong>{value}</strong>
    </button>

  return <section className="space-y-4">
    <div className="page-heading"><div><h2>Что делать сейчас</h2><p className="muted">Рабочий день{data ? ` · ${dateTime(data.as_of, timezone)}` : ''}</p></div><button onClick={() => void refresh()} className="btn btn-ghost btn-refresh">Обновить</button></div>
    {error && <p role="alert" className="state state-danger">{error}</p>}
    {!data && !error && <Loading label="Загружаем приоритеты…" />}
    {data && <>
      {data.cancelled_after_start.length > 0 && <div role="alert" className="cancellation"><h3 className="font-semibold">КРИТИЧЕСКАЯ ОТМЕНА OZON после начала производства</h3>{data.cancelled_after_start.map(row => <button key={row.id} className="btn btn-danger justify-start" onClick={() => open('queue', `order_id:${row.id}`)}>{row.posting_number} · Принять решение →</button>)}</div>}
      {data.critical_problems.length > 0 && <div className="panel problem-critical"><h3 className="font-semibold">Критические проблемы</h3>{data.critical_problems.map(problem => <button key={problem.id} className="attention-order mt-2" onClick={() => open('queue', `order_id:${problem.order_id}`)}><strong>{problem.posting_number}</strong><span className="whitespace-pre-wrap">{problem.description}</span></button>)}</div>}
      <div className="dashboard-grid">
        <div className="priority-workspace">
          <div className="workspace-heading"><h3>Требуют внимания сейчас</h3><button onClick={() => open('queue')} className="btn btn-ghost">Очередь →</button></div>
          {data.attention.length ? <ul className="attention-list">{data.attention.slice(0, 3).map((order, index) => <li key={order.id}>
            {index === 0 ? <article className="focus-order">
              <div className="focus-heading"><span className="eyebrow">В первую очередь</span><span className={`badge priority-${order.priority_level}`}>{order.priority_level}</span></div>
              <h3>{order.posting_number}</h3>
              {order.items.slice(0, 1).map((item, i) => <div className="focus-product" key={i}><p>{item.product_name}</p><span>{item.article ?? 'Без артикула'} · {item.quantity} шт.{order.items.length > 1 && ` · ещё товаров: ${order.items.length - 1}`}</span></div>)}
              <div className="focus-facts"><div><span>До отгрузки</span><strong>{remaining(order.shipment_deadline)}</strong></div>{order.money_at_risk !== undefined && <div><span>Деньги под угрозой</span><strong>{order.money_at_risk === null ? 'Неизвестно' : money(order.money_at_risk)}</strong></div>}</div>
              {order.next_tariff_at && <p className="focus-note">Тариф через {remaining(order.next_tariff_at)}{order.financial_delta !== null && ` · эффект ${money(order.financial_delta, order.currency ?? '')}`}</p>}
              {order.problems?.length ? <p className="focus-problem">Есть проблема · {order.problems[0]}</p> : !order.reason.startsWith('Отгрузка:') && <p className="focus-note">{order.reason}</p>}
              <div className="focus-footer"><div><StatusBadge status={order.internal_status} label={order.internal_status === 'BLOCKED' ? 'Есть проблема' : order.internal_status === 'IN_PRODUCTION' ? 'В работе' : ['PRODUCED', 'QUALITY_CHECK', 'PACKING'].includes(order.internal_status) ? 'Произведён' : 'Новый'} /><span className="focus-assignee">{order.assigned_user?.display_name ?? 'Без ответственного'}</span></div><button onClick={() => open('queue', `order_id:${order.id}`)} className="btn focus-open attention-order">Открыть заказ →</button></div>
            </article> : <button onClick={() => open('queue', `order_id:${order.id}`)} className="attention-order"><div className="attention-heading"><strong>{order.posting_number}</strong><span className={`badge priority-${order.priority_level}`}>{order.priority_level}</span></div><span className="attention-product">{order.items[0]?.product_name}</span><span className="muted">До отгрузки: {remaining(order.shipment_deadline)}{order.next_tariff_at && ` · тариф через ${remaining(order.next_tariff_at)}`}</span></button>}
          </li>)}</ul> : <div className="home-empty"><svg className="empty-mark" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M4 4h16v16H4M8 9h8M8 13h5M4 17l3 3 5-5" /></svg><h3>Срочных заказов нет</h3><p className="muted">Продолжайте работу по очереди.<br />Здесь появится следующий приоритетный заказ.</p><button className="btn" onClick={() => open('queue')}>Открыть очередь →</button></div>}
          {data.attention.length > 2 && <button className="btn btn-ghost all-priorities" onClick={() => open('queue')}>Все приоритеты →</button>}
        </div>
        <div className="dashboard-summary">
          {data.money_at_risk && <aside className="panel risk-panel"><span className="eyebrow">Финансовый риск</span><button onClick={() => open('money-at-risk')} className="risk-total"><span>Деньги под угрозой</span><strong>{rubles(data.money_at_risk.total)} <span aria-hidden="true">↗</span></strong></button><p className="muted">По подтверждённым тарифам</p><details className="risk-breakdown"><summary>Риск по времени</summary><div className="risk-buckets">{data.money_at_risk.buckets.map(bucket => <button key={bucket.key} onClick={() => open('money-at-risk', bucket.key)}><span>{bucket.label}<small className="muted block">{bucket.order_count} заказов</small></span><strong>{rubles(bucket.amount)} →</strong></button>)}</div></details>{data.money_at_risk.unpriced_count > 0 && <p role="status" className="muted risk-unknown">Без подтверждённой суммы: {data.money_at_risk.unpriced_count}. Не включены в денежный риск.</p>}</aside>}
          <div className="workflow-summary"><h3 className="eyebrow">Состояние производства</h3><div className="metrics">{card('Критические заказы', data.critical, 'queue', 'priority_level')}{card('Заблокированы', data.blocked, 'queue', 'blocked')}{card('Готовы к отгрузке', data.ready, 'queue', 'ready')}{card('Просрочены', data.overdue, 'queue', 'overdue')}</div></div>
        </div>
      </div>
      {optional.includes('manager_tasks') && <div className="panel"><button onClick={() => open('manager-tasks', 'ACTIVE')} className="btn">Задачи руководителя · {data.manager_tasks} →</button>{data.tasks.map(task => <p className="muted mt-2" key={task.id}>{task.title} · {task.severity}{task.posting_number ? ` · ${task.posting_number}` : ''}</p>)}</div>}
      {optional.includes('analytics') && data.workload.length > 0 && <div className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="font-semibold">Загрузка сотрудников</h3><div className="mt-3 grid gap-2 sm:grid-cols-2">{data.workload.map(person => <button key={person.id} onClick={() => open('queue', `assigned_user_id:${person.id}`)} className="rounded-xl bg-slate-50 p-3 text-left hover:bg-blue-50"><strong>{person.name}</strong><span className="block text-sm text-slate-600">Активных заказов: {person.active_orders} →</span></button>)}</div></div>}
    </>}
  </section>
}

