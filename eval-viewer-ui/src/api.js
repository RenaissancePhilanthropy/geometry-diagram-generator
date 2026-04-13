/**
 * API layer that works in both live (backend on /api) and static (/data) modes.
 *
 * On first call we probe for /data/runs.json — if it exists, all subsequent
 * reads use the pre-exported static files.  The compile-ir and render-tikz
 * endpoints are only available in live mode.
 */

let _mode = null // 'live' | 'static'

// Vite injects import.meta.env.BASE_URL from the `base` config (e.g. "/geometry-diagram-generator/")
const BASE = import.meta.env.BASE_URL ?? '/'

function url(path) {
  return `${BASE}${path}`.replace(/\/\/+/g, '/')
}

async function detectMode() {
  if (_mode) return _mode
  try {
    const res = await fetch(url('data/runs.json'), { method: 'HEAD' })
    _mode = res.ok ? 'static' : 'live'
  } catch {
    _mode = 'live'
  }
  return _mode
}

export async function fetchRuns() {
  const mode = await detectMode()
  if (mode === 'static') {
    const res = await fetch(url('data/runs.json'))
    return res.json()
  }
  const res = await fetch('/api/runs')
  return res.json()
}

export async function fetchRun(runId) {
  const mode = await detectMode()
  if (mode === 'static') {
    const res = await fetch(url(`data/runs/${runId}/index.json`))
    if (!res.ok) return { ok: false }
    return { ok: true, data: await res.json() }
  }
  const res = await fetch(`/api/runs/${runId}`)
  if (!res.ok) return { ok: false }
  return { ok: true, data: await res.json() }
}

export async function fetchRecord(runId, index) {
  const mode = await detectMode()
  if (mode === 'static') {
    const res = await fetch(url(`data/runs/${runId}/records/${index}.json`))
    if (!res.ok) return { ok: false }
    return { ok: true, data: await res.json() }
  }
  const res = await fetch(`/api/runs/${runId}/records/${index}`)
  if (!res.ok) return { ok: false }
  return { ok: true, data: await res.json() }
}

export async function fetchSvg(runId, index) {
  const mode = await detectMode()
  if (mode === 'static') {
    const res = await fetch(url(`data/runs/${runId}/svg/${index}.svg`))
    if (!res.ok) return null
    return res.text()
  }
  const res = await fetch(`/api/runs/${runId}/svg/${index}`)
  if (!res.ok) return null
  return res.text()
}

export async function compileIR(diagramIR) {
  const res = await fetch('/api/compile-ir', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ diagram_ir: diagramIR }),
  })
  const data = await res.json()
  return { ok: res.ok, data }
}

export async function renderTikz(tikzCode) {
  const res = await fetch('/api/render-tikz', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ tikz_code: tikzCode }),
  })
  const data = await res.json()
  return { ok: res.ok, data }
}

export function isStaticMode() {
  return _mode === 'static'
}
