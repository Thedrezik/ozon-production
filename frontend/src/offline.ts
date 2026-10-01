// A short-lived display snapshot, never an authenticated session or API cache.
const key = 'production.queue.v1'
export const snapshotLifetime = 60 * 60 * 1000
export type QueueRow = {
  posting_number: string; internal_status: string; ozon_status: string;
  shipment_deadline: string; priority: { level: string; label: string } | null;
  items: { product_name: string; quantity: number }[]
}
export type QueueSnapshot = { owner: number; savedAt: string; title: string; total: number; offset: number; items: QueueRow[] }
let memory: QueueSnapshot | null = null

export function clearQueueSnapshot() {
  memory = null
  try { sessionStorage.removeItem(key) } catch { /* Storage may be disabled. */ }
}

export function readQueueSnapshot(): QueueSnapshot | null {
  try {
    const value = memory ?? JSON.parse(sessionStorage.getItem(key) ?? 'null') as QueueSnapshot | null
    if (!value) return null
    const age = Date.now() - Date.parse(value.savedAt)
    if (!Number.isFinite(age) || age < 0 || age > snapshotLifetime || !Array.isArray(value.items)) {
      clearQueueSnapshot(); return null
    }
    return value
  } catch { clearQueueSnapshot(); return null }
}

export function saveQueueSnapshot(owner: number, title: string, offset: number, page: { total: number; items: QueueRow[] }) {
  memory = {
    owner, title, offset, total: page.total, savedAt: new Date().toISOString(),
    items: page.items.map(row => ({
      posting_number: row.posting_number, internal_status: row.internal_status,
      ozon_status: row.ozon_status, shipment_deadline: row.shipment_deadline,
      priority: row.priority ? { level: row.priority.level, label: row.priority.label } : null,
      items: row.items.map(item => ({ product_name: item.product_name, quantity: item.quantity })),
    })),
  }
  try { sessionStorage.setItem(key, JSON.stringify(memory)) } catch { /* Keep in-memory fallback. */ }
}

export function reportUnavailable() { window.dispatchEvent(new Event('backend-unavailable')) }
