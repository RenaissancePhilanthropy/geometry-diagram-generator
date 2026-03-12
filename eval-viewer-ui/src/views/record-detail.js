import { gateBadge, checkBadge } from '../components/badges.js'

export async function renderRecordDetail(container, { runId, index, navigate }) {
  container.innerHTML = '<p style="color:#888;padding:20px">Loading…</p>'

  let record, totalRecords
  try {
    const [recRes, runRes] = await Promise.all([
      fetch(`/api/runs/${runId}/records/${index}`),
      fetch(`/api/runs/${runId}`),
    ])
    if (!recRes.ok) { container.innerHTML = `<p style="color:#f87171;padding:20px">Record not found.</p>`; return }
    record = await recRes.json()
    const allRecords = await runRes.json()
    totalRecords = allRecords.length
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171;padding:20px">Failed to load: ${e.message}</p>`
    return
  }

  const hasIR = record.diagram_ir != null
  let currentSvgSource = record.svg_path ? `svg-from-file` : null

  // Build layout
  container.innerHTML = `
    <div class="record-nav">
      ${index > 0 ? `<a href="#/runs/${runId}/records/${index - 1}" class="btn btn-primary" style="padding:4px 12px;font-size:12px">← Prev</a>` : ''}
      <span class="nav-info">Record ${index + 1} of ${totalRecords}</span>
      ${index < totalRecords - 1 ? `<a href="#/runs/${runId}/records/${index + 1}" class="btn btn-primary" style="padding:4px 12px;font-size:12px">Next →</a>` : ''}
    </div>

    <div class="record-layout">
      <!-- Left: metadata + editors -->
      <div>
        <!-- Metadata -->
        <div class="panel" style="margin-bottom:16px">
          <div class="panel-header">
            ${record.scenario_id || '—'}
            <span style="margin-left:auto">${gateBadge(record.gate_status)}</span>
          </div>
          <div class="panel-body">
            <div class="meta-grid" style="margin-bottom:12px">
              <span class="meta-key">Strategy</span><span class="meta-val">${record.strategy || '—'}</span>
              <span class="meta-key">Model</span><span class="meta-val">${record.model || '—'}</span>
              <span class="meta-key">Repeat</span><span class="meta-val">${record.repeat_index ?? '—'}</span>
              <span class="meta-key">Duration</span><span class="meta-val">${record.duration_s != null ? record.duration_s.toFixed(2) + 's' : '—'}</span>
              <span class="meta-key">LLM Judge</span><span class="meta-val">${record.llm_judge_score != null ? record.llm_judge_score + '/5' : '—'}</span>
              <span class="meta-key">Gate failures</span><span class="meta-val" style="color:#fca5a5">${(record.gate_failures || []).join(', ') || 'none'}</span>
            </div>
            <div class="prompt-text">${escapeHtml(record.user_prompt || '')}</div>
          </div>
        </div>

        <!-- Editors -->
        <div class="panel">
          <div class="tabs">
            ${hasIR ? '<button class="tab-btn active" data-tab="ir">Edit IR</button>' : ''}
            <button class="tab-btn ${hasIR ? '' : 'active'}" data-tab="tikz">Edit TikZ</button>
          </div>

          ${hasIR ? `
          <div class="tab-pane active" id="tab-ir">
            <textarea id="ir-editor" class="code-editor" style="min-height:360px">${escapeHtml(JSON.stringify(record.diagram_ir, null, 2))}</textarea>
            <div style="margin-top:10px;display:flex;align-items:center;gap:10px">
              <button class="btn btn-primary" id="btn-compile">Recompile &amp; Render</button>
              <span id="compile-spinner" style="display:none"><span class="spinner"></span></span>
            </div>
            <div id="compile-error" style="display:none"></div>
          </div>
          ` : ''}

          <div class="tab-pane ${hasIR ? '' : 'active'}" id="tab-tikz">
            <textarea id="tikz-editor" class="code-editor" style="min-height:360px">${escapeHtml(record.tikz_code || '')}</textarea>
            <div style="margin-top:10px;display:flex;align-items:center;gap:10px">
              <button class="btn btn-primary" id="btn-render">Re-render</button>
              <span id="render-spinner" style="display:none"><span class="spinner"></span></span>
            </div>
            <div id="render-error" style="display:none"></div>
          </div>
        </div>
      </div>

      <!-- Right: SVG preview + checks -->
      <div>
        <div class="panel" style="margin-bottom:16px">
          <div class="panel-header">
            SVG Preview
            <span id="svg-source-label" style="margin-left:auto;font-size:11px;color:#888;font-weight:400"></span>
          </div>
          <div class="panel-body">
            <div class="svg-preview" id="svg-container">
              <span class="svg-placeholder">Loading…</span>
            </div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-header">Check Results</div>
          <div class="panel-body">
            <div id="checks-container">${renderAllChecks(record)}</div>
          </div>
        </div>
      </div>
    </div>
  `

  // Load initial SVG
  if (record.svg_path) {
    loadSvgFromFile(runId, index)
  } else {
    document.getElementById('svg-container').innerHTML = '<span class="svg-placeholder">No SVG available</span>'
    document.getElementById('svg-source-label').textContent = 'no SVG saved'
  }

  // Tab switching
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'))
      container.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'))
      btn.classList.add('active')
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active')
    })
  })

  // Compile IR button
  if (hasIR) {
    document.getElementById('btn-compile').addEventListener('click', async () => {
      const btn = document.getElementById('btn-compile')
      const spinner = document.getElementById('compile-spinner')
      const errBox = document.getElementById('compile-error')

      btn.disabled = true
      spinner.style.display = 'inline'
      errBox.style.display = 'none'

      let irData
      try {
        irData = JSON.parse(document.getElementById('ir-editor').value)
      } catch (e) {
        showError(errBox, `JSON parse error: ${e.message}`)
        btn.disabled = false
        spinner.style.display = 'none'
        return
      }

      try {
        const res = await fetch('/api/compile-ir', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ diagram_ir: irData }),
        })
        const data = await res.json()
        if (!res.ok) {
          showError(errBox, data.error || 'Compilation failed')
        } else {
          // Update TikZ editor with generated code (read from result)
          document.getElementById('tikz-editor').value = data.tikz_code || ''
          setSvgContent(data.svg, 'recompiled from IR')
          document.getElementById('checks-container').innerHTML = renderCheckResults(data.checks || [])
        }
      } catch (e) {
        showError(errBox, `Request failed: ${e.message}`)
      }

      btn.disabled = false
      spinner.style.display = 'none'
    })
  }

  // Re-render TikZ button
  document.getElementById('btn-render').addEventListener('click', async () => {
    const btn = document.getElementById('btn-render')
    const spinner = document.getElementById('render-spinner')
    const errBox = document.getElementById('render-error')

    btn.disabled = true
    spinner.style.display = 'inline'
    errBox.style.display = 'none'

    const tikzCode = document.getElementById('tikz-editor').value
    try {
      const res = await fetch('/api/render-tikz', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ tikz_code: tikzCode }),
      })
      const data = await res.json()
      if (!res.ok) {
        showError(errBox, data.error || 'Render failed')
      } else {
        setSvgContent(data.svg, 're-rendered from TikZ')
      }
    } catch (e) {
      showError(errBox, `Request failed: ${e.message}`)
    }

    btn.disabled = false
    spinner.style.display = 'none'
  })
}

