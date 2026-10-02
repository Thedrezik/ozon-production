// Only mounted in isolated E2E containers, never copied into a production image.
import { createServer, request } from 'node:http'
import { readFile, writeFile, access } from 'node:fs/promises'
const directory = '/e2e'
createServer(async (req, res) => {
  try {
    const state = JSON.parse(await readFile(`${directory}/transport.json`, 'utf8'))
    if (state.outage || (state.eventsOffline && req.url === '/api/orders/events')) {
      res.writeHead(503); res.end(); return
    }
    if (state.race && req.method === 'POST' && /^\/api\/orders\/\d+\/claim$/.test(req.url)) {
      await writeFile(`${directory}/claim-pending`, '')
      const end = Date.now() + 15000
      while (true) {
        try { await access(`${directory}/claim-release`); break } catch { /* wait for real competing write */ }
        if (Date.now() > end) throw new Error('claim barrier timeout')
        await new Promise(resolve => setTimeout(resolve, 50))
      }
    }
    const upstream = request({ hostname: 'backend', port: 8000, path: req.url, method: req.method, headers: req.headers }, response => {
      res.writeHead(response.statusCode, response.headers); response.pipe(res)
    })
    upstream.on('error', () => { if (!res.headersSent) res.writeHead(502); res.end() })
    res.on('close', () => upstream.destroy())
    req.pipe(upstream)
  } catch { res.writeHead(503); res.end() }
}).listen(8000, '0.0.0.0')
