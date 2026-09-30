import { useEffect, useState, type FormEvent } from 'react'

type Current = { csrf_token?: string }
type Profile = { id: number; offer_id: string | null; sku: string | null; product_name: string; production_minutes: number; packing_minutes: number; complexity: 'LOW' | 'MEDIUM' | 'HIGH'; production_group: string | null }
type Draft = Omit<Profile, 'id'>
const empty: Draft = { offer_id: '', sku: '', product_name: '', production_minutes: 0, packing_minutes: 0, complexity: 'MEDIUM', production_group: '' }

async function api<T>(path: string, options: RequestInit = {}, csrf?: string): Promise<T> {
  const response = await fetch(`/api${path}`, { ...options, credentials: 'same-origin', cache: 'no-store', headers: { ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(csrf ? { 'X-CSRF-Token': csrf } : {}), ...options.headers } })
  if (!response.ok) { const body = await response.json().catch(() => null) as { detail?: string } | null; throw new Error(body?.detail || `Ошибка ${response.status}`) }
  return response.status === 204 ? undefined as T : response.json() as Promise<T>
}

export function ProductProfiles({ current }: { current: Current }) {
  const [rows, setRows] = useState<Profile[]>([])
  const [draft, setDraft] = useState<Draft>(empty)
  const [editing, setEditing] = useState<number | null>(null)
  const [notice, setNotice] = useState('')
  async function refresh() { setRows(await api<Profile[]>('/product-profiles')) }
  useEffect(() => { void refresh().catch(() => setNotice('Не удалось загрузить нормативы')) }, [])
  function set<K extends keyof Draft>(key: K, value: Draft[K]) { setDraft(previous => ({ ...previous, [key]: value })) }
  async function save(event: FormEvent) {
    event.preventDefault(); setNotice('')
    try {
      await api(`/product-profiles${editing ? `/${editing}` : ''}`, { method: editing ? 'PUT' : 'POST', body: JSON.stringify({ ...draft, offer_id: draft.offer_id || null, sku: draft.sku || null, production_group: draft.production_group || null }) }, current.csrf_token)
      setDraft(empty); setEditing(null); setNotice('Норматив сохранён'); await refresh()
    } catch (error) { setNotice(error instanceof Error ? error.message : 'Не удалось сохранить') }
  }
  function edit(row: Profile) { setEditing(row.id); setDraft({ ...row }); window.scrollTo({ top: 0, behavior: 'smooth' }) }
  async function remove(row: Profile) {
    if (!window.confirm(`Удалить норматив «${row.product_name}»?`)) return
    try { await api(`/product-profiles/${row.id}`, { method: 'DELETE' }, current.csrf_token); setNotice('Норматив удалён'); await refresh() }
    catch (error) { setNotice(error instanceof Error ? error.message : 'Не удалось удалить') }
  }
  return <section className="space-y-5"><h2 className="text-xl font-semibold">Нормативы производства</h2>{notice && <p role="status" className="rounded-lg bg-amber-50 p-3">{notice}</p>}
    <form onSubmit={save} className="space-y-3 rounded-2xl bg-white p-5 shadow-sm"><h3 className="font-semibold">{editing ? 'Изменить норматив' : 'Новый норматив'}</h3>
      <input aria-label="Название товара" placeholder="Название товара" required value={draft.product_name} onChange={e => set('product_name', e.target.value)} className="w-full rounded-lg border p-3" />
      <div className="grid grid-cols-2 gap-3"><input aria-label="offer_id" placeholder="offer_id" value={draft.offer_id ?? ''} onChange={e => set('offer_id', e.target.value)} className="min-w-0 rounded-lg border p-3" /><input aria-label="SKU" placeholder="SKU" value={draft.sku ?? ''} onChange={e => set('sku', e.target.value)} className="min-w-0 rounded-lg border p-3" /></div>
      <div className="grid grid-cols-2 gap-3"><label className="text-sm">Производство, мин<input type="number" min="0" required value={draft.production_minutes} onChange={e => set('production_minutes', Number(e.target.value))} className="mt-1 w-full rounded-lg border p-3" /></label><label className="text-sm">Упаковка, мин<input type="number" min="0" required value={draft.packing_minutes} onChange={e => set('packing_minutes', Number(e.target.value))} className="mt-1 w-full rounded-lg border p-3" /></label></div>
      <div className="grid grid-cols-2 gap-3"><label className="text-sm">Сложность<select value={draft.complexity} onChange={e => set('complexity', e.target.value as Draft['complexity'])} className="mt-1 w-full rounded-lg border p-3"><option value="LOW">Низкая</option><option value="MEDIUM">Средняя</option><option value="HIGH">Высокая</option></select></label><input aria-label="Группа производства" placeholder="Группа производства" value={draft.production_group ?? ''} onChange={e => set('production_group', e.target.value)} className="self-end rounded-lg border p-3" /></div>
      <div className="flex gap-2"><button className="min-h-11 rounded-xl bg-blue-800 px-5 font-semibold text-white">{editing ? 'Сохранить' : 'Добавить'}</button>{editing && <button type="button" onClick={() => { setEditing(null); setDraft(empty) }} className="min-h-11 rounded-xl border px-4">Отмена</button>}</div>
    </form>
    {rows.map(row => <article key={row.id} className="rounded-2xl bg-white p-5 shadow-sm"><h3 className="font-semibold">{row.product_name}</h3><p className="mt-1 text-sm text-slate-600">{row.offer_id ? `offer_id: ${row.offer_id}` : ''}{row.offer_id && row.sku ? ' · ' : ''}{row.sku ? `SKU: ${row.sku}` : ''}</p><p className="mt-2">Производство {row.production_minutes} мин · упаковка {row.packing_minutes} мин · {row.complexity === 'LOW' ? 'низкая' : row.complexity === 'HIGH' ? 'высокая' : 'средняя'}{row.production_group ? ` · ${row.production_group}` : ''}</p><div className="mt-3 flex gap-2"><button onClick={() => edit(row)} className="min-h-11 rounded-xl border px-4">Изменить</button><button onClick={() => void remove(row)} className="min-h-11 rounded-xl border border-red-300 px-4 text-red-700">Удалить</button></div></article>)}
  </section>
}
