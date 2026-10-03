export const button = 'btn'

export function Loading({ label = 'Загрузка…' }: { label?: string }) {
  return <p role="status" className="state" aria-live="polite">{label}</p>
}

export function StatusBadge({ status, label }: { status: string; label: string }) {
  const tone = status === 'CANCELLED' ? 'danger' : status === 'BLOCKED' ? 'warning'
    : ['PRODUCED', 'QUALITY_CHECK', 'PACKING', 'READY_TO_SHIP', 'HANDED_TO_SHIPPING', 'DONE'].includes(status) ? 'success'
      : status === 'IN_PRODUCTION' ? 'active' : ''
  return <span className={`badge badge-${tone}`}>{label}</span>
}

export function NavIcon({ name }: { name: string }) {
  const paths: Record<string, string> = {
    dashboard: 'M3 10 12 3l9 7v10a1 1 0 0 1-1 1h-5v-7H9v7H4a1 1 0 0 1-1-1Z',
    queue: 'M4 4h16v16H4ZM8 8h8M8 12h8M8 16h5',
    feed: 'M5 5h14M5 12h14M5 19h14',
    problems: 'M12 3 2 21h20ZM12 9v5M12 17v1',
  }
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={paths[name]} /></svg>
}
