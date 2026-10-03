// Reuses every existing scenario with isolated PostgreSQL + actual Caddy/PWA HTTPS.
import assert from 'node:assert/strict'
import { execFile } from 'node:child_process'
import { promisify } from 'node:util'
import { randomBytes } from 'node:crypto'
import { mkdtemp, readFile, writeFile, rm, access, rename, mkdir, copyFile } from 'node:fs/promises'
import { createServer } from 'node:net'
import { get } from 'node:https'
import { tmpdir } from 'node:os'
import { join } from 'node:path'
import { root, until } from './helpers.mjs'
const execute = promisify(execFile)
async function freePort() {
  const server = createServer()
  await new Promise(resolve => server.listen(0, '127.0.0.1', resolve))
  const port = server.address().port
  await new Promise(resolve => server.close(resolve))
  return port
}
export async function containerEnvironment() {
  assert.equal(process.platform, 'linux', 'Container E2E acceptance requires Linux')
  const directory = await mkdtemp(join(tmpdir(), 'ozon-e2e-'))
  const project = `ozon-e2e-${randomBytes(8).toString('hex')}`
  const envFile = join(directory, 'test.env')
  const manifest = join(directory, 'compose.json')
  const password = randomBytes(24).toString('hex')
  const port = await freePort()
  const values = { APP_ENV: 'test', APP_ENV_FILE: envFile, DOMAIN: 'localhost', APP_PUBLIC_URL: `https://localhost:${port}`,
    POSTGRES_PASSWORD: password, DATABASE_URL: `postgresql+psycopg://ozon:${password}@postgres:5432/ozon`,
    OZON_MOCK_MODE: 'true', OZON_WEBHOOK_ENABLED: 'true', OZON_RECONCILIATION_ENABLED: 'false',
    OZON_CLIENT_ID: '', OZON_API_KEY: '', OZON_CREDENTIALS_MASTER_KEY: '', APP_SECRET: '',
    ENABLED_OPTIONAL_FEATURES: '',
    TELEGRAM_BOT_TOKEN: 'synthetic-e2e-token', TELEGRAM_BOT_USERNAME: 'synthetic_e2e_bot', TELEGRAM_WEBHOOK_SECRET: 'synthetic-e2e-secret',
    VAPID_PUBLIC_KEY: '', VAPID_PRIVATE_KEY: '', VAPID_SUBJECT: '', UPLOAD_DIR: '/data/uploads', BACKUP_DIR: '/data/backups', E2E_PROJECT: project }
  const env = { ...process.env, ...values, COMPOSE_ENV_FILES: envFile, COMPOSE_PROJECT_NAME: project }
  await writeFile(envFile, Object.entries(values).map(([key, value]) => `${key}=${value}`).join('\n'), { mode: 0o600 })
  let logs = ''
  let started = false
  const docker = async args => {
    try {
      const output = await execute('docker', args, { cwd: root, env, maxBuffer: 16 * 1024 * 1024 })
      logs += output.stderr
      return output.stdout
    } catch (error) {
      logs += error.stderr || ''
      // No command/env expansion in exceptions; this contains synthetic logs only.
      throw new Error(`Container command failed: ${error.stderr || error.message}`)
    }
  }
  const base = ['compose', '--env-file', envFile, '-p', project, '-f', manifest]
  const compose = args => docker([...base, ...args])
  const guard = async () => {
    const config = JSON.parse(await compose(['config', '--format', 'json']))
    assert.equal(config.name, project)
    assert.deepEqual(Object.keys(config.services).sort(), ['backend', 'caddy', 'fault-proxy', 'postgres'])
    assert.equal(config.services.backend.environment.E2E_PROJECT, project)
    assert.equal(config.services.backend.environment.APP_ENV, 'test')
    assert.equal(config.services.backend.environment.OZON_MOCK_MODE, 'true')
    for (const [key, volume] of Object.entries(config.volumes)) {
      assert.equal(volume.name, `${project}_${key}`)
      assert.ok(!volume.external && !volume.driver_opts)
    }
    for (const service of Object.values(config.services))
      for (const mount of service.volumes || []) {
        if (mount.type === 'volume') assert.ok(Object.hasOwn(config.volumes, mount.source))
        else assert.ok([directory, join(root, 'backend/tests'), join(root, 'frontend/scripts/e2e/fault-proxy.mjs'), join(directory, 'Caddyfile')].includes(mount.source), 'only fixture/test-code binds allowed')
      }
  }
  const state = { outage: false, eventsOffline: false, race: false }
  const transport = async () => {
    await writeFile(join(directory, 'transport.next'), JSON.stringify(state))
    await rename(join(directory, 'transport.next'), join(directory, 'transport.json'))
  }
  const close = async () => {
    if (started) {
      logs += await compose(['logs', '--no-color', '--tail', '150']).catch(() => '')
      await guard() // Fail closed: never clean a changed/unsafe manifest.
      await compose(['down', '--volumes', '--remove-orphans'])
    }
    await rm(directory, { recursive: true, force: true })
  }
  try {
    const config = JSON.parse(await docker(['compose', '--env-file', envFile, '-p', project, '-f', join(root, 'docker-compose.yml'), 'config', '--format', 'json']))
    config.name = project
    for (const [key, volume] of Object.entries(config.volumes)) volume.name = `${project}_${key}`
    // Explicit names avoid inheriting any existing/default project network.
    for (const [key, network] of Object.entries(config.networks)) network.name = `${project}_${key}`
    const backend = config.services.backend
    backend.command = ['python', '-m', 'tests.e2e_server', '--container', '--directory', '/e2e', '--port', '8000']
    backend.volumes.push({ type: 'bind', source: join(root, 'backend/tests'), target: '/app/tests', read_only: true }, { type: 'bind', source: directory, target: '/e2e' })
    backend.restart = 'no'
    const caddy = config.services.caddy
    caddy.environment.DOMAIN = 'localhost'
    caddy.ports = [{ target: 443, published: String(port), host_ip: '127.0.0.1', protocol: 'tcp' }]
    caddy.volumes.push({ type: 'bind', source: join(directory, 'Caddyfile'), target: '/etc/caddy/Caddyfile', read_only: true })
    caddy.restart = 'no'
    config.services['fault-proxy'] = { image: 'node:22-alpine', command: ['node', '/fault-proxy.mjs'], mem_limit: '96m',
      volumes: [{ type: 'bind', source: join(root, 'frontend/scripts/e2e/fault-proxy.mjs'), target: '/fault-proxy.mjs', read_only: true }, { type: 'bind', source: directory, target: '/e2e' }],
      networks: { default: null } }
    let caddyfile = await readFile(join(root, 'deployment/Caddyfile'), 'utf8')
    // Test-only local issuer/source relaxation; production file remains unchanged.
    caddyfile = caddyfile.replace('{$DOMAIN} {', 'localhost {\n    tls internal')
      .replace(/ {4}@ozonDenied \{[\s\S]*?\n {4}\}/, '')
      .replace(/ {8}handle @ozonDenied \{[\s\S]*?\n {8}\}/, '')
      .replace('reverse_proxy backend:8000', 'reverse_proxy fault-proxy:8000')
    await writeFile(join(directory, 'Caddyfile'), caddyfile)
    await writeFile(manifest, JSON.stringify(config), { mode: 0o600 })
    await transport()
    await guard()
    for (const volume of Object.values(config.volumes)) {
      const existing = (await docker(['volume', 'ls', '-q'])).trim().split('\n')
      assert.ok(!existing.includes(volume.name), 'fixture volumes must be new')
    }
    started = true
    await compose(['up', '-d', '--build', '--wait', '--wait-timeout', '120', 'backend', 'fault-proxy', 'caddy'])
    await compose(['exec', '-T', 'caddy', 'caddy', 'validate', '--config', '/etc/caddy/Caddyfile'])
    const origin = `https://localhost:${port}`
    // Only generated loopback/internal-CA fixture. Live smoke never disables TLS verification.
    await until(() => new Promise((resolve, reject) => {
      get(`${origin}/api/health/ready`, { rejectUnauthorized: false }, response => { response.resume(); resolve(response.statusCode === 200) }).on('error', reject)
    }), 'container PostgreSQL/Caddy HTTPS readiness', 30000)
    let barrierJob
    return { directory, origin, close, logs: () => logs,
      captureLogs: async () => { logs += await compose(['logs', '--no-color', '--tail', '150']) },
      verifyDeployment: process.env.E2E_PROBE === 'true' ? async () => {
        const ids = (await compose(['ps', '-q'])).trim().split('\n').filter(Boolean)
        const probe = compose(['exec', '-T', 'backend', 'python', '-m', 'tests.deployment_probe'])
        const stats = await docker(['stats', '--no-stream', '--format', '{{json .}}', ...ids])
        console.log((await probe).trim())
        const output = join(root, 'deployment-results', project)
        await mkdir(output, { recursive: true })
        await copyFile(join(directory, 'postgres-report.json'), join(output, 'postgres-report.json'))
        await writeFile(join(output, 'docker-stats.jsonl'), stats)
        for (const service of ['backend', 'postgres', 'caddy']) {
          const rss = await compose(['exec', '-T', service, 'sh', '-c', 'for f in /proc/[0-9]*/status; do grep -E "^(Name|Pid|VmRSS):" "$f" 2>/dev/null || true; done'])
          await writeFile(join(output, `${service}-rss.txt`), rss)
        }
        console.log(`Synthetic Linux/PostgreSQL/CPU/cgroup-memory/process-RSS report: ${output}`)
      } : undefined,
      outage: async value => { state.outage = value; await transport() },
      disconnectEvents: async value => { state.eventsOffline = value; await transport() },
      raceBeforeClaim: async barrier => {
        state.race = true; await transport()
        barrierJob = (async () => {
          await until(async () => { await access(join(directory, 'claim-pending')); return true }, 'container claim barrier')
          await barrier(); state.race = false; await transport()
          await writeFile(join(directory, 'claim-release'), '')
        })()
        barrierJob.catch(error => { logs += error.stack })
      },
      changeOzon: changes => writeFile(join(directory, 'ozon-changes.json'), JSON.stringify(changes)),
      reconcile: () => compose(['exec', '-T', 'backend', 'python', '-c', 'from app.main import app; from app.ozon import MockOzonClient; from app.ozon_reconciliation import reconcile; reconcile(app.state.engine, MockOzonClient(), app.state.settings, app.state.order_events)']) }
  } catch (error) { await close(); throw error }
}
