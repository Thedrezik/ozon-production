import { lazy, Suspense, useEffect, useRef, useState, type FormEvent } from 'react'
const MoneyAtRisk = lazy(() => import('./MoneyAtRisk').then(m => ({ default: m.MoneyAtRisk })))
import { Dashboard } from './Dashboard'
const Notifications = lazy(() => import('./Notifications').then(m => ({ default: m.Notifications })))
const OzonIntegration = lazy(() => import('./OzonIntegration').then(m => ({ default: m.OzonIntegration })))
import { OzonSyncStatus } from './OzonSyncStatus'
import { OfflineQueue } from './OfflineQueue'
import { clearQueueSnapshot, readQueueSnapshot } from './offline'

const Orders = lazy(() => import('./Orders').then(m => ({ default: m.Orders })))
const ManagerTasks = lazy(() => import('./ManagerTasks').then(m => ({ default: m.ManagerTasks })))
const Procurement = lazy(() => import('./Procurement').then(m => ({ default: m.Procurement })))
const ProductProfiles = lazy(() => import('./ProductProfiles').then(m => ({ default: m.ProductProfiles })))
const Analytics = lazy(() => import('./Analytics').then(m => ({ default: m.Analytics })))
const AuditLog = lazy(() => import('./AuditLog').then(m => ({ default: m.AuditLog })))

import { CoreOrders } from './CoreOrders'
import { FeatureContext } from './features'
import { Loading, NavIcon } from './ui'

type User = { id: number; username: string; display_name: string; is_active: boolean; roles: string[]; permissions: string[]; csrf_token?: string }
type Health = { mock_mode: boolean }

async function api<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options, signal: options.signal ?? AbortSignal.timeout(12_000), cache: 'no-store', credentials: 'same-origin',
    headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}), ...options.headers },
  })
  if (!response.ok) {
    const body = await response.json().catch(() => null) as { detail?: string } | null
    throw new Error(body?.detail || `Ошибка ${response.status}`)
  }
  return response.json() as Promise<T>
}

function Login({ onLogin }: { onLogin: (user: User) => void }) {
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  async function submit(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true; setBusy(true); setError('')
    try { onLogin(await api<User>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })) }
    catch (cause) { setError(cause instanceof Error && cause.message === 'Invalid credentials' ? 'Неверный логин или пароль' : 'Не удалось войти. Попробуйте позже.') }
    finally { submitting.current = false; setBusy(false) }
  }
  return <section className="panel login-panel"><h2 className="mb-5 text-xl font-semibold">Вход</h2><form onSubmit={submit} className="space-y-4">
    <label className="block text-sm font-medium">Логин<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
    <label className="block text-sm font-medium">Пароль<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
    {error && <p role="alert" className="text-red-700">{error}</p>}<button disabled={busy} aria-busy={busy} className="btn btn-primary w-full">{busy ? 'Входим…' : 'Войти'}</button>
  </form></section>
}

