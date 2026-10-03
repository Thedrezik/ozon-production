import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Loading } from './ui'

type Status = { connection_state: string; last_successful_sync: string | null; last_webhook: string | null; recent_error_count: number; expires_at: string | null; checked_at: string | null; rotation_available: boolean }
export function OzonIntegration({ csrf, refreshToken }: { csrf?: string; refreshToken: number }) {
  const [status, setStatus] = useState<Status | null>(null)
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  async function load() {
    const response = await fetch('/api/ozon/integration', { cache: 'no-store' })
    if (!response.ok) throw new Error('Не удалось загрузить статус интеграции')
    setStatus(await response.json() as Status)
  }
  useEffect(() => { load().catch(error => setNotice(String(error))) }, [refreshToken])
  async function submit(event: FormEvent<HTMLFormElement>, rotation: boolean) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true
    const form = event.currentTarget
    const data = new FormData(form)
    const date = String(data.get('expires_at') || '')
    const payload: Record<string, string | null> = { expires_at: date ? new Date(date).toISOString() : null }
    if (rotation) {
      payload.api_key = String(data.get('api_key'))
      const id = String(data.get('client_id') || '')
      if (id) payload.client_id = id
    }
    setBusy(true); setNotice('')
    try {
      const response = await fetch(`/api/ozon/integration/${rotation ? 'credentials' : 'expiration'}`, {
        method: 'PUT', headers: { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf || '' }, body: JSON.stringify(payload),
      })
      if (!response.ok) throw new Error(rotation ? 'Проверка или сохранение не удались. Текущие credentials сохранены.' : 'Не удалось сохранить срок')
      setNotice(rotation ? 'Новый ключ проверен и сохранён' : 'Срок сохранён')
      await load()
    } catch (error) { setNotice(String(error)) }
    finally { form.reset(); payload.api_key = null; payload.client_id = null; submitting.current = false; setBusy(false) }
  }
  const date = (value: string | null) => value ? new Date(value).toLocaleString() : 'Нет данных'
  return <section className="panel space-y-4">
    <h2 className="text-xl font-semibold">Интеграция Ozon</h2>
    {!status && !notice && <Loading />}
    {status && <dl className="space-y-2"><dt>Соединение</dt><dd>{status.connection_state}</dd><dt>Последняя успешная синхронизация</dt><dd>{date(status.last_successful_sync)}</dd><dt>Последний webhook</dt><dd>{date(status.last_webhook)}</dd><dt>Ошибки за 24 часа</dt><dd>{status.recent_error_count}</dd><dt>Ключ проверен</dt><dd>{date(status.checked_at)}</dd><dt>Истекает</dt><dd>{date(status.expires_at)}</dd></dl>}
    <form onSubmit={event => submit(event, true)} className="space-y-3">
      <h3 className="font-semibold">Заменить credentials</h3>
      <p className="text-sm text-slate-600">Новый ключ проверяется перед сохранением. В Mock Mode проверка обращается к настоящему Ozon API; производство остаётся в Mock Mode.</p>
      <label className="block">Новый Client ID (пусто — сохранить текущий)<input name="client_id" type="password" autoComplete="off" className="mt-1 w-full rounded-lg border p-3" /></label>
      <label className="block">Новый API Key<input name="api_key" type="password" autoComplete="off" required className="mt-1 w-full rounded-lg border p-3" /></label>
      <label className="block">Срок действия<input name="expires_at" type="datetime-local" className="mt-1 w-full rounded-lg border p-3" /></label>
      <button disabled={busy || !status?.rotation_available} className="rounded-lg bg-blue-800 px-4 py-3 text-white disabled:opacity-50">Проверить и заменить</button>
      {status && !status.rotation_available && <p>Для замены требуется настройка шифрования на сервере.</p>}
    </form>
    <form onSubmit={event => submit(event, false)} className="space-y-3">
      <label className="block">Изменить только срок (пусто — удалить)<input name="expires_at" type="datetime-local" className="mt-1 w-full rounded-lg border p-3" /></label>
      <button disabled={busy} className="rounded-lg border px-4 py-3">Сохранить срок</button>
    </form>
    {notice && <p role="status">{notice}</p>}
  </section>
}
