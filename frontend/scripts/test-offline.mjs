import assert from 'node:assert/strict'
import { readFileSync } from 'node:fs'
import vm from 'node:vm'
import ts from 'typescript'

const storage = new Map()
const sessionStorage = { getItem: key => storage.get(key), setItem: (key, value) => storage.set(key, value), removeItem: key => storage.delete(key) }
const source = ts.transpileModule(readFileSync(new URL('../src/offline.ts', import.meta.url), 'utf8'), { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText
function load() { const exports = {}; vm.runInNewContext(source, { exports, sessionStorage, Date, Event, window: { dispatchEvent() {} } }); return exports }
let module = load()
module.saveQueueSnapshot(1, 'Queue', 20, { total: 50, items: [{ posting_number: 'MOCK-1', internal_status: 'QUEUED', ozon_status: 'awaiting_packaging', shipment_deadline: new Date().toISOString(), priority: { level: 'P1', label: 'Urgent', reasons: ['640 RUB'] }, items: [{ product_name: 'Chair', quantity: 1, price: '999' }], csrf_token: 'secret', tariff: { cost: '999' }, assigned_user: { display_name: 'Private' } }] })
assert.equal(module.readQueueSnapshot().items[0].posting_number, 'MOCK-1')
module = load() // Reload: restore only the display snapshot, without cached auth.
assert.equal(module.readQueueSnapshot().offset, 20)
const saved = [...storage.values()][0]
for (const excluded of ['secret', 'price', 'tariff', 'Private', '640 RUB']) assert.ok(!saved.includes(excluded))
module.clearQueueSnapshot(); assert.equal(load().readQueueSnapshot(), null)
sessionStorage.setItem('production.queue.v1', JSON.stringify({ savedAt: new Date(Date.now() - 3600001).toISOString(), items: [] }))
assert.equal(load().readQueueSnapshot(), null)
sessionStorage.setItem('production.queue.v1', 'broken'); assert.equal(load().readQueueSnapshot(), null)
const sw = readFileSync(new URL('../dist/sw.js', import.meta.url), 'utf8')
assert.ok(sw.includes('NetworkOnly')); assert.ok(sw.includes('index.html')); assert.ok(!sw.includes('StaleWhileRevalidate'))
console.log('Offline snapshot: reload, projection/privacy, logout cleanup, expiry, corruption and SW NetworkOnly passed')
