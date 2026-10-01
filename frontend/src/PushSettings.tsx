import { useEffect, useState } from 'react'

async function request<T>(path: string, csrf?: string, body?: unknown, method = 'POST'): Promise<T> {
  const response = await fetch(`/api/push${path}`, { method: body ? method : 'GET', credentials: 'same-origin',
    headers: body ? { 'Content-Type': 'application/json', 'X-CSRF-Token': csrf ?? '' } : {},
    ...(body ? { body: JSON.stringify(body) } : {}) })
  if (!response.ok) throw new Error('Не удалось выполнить действие. Проверьте подключение и настройки сервера.')
  return response.json() as Promise<T>
}

export function PushSettings({ csrf }: { csrf?: string }) {
  const supported = window.isSecureContext && 'serviceWorker' in navigator && 'PushManager' in window && 'Notification' in window
  const [config, setConfig] = useState<{ enabled: boolean; public_key: string } | null>(null)
  const [subscription, setSubscription] = useState<PushSubscription | null>(null)
  const [message, setMessage] = useState('')
  const [busy, setBusy] = useState(false)
  useEffect(() => {
    if (!supported) return
    let active = true
    request<{ enabled: boolean; public_key: string }>('/config').then(value => { if (active) setConfig(value) }).catch(() => { if (active) setMessage('Не удалось загрузить настройки Web Push.') })
    navigator.serviceWorker.ready.then(registration => registration.pushManager.getSubscription()).then(value => { if (active) setSubscription(value) }).catch(() => {})
    return () => { active = false }
  }, [supported])
  async function enable() {
    setBusy(true); setMessage('')
    try {
      const registration = await navigator.serviceWorker.getRegistration()
      if (!registration?.active) throw new Error('PWA ещё не готова. Обновите страницу и повторите действие.')
      // This is called only by the explicit enable button, never on mount.
      if (await Notification.requestPermission() !== 'granted') throw new Error('Разрешение не выдано. Измените настройку уведомлений в браузере и попробуйте снова.')
      const key = Uint8Array.from(atob(config!.public_key.replace(/-/g, '+').replace(/_/g, '/')), char => char.charCodeAt(0))
      const value = await registration.pushManager.getSubscription() ?? await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: key })
      await request('/subscriptions', csrf, value.toJSON()); setSubscription(value)
      setMessage('Устройство подключено. Выберите ниже события Web Push; для теста включите NEW_ORDER.')
    } catch (error) { setMessage(error instanceof Error ? error.message : 'Не удалось включить уведомления.') }
    finally { setBusy(false) }
  }
  async function disable() {
    setBusy(true)
    try {
      await request('/subscriptions', csrf, { endpoint: subscription!.endpoint }, 'DELETE')
      await subscription!.unsubscribe(); setSubscription(null); setMessage('Уведомления на этом устройстве отключены.')
    } catch { setMessage('Не удалось отключить уведомления. Повторите действие.') }
    finally { setBusy(false) }
  }
  async function test() {
    setBusy(true)
    try { await request('/test', csrf, {}); setMessage('Тест поставлен в очередь. Для доставки включите Web Push для NEW_ORDER.') }
    catch { setMessage('Не удалось отправить тест.') }
    finally { setBusy(false) }
  }
  return <div className="rounded-xl bg-white p-4 space-y-3"><h3 className="font-semibold">Уведомления на этом устройстве</h3>
    <p className="text-sm">Получайте сообщения о проблемах и сроках, даже когда приложение закрыто. Разрешение браузера запрашивается по кнопке включения.</p>
    {!supported ? <p role="status">Web Push недоступен в этом браузере. Используйте HTTPS и браузер с поддержкой push; на iPhone откройте установленную PWA. Уведомления внутри приложения доступны.</p> : <>
      {config && !config.enabled && <p>Администратор ещё не настроил Web Push.</p>}
      <button className="min-h-11 rounded-lg border px-4" disabled={busy || !config?.enabled} onClick={() => void enable()}>{subscription ? 'Подключить подписку к аккаунту' : 'Включить Web Push'}</button>
      {subscription && <><button className="min-h-11 rounded-lg border px-4" disabled={busy} onClick={() => void disable()}>Отключить на устройстве</button><button className="min-h-11 rounded-lg border px-4" disabled={busy || !config?.enabled} onClick={() => void test()}>Тестовое уведомление</button></>}
    </>}{message && <p role="status">{message}</p>}
  </div>
}
