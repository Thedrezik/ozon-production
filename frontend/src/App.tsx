import { useEffect, useState } from 'react'

type Health = { status: string; mock_mode: boolean }

export function App() {
  const [online, setOnline] = useState(navigator.onLine)
  const [health, setHealth] = useState<Health | null>(null)
  const [backendState, setBackendState] = useState('Проверка…')

  useEffect(() => {
    const syncOnline = () => setOnline(navigator.onLine)
    window.addEventListener('online', syncOnline)
    window.addEventListener('offline', syncOnline)
    return () => {
      window.removeEventListener('online', syncOnline)
      window.removeEventListener('offline', syncOnline)
    }
  }, [])

  useEffect(() => {
    setHealth(null)
    if (!online) return
    setBackendState('Проверка…')
    const controller = new AbortController()
    fetch('/api/health', { cache: 'no-store', signal: controller.signal })
      .then((response) => {
        if (!response.ok) throw new Error('Backend unavailable')
        return response.json() as Promise<Health>
      })
      .then((result) => { setHealth(result); setBackendState('Доступен') })
      .catch((error: unknown) => {
        if (error instanceof Error && error.name === 'AbortError') return
        setHealth(null)
        setBackendState('Недоступен')
      })
    return () => controller.abort()
  }, [online])

  return (
    <main className="min-h-screen bg-slate-50 px-5 py-10 text-slate-900">
      <div className="mx-auto max-w-lg">
        <header className="mb-10 flex items-center gap-4">
          <img src="/icon.svg" alt="" className="h-14 w-14" />
          <div>
            <h1 className="text-2xl font-bold tracking-tight">Ozon Production</h1>
            <p className="text-sm text-slate-600">Управление производством</p>
          </div>
        </header>
        <section className="rounded-2xl bg-white p-6 shadow-sm" aria-label="Состояние системы">
          <h2 className="mb-5 text-lg font-semibold">Состояние системы</h2>
          <dl className="space-y-4">
            <div className="flex justify-between gap-4"><dt>Приложение</dt><dd className="font-semibold text-emerald-700">Работает</dd></div>
            <div className="flex justify-between gap-4"><dt>Сеть</dt><dd className={online ? 'font-semibold text-emerald-700' : 'font-semibold text-amber-700'}>{online ? 'Онлайн' : 'Офлайн'}</dd></div>
            <div className="flex justify-between gap-4"><dt>Backend</dt><dd className="font-semibold">{online ? backendState : 'Нет соединения'}</dd></div>
          </dl>
        </section>
        {health?.mock_mode && online && <p className="mt-5 rounded-xl bg-amber-100 px-5 py-4 font-bold text-amber-900">MOCK MODE · Тестовый режим</p>}
        {!online && <p role="status" className="mt-5 rounded-xl bg-amber-100 px-5 py-4 text-amber-900">Нет соединения. Данные API сейчас недоступны.</p>}
      </div>
    </main>
  )
}