function Users({ current }: { current: User }) {
  const [users, setUsers] = useState<User[]>([])
  const [roles, setRoles] = useState<string[]>([])
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [password, setPassword] = useState('')
  const [newRole, setNewRole] = useState('PRODUCTION_WORKER')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)

  async function refresh() {
    const [result, names] = await Promise.all([api<{ items: User[] }>('/users'), api<string[]>('/roles')])
    setUsers(result.items); setRoles(names.filter(r => ['ADMIN', 'PRODUCTION_WORKER'].includes(r) || (r === 'SUPER_ADMIN' && current.roles.includes(r))))
  }
  useEffect(() => { api<{ items: User[] }>('/users').then(r => setUsers(r.items)).catch(() => setNotice('Не удалось загрузить пользователей')); api<string[]>('/roles').then(names => setRoles(names.filter(r => ['ADMIN', 'PRODUCTION_WORKER'].includes(r) || (r === 'SUPER_ADMIN' && current.roles.includes(r))))).catch(() => setNotice('Не удалось загрузить роли')) }, [current.roles])

  async function create(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true; setBusy(true); setNotice('')
    try {
      await api('/users', { method: 'POST', body: JSON.stringify({ username, display_name: displayName, password, roles: [newRole] }) }, current.csrf_token)
      setUsername(''); setDisplayName(''); setPassword(''); setNotice('Пользователь создан'); await refresh()
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
    finally { submitting.current = false; setBusy(false) }
  }
  async function changeRoles(user: User, role: string) {
    const next = user.roles.includes(role) ? user.roles.filter(r => r !== role) : [...user.roles, role]
    if (!next.length) return
    try { await api(`/users/${user.id}/roles`, { method: 'PUT', body: JSON.stringify({ roles: next }) }, current.csrf_token); setNotice('Роли обновлены'); await refresh() }
    catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
  }
  async function deactivate(user: User) {
    if (!window.confirm(`Отключить ${user.display_name}?`)) return
    try { await api(`/users/${user.id}/deactivate`, { method: 'POST' }, current.csrf_token); setNotice('Пользователь отключён'); await refresh() }
    catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
  }
  return <section className="space-y-5"><h2 className="text-xl font-semibold">Пользователи</h2>{notice && <p role="status" className="rounded-lg bg-amber-50 p-3">{notice}</p>}
    {current.permissions.includes('users.create') && <form onSubmit={create} className="space-y-3 rounded-2xl bg-white p-5 shadow-sm"><h3 className="font-semibold">Новый пользователь</h3>
      <input aria-label="Логин" placeholder="Логин" required value={username} onChange={e => setUsername(e.target.value)} className="w-full rounded-lg border p-3" />
      <input aria-label="Имя" placeholder="Имя" required value={displayName} onChange={e => setDisplayName(e.target.value)} className="w-full rounded-lg border p-3" />
      <input aria-label="Пароль" placeholder="Пароль от 12 символов" type="password" minLength={12} required value={password} onChange={e => setPassword(e.target.value)} className="w-full rounded-lg border p-3" />
      <label className="block text-sm">Роль<select value={newRole} onChange={e => setNewRole(e.target.value)} className="mt-1 w-full rounded-lg border p-3">{roles.filter(r => r !== 'SUPER_ADMIN' || current.roles.includes('SUPER_ADMIN')).map(r => <option key={r}>{r}</option>)}</select></label>
      <button disabled={busy} aria-busy={busy} className="btn btn-primary">{busy ? 'Создаём…' : 'Создать'}</button></form>}
    {users.map(user => <article key={user.id} className="rounded-2xl bg-white p-5 shadow-sm"><div className="flex justify-between gap-2"><div><h3 className="font-semibold">{user.display_name}</h3><p className="text-sm text-slate-500">{user.username} · {user.is_active ? 'Активен' : 'Отключён'}</p></div>{current.permissions.includes('users.manage') && user.is_active && user.id !== current.id && <button onClick={() => deactivate(user)} className="rounded-lg border px-3 text-sm text-red-700">Отключить</button>}</div>
      <div className="mt-4 flex flex-wrap gap-3">{roles.map(role => <label key={role} className="flex min-h-11 items-center gap-2 text-sm"><input type="checkbox" checked={user.roles.includes(role)} disabled={!current.permissions.includes('users.manage') || (role === 'SUPER_ADMIN' && !current.roles.includes('SUPER_ADMIN'))} onChange={() => changeRoles(user, role)} /> {role}</label>)}</div></article>)}
  </section>
}

