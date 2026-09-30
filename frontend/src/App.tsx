import { useEffect, useState, type FormEvent } from 'react'
import { Orders } from './Orders'
import { ManagerTasks } from './ManagerTasks'

type User = { id: number; username: string; display_name: string; is_active: boolean; roles: string[]; permissions: string[]; csrf_token?: string }
type Health = { mock_mode: boolean }

async function api<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const response = await fetch(`/api${path}`, {
    ...options, cache: 'no-store', credentials: 'same-origin',
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
  async function submit(event: FormEvent) {
    event.preventDefault(); setError('')
    try { onLogin(await api<User>('/auth/login', { method: 'POST', body: JSON.stringify({ username, password }) })) }
    catch (cause) { setError(cause instanceof Error && cause.message === 'Invalid credentials' ? 'Неверный логин или пароль' : 'Не удалось войти. Попробуйте позже.') }
  }
  return <section className="rounded-2xl bg-white p-6 shadow-sm"><h2 className="mb-5 text-xl font-semibold">Вход</h2><form onSubmit={submit} className="space-y-4">
    <label className="block text-sm font-medium">Логин<input autoComplete="username" required value={username} onChange={e => setUsername(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
    <label className="block text-sm font-medium">Пароль<input type="password" autoComplete="current-password" required value={password} onChange={e => setPassword(e.target.value)} className="mt-1 w-full rounded-lg border p-3" /></label>
    {error && <p role="alert" className="text-red-700">{error}</p>}<button className="w-full rounded-xl bg-blue-800 p-4 font-semibold text-white">Войти</button>
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

  async function refresh() {
    const [result, names] = await Promise.all([api<{ items: User[] }>('/users'), api<string[]>('/roles')])
    setUsers(result.items); setRoles(names)
  }
  useEffect(() => { api<{ items: User[] }>('/users').then(r => setUsers(r.items)).catch(() => setNotice('Не удалось загрузить пользователей')); api<string[]>('/roles').then(setRoles).catch(() => setNotice('Не удалось загрузить роли')) }, [])

  async function create(event: FormEvent) {
    event.preventDefault(); setNotice('')
    try {
      await api('/users', { method: 'POST', body: JSON.stringify({ username, display_name: displayName, password, roles: [newRole] }) }, current.csrf_token)
      setUsername(''); setDisplayName(''); setPassword(''); setNotice('Пользователь создан'); await refresh()
    } catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
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
      <button className="rounded-xl bg-blue-800 px-5 py-3 font-semibold text-white">Создать</button></form>}
    {users.map(user => <article key={user.id} className="rounded-2xl bg-white p-5 shadow-sm"><div className="flex justify-between gap-2"><div><h3 className="font-semibold">{user.display_name}</h3><p className="text-sm text-slate-500">{user.username} · {user.is_active ? 'Активен' : 'Отключён'}</p></div>{current.permissions.includes('users.manage') && user.is_active && user.id !== current.id && <button onClick={() => deactivate(user)} className="rounded-lg border px-3 text-sm text-red-700">Отключить</button>}</div>
      <div className="mt-4 flex flex-wrap gap-3">{roles.map(role => <label key={role} className="text-xs"><input type="checkbox" checked={user.roles.includes(role)} disabled={!current.permissions.includes('users.manage') || (role === 'SUPER_ADMIN' && !current.roles.includes('SUPER_ADMIN'))} onChange={() => changeRoles(user, role)} /> {role}</label>)}</div></article>)}
  </section>
}

function Account({ current }: { current: User }) {
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [notice, setNotice] = useState('')
  async function change(event: FormEvent) {
    event.preventDefault()
    try { await api('/auth/change-password', { method: 'POST', body: JSON.stringify({ current_password: oldPassword, new_password: newPassword }) }, current.csrf_token); setOldPassword(''); setNewPassword(''); setNotice('Пароль изменён') }
    catch (cause) { setNotice(cause instanceof Error ? cause.message : 'Ошибка') }
  }
  return <section className="rounded-2xl bg-white p-5 shadow-sm"><h2 className="text-xl font-semibold">Профиль</h2><p className="mt-2">{current.display_name} · {current.username}</p><p className="text-sm text-slate-500">Роли: {current.roles.join(', ')}</p><form onSubmit={change} className="mt-6 space-y-3"><h3 className="font-semibold">Сменить пароль</h3><input aria-label="Текущий пароль" type="password" autoComplete="current-password" required value={oldPassword} onChange={e => setOldPassword(e.target.value)} className="w-full rounded-lg border p-3" /><input aria-label="Новый пароль" type="password" autoComplete="new-password" minLength={12} required value={newPassword} onChange={e => setNewPassword(e.target.value)} className="w-full rounded-lg border p-3" /><button className="rounded-xl bg-blue-800 px-5 py-3 font-semibold text-white">Сохранить</button></form>{notice && <p role="status" className="mt-3">{notice}</p>}</section>
}

export function App() {
  const [online, setOnline] = useState(navigator.onLine)
  const [user, setUser] = useState<User | null>(null)
  const [loading, setLoading] = useState(true)
  const [health, setHealth] = useState<Health | null>(null)
  const [page, setPage] = useState<'queue' | 'mine' | 'manager-tasks' | 'users' | 'account'>('queue')
  useEffect(() => { const sync = () => setOnline(navigator.onLine); window.addEventListener('online', sync); window.addEventListener('offline', sync); return () => { window.removeEventListener('online', sync); window.removeEventListener('offline', sync) } }, [])
  useEffect(() => { api<User>('/auth/me').then(setUser).catch(() => setUser(null)).finally(() => setLoading(false)); api<Health>('/health').then(setHealth).catch(() => setHealth(null)) }, [])
  async function logout() { try { await api('/auth/logout', { method: 'POST' }, user?.csrf_token) } finally { setUser(null); setPage('queue') } }
  return <main className="min-h-screen bg-slate-50 px-4 py-8 text-slate-900"><div className="mx-auto max-w-2xl"><header className="mb-7 flex items-center gap-3"><img src="/icon.svg" alt="" className="h-12 w-12" /><div><h1 className="text-xl font-bold">Ozon Production</h1><p className="text-sm text-slate-600">Управление производством</p></div></header>
    {health?.mock_mode && <p className="mb-5 rounded-xl bg-amber-100 p-3 font-semibold text-amber-900">MOCK MODE · Тестовый режим</p>}{!online && <p role="status" className="mb-5 rounded-xl bg-amber-100 p-3">Нет соединения. Данные недоступны.</p>}
    {loading ? <p>Загрузка…</p> : !user ? <Login onLogin={setUser} /> : <><nav aria-label="Основная навигация" className="mb-5 flex flex-wrap gap-2"><button onClick={() => setPage('mine')} className="rounded-lg bg-white px-4 py-3 shadow-sm">Мои задачи</button><button onClick={() => setPage('queue')} className="rounded-lg bg-white px-4 py-3 shadow-sm">Очередь</button>{user.permissions.includes('manager_tasks.view') && <button onClick={() => setPage('manager-tasks')} className="rounded-lg bg-white px-4 py-3 shadow-sm">Задачи руководителя</button>}{user.permissions.includes('users.view') && <button onClick={() => setPage('users')} className="rounded-lg bg-white px-4 py-3 shadow-sm">Пользователи</button>}<button onClick={() => setPage('account')} className="rounded-lg bg-white px-4 py-3 shadow-sm">Профиль</button><button onClick={logout} className="rounded-lg bg-white px-4 py-3 shadow-sm">Выйти</button></nav>{page === 'queue' && <Orders current={user} mine={false} />}{page === 'mine' && <Orders current={user} mine />}{page === 'manager-tasks' && user.permissions.includes('manager_tasks.view') && <ManagerTasks current={user} />}{page === 'users' && user.permissions.includes('users.view') && <Users current={user} />}{page === 'account' && <Account current={user} />}</>}
  </div></main>
}
