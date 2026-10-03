import { lazy, Suspense, useEffect, useState } from 'react'
import { useFeatures } from './features'
const PushSettings = lazy(() => import('./PushSettings').then(m => ({ default: m.PushSettings })))

type User = { csrf_token?: string }
type Notice = { id: number; type: string; title: string; body: string; url: string | null; created_at: string; read_at: string | null }
type Page = { items: Notice[]; unread: number }
type Prefs = { types: string[]; channels: string[]; mandatory_admin: string[]; items: { type: string; channel: string; enabled: boolean }[] }
type Telegram = { configured: boolean; linked: boolean; bot_username: string | null }

async function api<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const response = await fetch(`/api/notifications${path}`, { ...options, credentials: 'same-origin', cache: 'no-store',
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}) } })
  if (!response.ok) throw new Error((await response.json().catch(() => null) as { detail?: string } | null)?.detail ?? 'Ошибка загрузки')
  return response.json() as Promise<T>
}

export function Notifications({ current, refreshToken, open }: { current: User; refreshToken: number; open: (target: string) => void }) {
  const { optional } = useFeatures()
  const [page, setPage] = useState<Page>({ items: [], unread: 0 })
  const [prefs, setPrefs] = useState<Prefs | null>(null)
  const [error, setError] = useState('')
  const [telegram, setTelegram] = useState<Telegram | null>(null)
  const [linkUrl, setLinkUrl] = useState('')
  useEffect(() => { api<Page>('').then(setPage).catch(() => setError('Не удалось загрузить уведомления')) }, [refreshToken])
  useEffect(() => { if (optional.includes('notification_preferences')) api<Prefs>('/preferences').then(setPrefs).catch(() => setError('Не удалось загрузить настройки')) }, [optional])
  useEffect(() => { fetch('/api/telegram/status', { credentials: 'same-origin', cache: 'no-store' }).then(r => r.json()).then(setTelegram).catch(() => {}) }, [])
  async function linkTelegram() {
    try { const r = await fetch('/api/telegram/link', { method: 'POST', credentials: 'same-origin', headers: current.csrf_token ? { 'X-CSRF-Token': current.csrf_token } : {} }); const value = await r.json(); if (!r.ok) throw new Error(value.detail); setLinkUrl(value.url) }
    catch (e) { setError(e instanceof Error ? e.message : 'Не удалось создать ссылку') }
  }
  async function unlinkTelegram() {
    try { const r = await fetch('/api/telegram/link', { method: 'DELETE', credentials: 'same-origin', headers: current.csrf_token ? { 'X-CSRF-Token': current.csrf_token } : {} }); if (!r.ok) throw new Error(); setTelegram(value => value && ({ ...value, linked: false })); setLinkUrl('') }
    catch { setError('Не удалось отключить Telegram') }
  }
  async function read(id: number) {
    try { await api(`/${id}/read`, { method: 'POST' }, current.csrf_token); setPage(value => ({ ...value, unread: Math.max(0, value.unread - (value.items.find(item => item.id === id)?.read_at ? 0 : 1)), items: value.items.map(item => item.id === id ? { ...item, read_at: new Date().toISOString() } : item) })) }
    catch { setError('Не удалось отметить уведомление') }
  }
  async function toggle(type: string, channel: string, enabled: boolean) {
    try { const updated = await api<{ type: string; channel: string; enabled: boolean }>('/preferences', { method: 'PUT', body: JSON.stringify({ type, channel, enabled }) }, current.csrf_token)
      setPrefs(value => value && ({ ...value, items: [...value.items.filter(item => item.type !== type || item.channel !== channel), updated] })) }
    catch { setError('Не удалось сохранить настройку') }
  }
  return <section className="space-y-4"><h2 className="text-xl font-semibold">Уведомления · непрочитано {page.unread}</h2>{error && <p role="alert" className="text-red-700">{error}</p>}
    {page.items.length === 0 && <p>Уведомлений пока нет.</p>}
    {page.items.map(item => <article key={item.id} className={`rounded-xl bg-white p-4 shadow-sm ${item.read_at ? '' : 'border-l-4 border-blue-700'}`}>
      <p className="font-semibold">{item.title}</p><p className="mt-1 whitespace-pre-wrap text-sm">{item.body}</p><p className="mt-2 text-xs text-slate-500">{new Date(item.created_at).toLocaleString('ru-RU')}</p>
      <div className="mt-3 flex gap-3">{!item.read_at && <button className="rounded-lg border px-3 py-2 text-sm" onClick={() => read(item.id)}>Прочитано</button>}
        {item.url && <button className="rounded-lg border px-3 py-2 text-sm" onClick={() => { open(item.url!) }}>Открыть</button>}</div></article>)}
    {optional.includes('web_push') && <Suspense fallback={null}><PushSettings csrf={current.csrf_token} /></Suspense>}{telegram && <div className="rounded-xl bg-white p-4"><h3 className="font-semibold">Telegram · дополнительный канал</h3>{!telegram.configured ? <p className="mt-2 text-sm text-slate-500">Telegram не настроен на сервере.</p> : telegram.linked ? <div className="mt-2"><p className="text-sm">Аккаунт привязан.</p><button className="mt-2 rounded-lg border px-3 py-2" onClick={unlinkTelegram}>Отключить Telegram</button></div> : <div className="mt-2"><button className="rounded-lg border px-3 py-2" onClick={linkTelegram}>Привязать Telegram</button>{linkUrl && <p className="mt-2 text-sm">Откройте бота и нажмите Start: <a className="text-blue-700 underline" href={linkUrl} target="_blank" rel="noreferrer">Открыть @{telegram.bot_username}</a>. Ссылка действует 10 минут.</p>}</div>}</div>}{prefs && <details className="rounded-xl bg-white p-4"><summary className="font-semibold">Настройки уведомлений</summary><p className="mt-2 text-sm text-slate-500">Выберите события для Web Push и Telegram.</p>
      <div className="mt-3 space-y-3">{prefs.types.map(type => <div key={type} className="border-t pt-2"><p className="text-sm font-medium">{type}</p><div className="flex flex-wrap gap-3">{prefs.channels.map(channel => { const mandatory = channel === 'IN_APP' && prefs.mandatory_admin.includes(type); const enabled = mandatory || prefs.items.find(item => item.type === type && item.channel === channel)?.enabled || (channel === 'IN_APP' && !prefs.items.some(item => item.type === type && item.channel === channel)); return <label key={channel} className="text-sm"><input type="checkbox" checked={enabled} disabled={mandatory} onChange={event => toggle(type, channel, event.target.checked)} /> {channel}{mandatory ? ' · обязательно' : ''}</label> })}</div></div>)}</div></details>}
  </section>
}
