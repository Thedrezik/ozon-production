import { useEffect, useState } from 'react'
import { dateTime, useFeatures } from './features'

type SyncState = {
  enabled: boolean; status: string; error_code: string | null
  last_attempt_at: string | null; last_successful_sync: string | null
  age_seconds: number | null; stale: boolean
}

export function OzonSyncStatus({ refreshToken }: { refreshToken: number }) {
  const { timezone } = useFeatures()
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
  if (unavailable) return <p role="status" className="sync-status sync-warning">Не удалось проверить актуальность данных Ozon.</p>
  if (!state) return null
  const failed = state.status === 'ERROR'
  return <details className={`sync-status ${failed ? 'sync-error' : state.stale ? 'sync-warning' : ''}`}>
    <summary><span className="sync-indicator" aria-hidden="true" /><span role={failed ? 'alert' : 'status'}>{failed ? 'Ошибка синхронизации Ozon' : state.stale ? 'Данные Ozon устарели' : state.status === 'RUNNING' ? 'Ozon · обновляем…' : 'Ozon · данные актуальны'}</span><span className="sync-helper">{state.stale || failed ? 'Локальное производство доступно' : state.age_seconds !== null ? `${Math.floor(state.age_seconds / 60)} мин. назад` : ''}</span><span aria-hidden="true">⌄</span></summary>
    <div role="status"><p>{state.last_successful_sync ? `Обновлено ${dateTime(state.last_successful_sync, timezone)}` : 'Успешной синхронизации ещё не было.'}</p>
      {!state.enabled && <p>Периодическая синхронизация отключена.</p>}
      {failed && <p>Ошибка синхронизации: {state.error_code}. {state.last_attempt_at && `Попытка: ${dateTime(state.last_attempt_at, timezone)}`}</p>}
    </div>
  </details>
}
