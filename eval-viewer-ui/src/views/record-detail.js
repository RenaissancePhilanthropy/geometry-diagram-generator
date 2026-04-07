import { gateBadge, checkBadge } from '../components/badges.js'
import { renderDiff } from '../components/diff.js'

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
  const hasRecipe = record.recipe_dsl != null

  // Originals for diff comparison
  const originalIR = hasIR ? JSON.stringify(record.diagram_ir, null, 2) : ''
  const originalTikZ = record.tikz_code || ''

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
            <span style="margin-left:8px;font-size:11px;color:#888">${record.benchmark || ''}${record.tier != null ? ` · tier ${record.tier}` : ''}${(record.tags || []).length ? ` · ${record.tags.join(', ')}` : ''}</span>
            <span style="margin-left:auto">${gateBadge(record.gate_status)}</span>
          </div>
          <div class="panel-body">
            <div class="meta-grid" style="margin-bottom:12px">
              <span class="meta-key">Strategy</span><span class="meta-val">${record.strategy || '—'}</span>
              <span class="meta-key">Model</span><span class="meta-val">${record.model || '—'}</span>
              <span class="meta-key">Repeat</span><span class="meta-val">${record.repeat_index ?? '—'}</span>
              <span class="meta-key">Timestamp</span><span class="meta-val" style="font-size:12px">${record.timestamp ? new Date(record.timestamp).toLocaleString() : '—'}</span>
              <span class="meta-key">Duration</span><span class="meta-val">${record.duration_s != null ? record.duration_s.toFixed(2) + 's' : '—'}</span>
              ${record.input_tokens != null ? `<span class="meta-key">Tokens</span><span class="meta-val">${record.input_tokens.toLocaleString()} in / ${(record.output_tokens ?? 0).toLocaleString()} out</span>` : ''}
              ${record.tool_calls > 0 ? `<span class="meta-key">Tool calls</span><span class="meta-val">${record.tool_calls}${record.retries > 0 ? ` (${record.retries} retr${record.retries === 1 ? 'y' : 'ies'})` : ''}</span>` : ''}
              <span class="meta-key">Generated</span><span class="meta-val">${statusDot(record.generation_success)} SVG: ${statusDot(record.svg_rendered)} Checks: ${statusDot(record.deterministic_pass)}</span>
              <span class="meta-key">Gate failures</span><span class="meta-val" style="color:#fca5a5">${(record.gate_failures || []).join(', ') || 'none'}</span>
              ${record.error ? `<span class="meta-key">Error</span><span class="meta-val" style="color:#fca5a5;font-size:12px">${escapeHtml(record.error)}</span>` : ''}
            </div>
            <div class="prompt-text">${escapeHtml(record.user_prompt || '')}</div>
          </div>
        </div>

        <!-- Judge scores -->
        ${renderJudgePanel(record)}

        <!-- Renderer selector -->
        <div style="padding:10px 14px;background:#1a1a1a;border:1px solid #333;border-radius:6px;margin-bottom:16px;display:flex;align-items:center;gap:10px">
          <label style="color:#888;font-size:12px;white-space:nowrap">Renderer:</label>
          <select id="renderer-select" style="background:#1e1e1e;border:1px solid #333;color:#e0e0e0;padding:4px 8px;border-radius:4px;font-size:13px">
            <option value="svg">SVG (no Docker)</option>
            <option value="tikz">TikZ (Docker)</option>
          </select>
          <span id="tikz-status" style="font-size:11px;color:#888"></span>
        </div>

        <!-- Editors -->
        <div class="panel">
          <div class="tabs">
            ${hasRecipe ? '<button class="tab-btn active" data-tab="recipe">Edit Recipe</button>' : ''}
            ${hasIR ? `<button class="tab-btn ${hasRecipe ? '' : 'active'}" data-tab="ir">Edit IR</button>` : ''}
            <button class="tab-btn ${hasRecipe || hasIR ? '' : 'active'}" data-tab="tikz">Edit TikZ</button>
          </div>

          ${hasRecipe ? `
          <div class="tab-pane active" id="tab-recipe">
            <textarea id="recipe-editor" class="code-editor" style="min-height:360px">${escapeHtml(JSON.stringify(record.recipe_dsl, null, 2))}</textarea>
            <div style="margin-top:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <button class="btn btn-primary" id="btn-compile-recipe">Compile Recipe</button>
              <span id="recipe-spinner" style="display:none"><span class="spinner"></span></span>
            </div>
            <div id="recipe-error" style="display:none"></div>
          </div>
          ` : ''}

          ${hasIR ? `
          <div class="tab-pane ${hasRecipe ? '' : 'active'}" id="tab-ir">
            <textarea id="ir-editor" class="code-editor" style="min-height:360px">${escapeHtml(originalIR)}</textarea>
            <div style="margin-top:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <button class="btn btn-primary" id="btn-compile">Recompile &amp; Render</button>
              <button class="btn" id="btn-ir-diff" style="background:#2a2a2a;color:#ccc">Show Diff</button>
              <span id="compile-spinner" style="display:none"><span class="spinner"></span></span>
            </div>
            <div id="compile-error" style="display:none"></div>
            <div id="ir-diff-container" style="display:none"></div>
          </div>
          ` : ''}

          <div class="tab-pane ${hasRecipe || hasIR ? '' : 'active'}" id="tab-tikz">
            <textarea id="tikz-editor" class="code-editor" style="min-height:360px">${escapeHtml(originalTikZ)}</textarea>
            <div style="margin-top:10px;display:flex;align-items:center;gap:10px;flex-wrap:wrap">
              <button class="btn btn-primary" id="btn-render">Re-render</button>
              <button class="btn" id="btn-tikz-diff" style="background:#2a2a2a;color:#ccc">Show Diff</button>
              <span id="render-spinner" style="display:none"><span class="spinner"></span></span>
            </div>
            <div id="render-error" style="display:none"></div>
            <div id="tikz-diff-container" style="display:none"></div>
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

  // Check renderer status
  checkRendererStatus()

  // Tab switching
  container.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      container.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'))
      container.querySelectorAll('.tab-pane').forEach(p => p.classList.remove('active'))
      btn.classList.add('active')
      document.getElementById(`tab-${btn.dataset.tab}`).classList.add('active')
    })
  })

  // Diff toggles
  setupDiffToggle('btn-ir-diff', 'ir-diff-container', () => [
    originalIR,
    document.getElementById('ir-editor').value,
  ])
  setupDiffToggle('btn-tikz-diff', 'tikz-diff-container', () => [
    originalTikZ,
    document.getElementById('tikz-editor').value,
  ])

  // Compile Recipe button
  if (hasRecipe) {
    document.getElementById('btn-compile-recipe').addEventListener('click', async () => {
      const btn = document.getElementById('btn-compile-recipe')
      const spinner = document.getElementById('recipe-spinner')
      const errBox = document.getElementById('recipe-error')

      btn.disabled = true
      spinner.style.display = 'inline'
      errBox.style.display = 'none'

      let recipeData
      try {
        recipeData = JSON.parse(document.getElementById('recipe-editor').value)
      } catch (e) {
        showError(errBox, `JSON parse error: ${e.message}`)
        btn.disabled = false
        spinner.style.display = 'none'
        return
      }

      try {
        const res = await fetch('/api/compile-recipe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            recipe_dsl: recipeData,
            renderer: document.getElementById('renderer-select').value,
          }),
        })
        const data = await res.json()
        if (!res.ok) {
          showError(errBox, formatError(data))
        } else {
          // Update IR editor with lowered IR
          const irEditor = document.getElementById('ir-editor')
          if (irEditor) irEditor.value = JSON.stringify(data.diagram_ir, null, 2)
          updateAfterCompile(data, 'compiled from Recipe')
        }
      } catch (e) {
        showError(errBox, `Request failed: ${e.message}`)
      }

      btn.disabled = false
      spinner.style.display = 'none'
    })
  }

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
          body: JSON.stringify({
            diagram_ir: irData,
            renderer: document.getElementById('renderer-select').value,
          }),
        })
        const data = await res.json()
        if (!res.ok) {
          showError(errBox, formatError(data))
        } else {
          updateAfterCompile(data, 'recompiled from IR')
          refreshDiffIfVisible('ir-diff-container', originalIR, document.getElementById('ir-editor').value)
          refreshDiffIfVisible('tikz-diff-container', originalTikZ, data.tikz_code || '')
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
        showError(errBox, formatError(data))
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

// Shared post-compile update: sets TikZ editor, SVG, and checks
function updateAfterCompile(data, svgLabel) {
  const tikzEditor = document.getElementById('tikz-editor')
  const renderBtn = document.getElementById('btn-render')
  if (tikzEditor) {
    tikzEditor.value = data.tikz_code || ''
  }
  if (renderBtn) {
    if (!data.tikz_code) {
      renderBtn.disabled = true
      renderBtn.title = 'No TikZ code (SVG renderer used)'
    } else {
      renderBtn.disabled = false
      renderBtn.title = ''
    }
  }
  setSvgContent(data.svg, svgLabel + (data.renderer ? ` via ${data.renderer}` : ''))
  document.getElementById('checks-container').innerHTML = renderCheckResults(data.checks || [])
}

async function checkRendererStatus() {
  const select = document.getElementById('renderer-select')
  const status = document.getElementById('tikz-status')
  if (!select || !status) return
  try {
    const res = await fetch('/api/renderer-status')
    const data = await res.json()
    if (!data.tikz) {
      const tikzOpt = select.querySelector('option[value="tikz"]')
      if (tikzOpt) {
        tikzOpt.disabled = true
        tikzOpt.text = 'TikZ (Docker — unavailable)'
      }
      status.textContent = 'TikZ renderer not reachable'
    }
  } catch {
    // If the status check fails, leave both options enabled
  }
}

function setupDiffToggle(btnId, containerId, getTexts) {
  const btn = document.getElementById(btnId)
  const container = document.getElementById(containerId)
  if (!btn || !container) return

  let shown = false
  btn.addEventListener('click', () => {
    shown = !shown
    if (shown) {
      const [oldText, newText] = getTexts()
      container.innerHTML = renderDiff(oldText, newText)
      container.style.display = 'block'
      btn.textContent = 'Hide Diff'
      btn.style.color = '#60a5fa'
    } else {
      container.style.display = 'none'
      btn.textContent = 'Show Diff'
      btn.style.color = '#ccc'
    }
  })
}

function refreshDiffIfVisible(containerId, oldText, newText) {
  const container = document.getElementById(containerId)
  if (container && container.style.display !== 'none') {
    container.innerHTML = renderDiff(oldText, newText)
  }
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

function formatError(data) {
  const stage = data.stage ? `[${data.stage}] ` : ''
  return stage + (data.error || 'Unknown error')
}

function renderAllChecks(record) {
  const sections = []

  if (record.tikz_checks) {
    const items = Object.entries(record.tikz_checks).map(([name, result]) => {
      if (typeof result !== 'object') return null
      const label = result.type ? `${name} <span style="color:#555;font-size:11px">${result.type}</span>` : name
      return checkItem(label, result.passed, result.skipped, result.error || '', /*rawLabel=*/true)
    }).filter(Boolean)
    if (items.length) sections.push(`<h3>TikZ Checks</h3><div class="check-list">${items.join('')}</div>`)
  }

  if (record.svg_checks) {
    const failures = record.svg_checks.failures || []
    let svgItems
    if (failures.length) {
      svgItems = failures.map(f => checkItem('svg', false, false, f))
    } else {
      svgItems = [checkItem('svg', record.svg_checks.passed, false, record.svg_checks.passed ? 'well-formed · has content · reasonable size' : '')]
    }
    sections.push(`<h3 style="margin-top:12px">SVG Checks</h3><div class="check-list">${svgItems.join('')}</div>`)
  }

  if (record.expected_point_checks) {
    const epc = record.expected_point_checks
    const parts = []
    if (epc.missing && epc.missing.length) parts.push(`missing: ${epc.missing.join(', ')}`)
    if (epc.mismatches) {
      for (const [pt, info] of Object.entries(epc.mismatches)) {
        parts.push(`${pt}: expected (${info.expected}), got (${info.actual}), err=${info.error?.toFixed(4)}`)
      }
    }
    const msg = parts.join('; ')
    sections.push(`<h3 style="margin-top:12px">Point Checks</h3><div class="check-list">${checkItem('expected points', epc.passed, false, msg)}</div>`)
  }

  if (!sections.length) return '<p style="color:#888;font-size:12px">No checks available.</p>'
  return sections.join('')
}

function renderCheckResults(checks) {
  if (!checks.length) return '<p style="color:#888;font-size:12px">No checks.</p>'
  const items = checks.map(c => {
    const source = c.check?.source
    const level = c.check?.level || 'must'
    const sourceTag = source
      ? `<span class="source-tag">${escapeHtml(source)}</span>`
      : ''
    const kindLabel = sourceTag + escapeHtml(c.check?.kind || 'check')
    return checkItem(kindLabel, c.passed, false, c.message || '', /*rawLabel=*/true, level)
  })
  return `<h3>IR Checks</h3><div class="check-list">${items.join('')}</div>`
}

function checkItem(name, passed, skipped, message, rawLabel = false, level = 'must') {
  const isWarn = !passed && !skipped && level === 'prefer'
  const cls = skipped ? 'skip' : passed ? 'pass' : isWarn ? 'warn' : 'fail'
  const icon = skipped ? '⊘' : passed ? '✓' : '✗'
  const nameHtml = rawLabel ? name : escapeHtml(String(name))

  // Split on " | " to separate failure message from candidate hints
  let mainMsg = message
  let hints = ''
  const pipeIdx = message.indexOf(' | ')
  if (pipeIdx !== -1) {
    mainMsg = message.substring(0, pipeIdx)
    hints = message.substring(pipeIdx + 3)
  }

  return `
    <div class="check-item ${cls}">
      <span class="check-icon">${icon}</span>
      <div>
        <div class="check-name">${nameHtml}</div>
        ${mainMsg ? `<div class="check-msg">${escapeHtml(String(mainMsg))}</div>` : ''}
        ${hints ? `<div class="check-hint">Hint: ${escapeHtml(hints)}</div>` : ''}
      </div>
    </div>
  `
}

function statusDot(val) {
  if (val === true) return '<span style="color:#86efac">✓</span>'
  if (val === false) return '<span style="color:#fca5a5">✗</span>'
  return '<span style="color:#555">—</span>'
}

function renderJudgePanel(record) {
  const hasLLM = record.llm_judge_score != null
  const hasVisual = record.visual_judge_score != null
  if (!hasLLM && !hasVisual) return ''

  const details = record.llm_judge_details || {}
  const subScores = ['geometric_accuracy', 'labeling', 'completeness', 'likely_renders']

  return `
    <div class="panel" style="margin-bottom:16px">
      <div class="panel-header">Judge Scores</div>
      <div class="panel-body">
        ${hasLLM ? `
          <div style="margin-bottom:10px">
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
              <span style="font-weight:600;font-size:13px;color:#ccc">LLM Judge</span>
              <span style="font-size:18px;font-weight:700;color:${scoreColor(record.llm_judge_score)}">${record.llm_judge_score}/5</span>
            </div>
            ${subScores.filter(k => details[k] != null).length ? `
              <div style="display:flex;gap:8px;flex-wrap:wrap;margin-bottom:8px">
                ${subScores.filter(k => details[k] != null).map(k => `
                  <span style="background:#1a1a1a;border:1px solid #333;border-radius:4px;padding:2px 8px;font-size:11px">
                    <span style="color:#888">${k.replace(/_/g, ' ')}</span>
                    <span style="color:${scoreColor(details[k])};font-weight:600;margin-left:4px">${details[k]}</span>
                  </span>
                `).join('')}
              </div>
            ` : ''}
            ${record.llm_judge_reasoning ? `<div style="font-size:12px;color:#aaa;line-height:1.5;border-left:2px solid #333;padding-left:10px">${escapeHtml(record.llm_judge_reasoning)}</div>` : ''}
          </div>
        ` : ''}
        ${hasVisual ? `
          <div ${hasLLM ? 'style="border-top:1px solid #222;padding-top:10px"' : ''}>
            <div style="display:flex;align-items:center;gap:12px;margin-bottom:6px">
              <span style="font-weight:600;font-size:13px;color:#ccc">Visual Judge</span>
              <span style="font-size:18px;font-weight:700;color:${scoreColor(record.visual_judge_score)}">${record.visual_judge_score}/5</span>
            </div>
            ${record.visual_judge_reasoning ? `<div style="font-size:12px;color:#aaa;line-height:1.5;border-left:2px solid #333;padding-left:10px">${escapeHtml(record.visual_judge_reasoning)}</div>` : ''}
          </div>
        ` : ''}
      </div>
    </div>
  `
}

function scoreColor(score) {
  if (score >= 4) return '#86efac'
  if (score >= 3) return '#fde68a'
  return '#fca5a5'
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
}
