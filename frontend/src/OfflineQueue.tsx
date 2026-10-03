import { readQueueSnapshot } from './offline'
import { useEffect, useState } from 'react'

export function OfflineQueue({ reconnecting, retry, forget }: { reconnecting: boolean; retry: () => void; forget: () => void }) {
  const [, tick] = useState(0)
  useEffect(() => { const timer = window.setInterval(() => tick(value => value + 1), 30_000); return () => window.clearInterval(timer) }, [])
  const snapshot = readQueueSnapshot()
  return <section className="space-y-4">
    <div role="status" className="state state-warning">
      <p className="text-lg font-semibold">OFFLINE · Нет связи с сервером</p>
      <p>Данные могут быть устаревшими. Доступен только просмотр. Изменения не сохраняются и не отправляются позже.</p>
      <p>{reconnecting ? 'Проверяем соединение…' : 'После восстановления связи очередь обновится с сервера.'}</p>
    </div>
    <button disabled={reconnecting} onClick={retry} className="btn">Проверить соединение</button>
    <button onClick={forget} className="btn btn-ghost">Закрыть и удалить offline-данные</button>
    {snapshot ? <>
      <h2 className="text-lg font-semibold">{snapshot.title} · Последняя загруженная страница</h2>
      <p>Последнее успешное обновление: <time dateTime={snapshot.savedAt}>{new Date(snapshot.savedAt).toLocaleString('ru-RU')}</time>. Приоритеты и сроки показаны на этот момент.</p>
      <p className="text-sm">Сохранено {snapshot.items.length} из {snapshot.total} заказов, начиная с {snapshot.offset + 1}. Фильтры и другие страницы недоступны offline. Снимок хранится до часа в этой вкладке.</p>
      {snapshot.items.map(row => <article key={row.posting_number} className="rounded-2xl bg-white p-4 shadow-sm">
        <h3 className="font-bold">{row.posting_number}</h3>
        <p>Производство: {row.internal_status} · Ozon: {row.ozon_status}</p>
        {row.priority && <p>Приоритет на момент обновления: {row.priority.level} · {row.priority.label}</p>}
        <p>Срок отгрузки: {new Date(row.shipment_deadline).toLocaleString('ru-RU')}</p>
        {row.items.map((item, index) => <p key={index}>{item.product_name} × {item.quantity}</p>)}
      </article>)}
    </> : <p>Нет сохранённой очереди или срок хранения истёк. Для входа и загрузки данных необходимо соединение.</p>}
  </section>
}
