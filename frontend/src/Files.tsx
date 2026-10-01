import { useCallback, useEffect, useRef, useState } from 'react'

type User = { id: number; csrf_token?: string; permissions: string[] }
type Photo = { id: number; blocker_id: number | null; comment_id: number | null; url: string }

export function Photos({ orderId, blockerId, commentId, current }: { orderId: number; blockerId?: number; commentId?: number; current: User }) {
  const [photos, setPhotos] = useState<Photo[]>([])
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const refresh = useCallback(async (offset = 0) => {
    const params = new URLSearchParams({ limit: '20', offset: String(offset), target_only: 'true' })
    if (blockerId !== undefined) params.set('blocker_id', String(blockerId))
    if (commentId !== undefined) params.set('comment_id', String(commentId))
    const response = await fetch(`/api/files/orders/${orderId}/photos?${params}`, { cache: 'no-store' })
    if (!response.ok) throw new Error('Не удалось загрузить фотографии')
    const result = await response.json() as { items: Photo[]; has_more: boolean }
    setPhotos(previous => offset === 0 ? result.items : [...previous, ...result.items])
    setHasMore(result.has_more)
  }, [orderId, blockerId, commentId])
  useEffect(() => { void refresh().catch(cause => setError(String(cause))) }, [refresh])
  async function upload(file?: File) {
    if (!file) return
    if (file.size > 10 * 1024 * 1024) { setError('Максимальный размер — 10 МБ'); return }
    setBusy(true); setError('')
    try {
      const params = new URLSearchParams()
      if (blockerId !== undefined) params.set('blocker_id', String(blockerId))
      if (commentId !== undefined) params.set('comment_id', String(commentId))
      const response = await fetch(`/api/files/orders/${orderId}/photos?${params}`, { method: 'POST', body: file,
        headers: { 'Content-Type': file.type, 'X-CSRF-Token': current.csrf_token ?? '' } })
      if (!response.ok) { const body = await response.json(); throw new Error(body.detail ?? 'Не удалось загрузить фото') }
      await refresh()
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Ошибка загрузки') }
    finally { setBusy(false) }
  }
  return <details className="mt-3 rounded-xl border bg-white p-3" onToggle={event => { if (event.currentTarget.open) void refresh().catch(cause => setError(String(cause))) }}>
    <summary className="font-semibold">Фотографии ({photos.length})</summary>
    <div className="mt-2 flex flex-wrap gap-2">{photos.map(photo => <a key={photo.id} href={photo.url} target="_blank" rel="noreferrer"><img src={photo.url} alt={`Фото ${photo.id}`} loading="lazy" className="h-24 w-24 rounded-lg object-cover" /></a>)}</div>
    {hasMore && <button className="mt-2 min-h-11 rounded-xl border px-3" onClick={() => void refresh(photos.length).catch(cause => setError(String(cause)))}>Ещё фотографии</button>}
    {current.permissions.includes(blockerId !== undefined ? 'blockers.create' : 'comments.create') && <label className="mt-3 block min-h-11">{busy ? 'Сохранение…' : 'Добавить фото (JPEG, PNG, WebP, до 10 МБ)'}<input type="file" accept="image/jpeg,image/png,image/webp" disabled={busy} className="mt-2 block w-full" onChange={event => { void upload(event.target.files?.[0]); event.target.value = '' }} /></label>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </details>
}

export function OrderQR({ orderId }: { orderId: number }) {
  return <details className="mt-3 rounded-xl border p-3"><summary className="font-semibold">QR заказа</summary><img src={`/api/files/orders/${orderId}/qr`} alt="QR для открытия заказа" className="mt-2 h-48 w-48" /></details>
}

export function Scanner({ onOrder }: { onOrder: (id: number) => void }) {
  const video = useRef<HTMLVideoElement>(null)
  const [active, setActive] = useState(false)
  const [error, setError] = useState('')
  const [payload, setPayload] = useState('')
  const resolve = useCallback(async (value: string) => {
    const response = await fetch(`/api/files/resolve?payload=${encodeURIComponent(value)}`, { cache: 'no-store' })
    if (!response.ok) throw new Error(response.status === 404 ? 'Заказ с этим кодом не найден' : 'Не удалось открыть заказ')
    const result = await response.json() as { order_id: number }
    onOrder(result.order_id)
  }, [onOrder])
  const resolveRef = useRef(resolve)
  useEffect(() => { resolveRef.current = resolve }, [resolve])
  useEffect(() => {
    if (!active || !video.current) return
    let cancelled = false
    let controls: { stop: () => void } | undefined
    let processing = false
    const element = video.current
    void import('@zxing/browser').then(async ({ BrowserMultiFormatReader }) => {
      if (cancelled) return
      const reader = new BrowserMultiFormatReader()
      controls = await reader.decodeFromConstraints({ video: { facingMode: { ideal: 'environment' }, width: { ideal: 1280 } }, audio: false }, element, (result, _error, scanner) => {
        if (!result || cancelled || processing) return
        processing = true
        scanner.stop(); setActive(false)
        void resolveRef.current(result.getText()).catch(cause => setError(String(cause)))
      })
      if (cancelled) controls.stop()
    }).catch(() => { if (!cancelled) { setError('Камера недоступна. Разрешите доступ по HTTPS или введите номер отправления.'); setActive(false) } })
    return () => { cancelled = true; controls?.stop(); const stream = element.srcObject; if (stream instanceof MediaStream) stream.getTracks().forEach(track => track.stop()); element.srcObject = null }
  }, [active])
  return <div className="rounded-xl border bg-white p-3">
    <button className="min-h-11 rounded-xl bg-blue-800 px-4 text-white" onClick={() => { setError(''); setActive(!active) }}>{active ? 'Закрыть камеру' : 'Сканировать QR / штрихкод'}</button>
    {active && <video ref={video} muted playsInline className="mt-3 max-h-80 w-full rounded-xl" />}
    <form className="mt-2 flex flex-wrap gap-2" onSubmit={event => { event.preventDefault(); setError(''); setActive(false); void resolve(payload.trim()).catch(cause => setError(String(cause))) }}><input aria-label="Номер отправления или QR payload" value={payload} onChange={event => setPayload(event.target.value)} maxLength={160} required placeholder="Номер отправления" className="min-h-11 rounded-xl border p-2" /><button className="min-h-11 rounded-xl border px-4">Открыть заказ</button></form>
    <p className="mt-2 text-sm text-slate-600">QR и штрихкод должны содержать номер отправления. Камера работает по HTTPS.</p>
    {error && <p role="alert" className="text-red-700">{error}</p>}
  </div>
}