async function loadSvgFromFile(runId, index) {
  const container = document.getElementById('svg-container')
  const label = document.getElementById('svg-source-label')
  try {
    const res = await fetch(`/api/runs/${runId}/svg/${index}`)
    if (!res.ok) throw new Error('SVG not found')
    const svg = await res.text()
    setSvgContent(svg, 'saved SVG')
  } catch {
    container.innerHTML = '<span class="svg-placeholder">SVG file not available</span>'
    label.textContent = 'file missing'
  }
}

function setSvgContent(svgString, sourceLabel) {
  const container = document.getElementById('svg-container')
  const label = document.getElementById('svg-source-label')
  if (!svgString) {
    container.innerHTML = '<span class="svg-placeholder">No SVG</span>'
    return
  }
  container.innerHTML = svgString
  // Make SVGs responsive
  const svgEl = container.querySelector('svg')
  if (svgEl) {
    svgEl.style.maxWidth = '100%'
    svgEl.style.height = 'auto'
  }
  if (label) label.textContent = sourceLabel || ''
}

function showError(el, message) {
  el.className = 'error-box'
  el.textContent = message
  el.style.display = 'block'
}

function renderAllChecks(record) {
  const sections = []

  if (record.tikz_checks) {
    const items = Object.entries(record.tikz_checks).map(([name, result]) => {
      if (typeof result !== 'object') return null
      const passed = result.passed
      const skipped = result.skipped
      return checkItem(name, passed, skipped, result.error || '')
    }).filter(Boolean)
    if (items.length) sections.push(`<h3>TikZ Checks</h3><div class="check-list">${items.join('')}</div>`)
  }

  if (record.svg_checks) {
    const failures = record.svg_checks.failures || []
    const passed = record.svg_checks.passed
    sections.push(`<h3 style="margin-top:12px">SVG Checks</h3><div class="check-list">${checkItem('svg', passed, false, failures.join(', '))}</div>`)
  }

  if (record.expected_point_checks) {
    const items = Object.entries(record.expected_point_checks).map(([name, result]) => {
      return checkItem(name, result.passed, false, result.message || '')
    })
    if (items.length) sections.push(`<h3 style="margin-top:12px">Point Checks</h3><div class="check-list">${items.join('')}</div>`)
  }

  if (!sections.length) return '<p style="color:#888;font-size:12px">No checks available.</p>'
  return sections.join('')
}

function renderCheckResults(checks) {
  if (!checks.length) return '<p style="color:#888;font-size:12px">No checks.</p>'
  const items = checks.map(c => checkItem(
    c.check?.kind || 'check',
    c.passed,
    false,
    c.message || ''
  ))
  return `<h3>IR Checks</h3><div class="check-list">${items.join('')}</div>`
}

function checkItem(name, passed, skipped, message) {
  const cls = skipped ? 'skip' : passed ? 'pass' : 'fail'
  const icon = skipped ? '⊘' : passed ? '✓' : '✗'
  return `
    <div class="check-item ${cls}">
      <span class="check-icon">${icon}</span>
      <div>
        <div class="check-name">${escapeHtml(String(name))}</div>
        ${message ? `<div class="check-msg">${escapeHtml(String(message))}</div>` : ''}
      </div>
    </div>
  `
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
