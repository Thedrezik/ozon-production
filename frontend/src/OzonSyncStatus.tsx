import { useEffect, useState } from 'react'

type SyncState = {
  enabled: boolean; status: string; error_code: string | null
  last_attempt_at: string | null; last_successful_sync: string | null
  age_seconds: number | null; stale: boolean
}

export function OzonSyncStatus({ refreshToken }: { refreshToken: number }) {
  const [state, setState] = useState<SyncState | null>(null)
  const [unavailable, setUnavailable] = useState(false)
  useEffect(() => {
    const controller = new AbortController()
    fetch('/api/ozon/sync-state', { credentials: 'same-origin', cache: 'no-store', signal: controller.signal })
      .then(response => { if (!response.ok) throw new Error(); return response.json() as Promise<SyncState> })
      .then(value => { setState(value); setUnavailable(false) })
      .catch(() => { if (!controller.signal.aborted) setUnavailable(true) })
    return () => controller.abort()
  }, [refreshToken])
  if (unavailable) return <p role="status" className="mb-4 rounded-xl bg-amber-100 p-3">Не удалось проверить актуальность данных Ozon.</p>
  if (!state) return null
  return <aside role="status" className={`mb-4 rounded-xl p-3 text-sm ${state.stale || state.status === 'ERROR' ? 'bg-amber-100 text-amber-900' : 'bg-white text-slate-600'}`}>
    <p>Ozon: {state.last_successful_sync ? `обновлено ${new Date(state.last_successful_sync).toLocaleString('ru-RU')}` : 'успешной синхронизации ещё не было'}{state.age_seconds !== null && ` · ${Math.floor(state.age_seconds / 60)} мин. назад`}</p>
    {!state.enabled && <p>Периодическая синхронизация отключена.</p>}
    {state.stale && <p>Данные Ozon устарели. Локальное производство доступно.</p>}
    {state.status === 'RUNNING' && <p>Синхронизация выполняется…</p>}
    {state.status === 'ERROR' && <p>Ошибка синхронизации: {state.error_code}. {state.last_attempt_at && `Попытка: ${new Date(state.last_attempt_at).toLocaleString('ru-RU')}`}</p>}
  </aside>
}