function Account({ current }: { current: User }) {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const submitting = useRef(false)
  async function change(event: FormEvent) {
    event.preventDefault()
    if (submitting.current) return
    submitting.current = true; setBusy(true)
    try { await api('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: oldPassword, new_password: newPassword }) }, current.csrf_token); setOldPassword(''); setNewPassword(''); setNotice('Пароль изменён') }
    catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
    finally { submitting.current = false; setBusy(false) }
  }
  return <section className="rounded-2xl bg-white p-5 shadow-sm"><h2 className="text-xl font-semibold">Профиль</h2><p className="mt-2">{current.display_name} · {current.username}</p><p className="text-sm text-slate-500">Роли: {current.roles.join(', ')}</p><form onSubmit={change} className="mt-6 space-y-3"><h3 className="font-semibold">Сменить пароль</h3><input aria-label="Текущий пароль" type="password" autoComplete="current-password" required value={oldPassword} onChange={e => setOldPassword(e.target.value)} className="w-full rounded-lg border p-3" /><input aria-label="Новый пароль" type="password" autoComplete="new-password" minLength={12} required value={newPassword} onChange={e => setNewPassword(e.target.value)} className="w-full rounded-lg border p-3" /><button disabled={busy} aria-busy={busy} className="btn btn-primary">{busy ? 'Сохраняем…' : 'Сохранить'}</button></form>{notice && <p role="status" className="mt-3">{notice}</p>}</section>
}

type Screen = 'dashboard' | 'queue' | 'feed' | 'mine' | 'problems' | 'manager-tasks' | 'procurement' | 'product-profiles' | 'money-at-risk' | 'users' | 'account' | 'notifications' | 'ozon-integration' | 'analytics' | 'audit'

export function App() {
  const [offline, setOffline] = useState(!navigator.onLine)
  const [reconnecting, setReconnecting] = useState(false)
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [health, setHealth] = useState<Health | null>(null)
  const [features, setFeatures] = useState({ optional: [] as string[], timezone: 'Europe/Moscow' })
  const [refreshToken, setRefreshToken] = useState(0)
  const [page, setPage] = useState<Screen>('dashboard')
  const [filter, setFilter] = useState('')
  const [problemCount, setProblemCount] = useState(0)
  const checkRef = useRef<(refresh?: boolean) => void>(() => {})
  const stateRef = useRef({ user, offline })
  stateRef.current = { user, offline }
  const has = (name: string) => features.optional.includes(name)
  const admin = user?.roles.some(role => ['ADMIN', 'SUPER_ADMIN'].includes(role)) ?? false
  function open(destination: 'queue' | 'manager-tasks' | 'money-at-risk', selected = '') { setFilter(selected); setPage(destination) }
  function openNotice(path: string) {
    const order = path.match(/^\/orders\/(\d+)$/)
    const task = path.match(/^\/manager-tasks\/(\d+)$/)
    if (order) open('queue', `order_id:${order[1]}`)
    else if (task && has('manager_tasks')) open('manager-tasks', `task_id:${task[1]}`)
    else if (path === '/ozon-integration' && admin) setPage('ozon-integration')
    else setPage('notifications')
  }
  useEffect(() => { api<Health>('/health').then(setHealth).catch(() => {}) }, [])
  // One session/recovery timer. SSE is primary; this also refreshes read-time risk.
  useEffect(() => {
    let stopped = false
    let checking = false
    let cachedConfig: { optional: string[]; timezone: string } | null = null
    const invalid = () => { clearQueueSnapshot(); setUser(null); setOffline(false) }
    const disconnected = () => { setOffline(true); setLoading(false) }
    async function check(refreshData = true) {
      if (checking || stopped) return
      if (!navigator.onLine) { disconnected(); return }
      checking = true; setReconnecting(true)
      try {
        const response = await fetch('/api/auth/me', { cache: 'no-store', credentials: 'same-origin', signal: AbortSignal.timeout(12_000) })
        if (stopped) return
        if (response.status === 401 || response.status === 403) { invalid(); return }
        if (!response.ok) throw new Error('Server unavailable')
        const value = await response.json() as User
        const config = cachedConfig ?? await api<{ optional: string[]; timezone: string }>('/features')
        cachedConfig = config
        if (stopped || !navigator.onLine) return
        const snapshot = readQueueSnapshot()
        if (snapshot && (snapshot.owner !== value.id || !value.permissions.includes('orders.view'))) clearQueueSnapshot()
        if (!stateRef.current.user) {
          setPage(snapshot?.owner === value.id ? 'queue' : 'dashboard')
          const match = window.location.pathname.match(/^\/orders\/(\d+)$/)
          if (match) { setFilter(`order_id:${match[1]}`); setPage('queue') }
        }
        setFeatures(config); setUser(value); setOffline(false)
        if (stateRef.current.user && (refreshData || stateRef.current.offline)) setRefreshToken(v => v + 1)
      } catch { if (!stopped) disconnected() }
      finally { checking = false; if (!stopped) { setLoading(false); setReconnecting(false) } }
    }
    checkRef.current = (refresh = true) => { void check(refresh) }
    void check()
    const recover = () => { void check() }
    const fallback = () => {
      if (!stateRef.current.user || stateRef.current.offline) void check()
      else setRefreshToken(v => v + 1)
    }
    window.addEventListener('online', recover)
    window.addEventListener('offline', disconnected)
    window.addEventListener('backend-unavailable', disconnected)
    window.addEventListener('session-invalid', invalid)
    window.addEventListener('focus', recover)
    const timer = window.setInterval(fallback, 60_000)
    return () => { stopped = true; clearInterval(timer); window.removeEventListener('online', recover); window.removeEventListener('offline', disconnected); window.removeEventListener('backend-unavailable', disconnected); window.removeEventListener('session-invalid', invalid); window.removeEventListener('focus', recover) }
  }, [])
  const userId = user?.id
  useEffect(() => {
    if (!userId || offline) return
    const source = new EventSource('/api/orders/events')
    let pending: number | undefined
    let checkpoint: string | null = null
    const refresh = () => {
      if (pending !== undefined) return
      pending = window.setTimeout(() => { pending = undefined; setRefreshToken(v => v + 1) }, 150)
    }
    let checkedAt = 0
    const error = () => { if (Date.now() - checkedAt > 20_000) { checkedAt = Date.now(); checkRef.current(false) } }
    source.addEventListener('ready', event => {
      const version = (event as MessageEvent<string>).data
      if (checkpoint !== null && checkpoint !== version) refresh()
      checkpoint = version
    })
    source.addEventListener('orders', event => {
      checkpoint = (event as MessageEvent<string>).lastEventId
      refresh()
    })
    // Periodic authenticated SSE closure keeps security checks; opening a stream
    // does not independently reload the whole page every twenty seconds.
    source.addEventListener('error', error)
    return () => { source.close(); if (pending !== undefined) clearTimeout(pending) }
  }, [userId, offline])
  useEffect(() => {
    if (!userId || offline) return
    const controller = new AbortController()
    api<{ active: number }>('/blockers/summary', { signal: controller.signal }).then(r => setProblemCount(r.active)).catch(() => {})
    return () => controller.abort()
  }, [userId, offline, refreshToken])
  async function logout() { try { await api('/auth/logout', { method: 'POST' }, user?.csrf_token) } finally { clearQueueSnapshot(); setUser(null); setPage('dashboard') } }
  const nav = (target: Screen, label: string, primary = false) => <button key={target} aria-label={label} aria-current={page === target ? 'page' : undefined} className={primary ? 'nav-button' : 'btn'} onClick={() => { document.querySelector<HTMLDetailsElement>('.secondary-nav')?.removeAttribute('open'); setFilter(''); setPage(target); window.scrollTo(0, 0) }}>{primary && <NavIcon name={target} />}<span>{target === 'feed' ? 'Лента' : target === 'problems' ? 'Проблемы' : label}</span>{target === 'problems' && <span className="nav-count" aria-hidden="true">{problemCount}</span>}</button>
  return <FeatureContext.Provider value={features}><a className="skip-link" href="#workspace">К содержимому</a><main className="app-shell">
    <header className="app-header">
      <div className="brand"><img src="/icon.svg" alt="" /><h1>Ozon Production</h1>{health?.mock_mode && <span className="environment-note" title="Тестовый режим · синтетические заказы">MOCK</span>}</div>
      {user && !offline && <nav aria-label="Основная навигация" className="primary-nav">{nav('dashboard', 'Главная', true)}{nav('queue', 'Заказы', true)}{nav('feed', 'Лента заказов', true)}{nav('problems', `Проблемы (${problemCount})`, true)}</nav>}
      {user && <div className="header-tools">{!offline && <details className="secondary-nav" onKeyDown={event => { if (event.key === 'Escape') { event.currentTarget.open = false; event.currentTarget.querySelector('summary')?.focus() } }}><summary><span className="sr-only">{admin ? 'Администрирование и профиль' : 'Профиль'}</span><span className="user-avatar" aria-hidden="true">{user.display_name.slice(0, 1)}</span><span aria-hidden="true">Профиль</span></summary><div>{nav('account', 'Профиль')}{admin && nav('notifications', 'Уведомления / Telegram')}{admin && nav('ozon-integration', 'Ozon')}{admin && user.permissions.includes('users.view') && nav('users', 'Пользователи')}{admin && user.permissions.includes('audit.view') && nav('audit', 'Аудит')}{admin && nav('product-profiles', 'Нормативы')}{has('manager_tasks') && user.permissions.includes('manager_tasks.view') && nav('manager-tasks', 'Задачи руководителя')}{has('procurement') && user.permissions.includes('procurement.view') && nav('procurement', 'Закупки')}{has('analytics') && user.permissions.includes('analytics.view') && nav('analytics', 'Аналитика')}<button className="btn btn-ghost logout" onClick={logout}>Выйти</button></div></details>}{offline && <button className="btn btn-ghost logout" onClick={logout}>Выйти</button>}</div>}
    </header>
    {user && !offline && <OzonSyncStatus refreshToken={refreshToken} />}
    {offline ? <OfflineQueue reconnecting={reconnecting} retry={() => checkRef.current()} forget={() => { clearQueueSnapshot(); setUser(null); setRefreshToken(v => v + 1) }} /> : loading ? <Loading /> : !user ? <Login onLogin={value => { clearQueueSnapshot(); setUser(value); setPage('dashboard'); checkRef.current() }} /> : <>
      {['queue', 'mine'].includes(page) && <div className="mb-3 flex gap-2">{nav('queue', 'Все заказы')}{nav('mine', 'Мои задачи')}</div>}
      <div id="workspace" tabIndex={-1}><Suspense fallback={<Loading />}>
      {page === 'dashboard' && <Dashboard open={open} refreshToken={refreshToken} />}
      {['queue', 'mine', 'problems', 'feed'].includes(page) && (has('advanced_workflow') && page !== 'feed' && page !== 'problems' ? <Orders key={`${filter}:${page}`} current={user} mine={page === 'mine'} initialFilter={filter} refreshToken={refreshToken} /> : <CoreOrders key={`${filter}:${page}`} current={user} mine={page === 'mine'} feed={page === 'feed'} initialFilter={page === 'problems' ? 'problems' : filter} refreshToken={refreshToken} />)}
      {page === 'money-at-risk' && user.permissions.includes('finance.view') && <MoneyAtRisk key={filter} initialBucket={filter} refreshToken={refreshToken} />}
      {page === 'manager-tasks' && has('manager_tasks') && user.permissions.includes('manager_tasks.view') && <ManagerTasks current={user} refreshToken={refreshToken} />}
      {page === 'procurement' && has('procurement') && user.permissions.includes('procurement.view') && <Procurement current={user} refreshToken={refreshToken} />}
      {page === 'analytics' && has('analytics') && user.permissions.includes('analytics.view') && <Analytics refreshToken={refreshToken} />}
      {page === 'product-profiles' && admin && <ProductProfiles current={user} />}
      {page === 'audit' && admin && <AuditLog />}{page === 'users' && admin && <Users current={user} />}
      {page === 'account' && <Account current={user} />}{page === 'ozon-integration' && admin && <OzonIntegration csrf={user.csrf_token} refreshToken={refreshToken} />}
      {page === 'notifications' && admin && <Notifications current={user} refreshToken={refreshToken} open={openNotice} />}
      </Suspense></div>
    </>}
  </main></FeatureContext.Provider>
}
