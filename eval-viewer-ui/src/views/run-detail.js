import { gateBadge } from '../components/badges.js'

export async function renderRunDetail(container, { runId, navigate }) {
  container.innerHTML = '<p style="color:#888;padding:20px">Loading…</p>'

  let records
  try {
    const res = await fetch(`/api/runs/${runId}`)
    if (!res.ok) { container.innerHTML = `<p style="color:#f87171;padding:20px">Run not found.</p>`; return }
    records = await res.json()
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171;padding:20px">Failed to load: ${e.message}</p>`
    return
  }

  const strategies = [...new Set(records.map(r => r.strategy).filter(Boolean))].sort()
  const gateValues = ['pass', 'soft_pass', 'fail']

  function render(filterStrategy, filterGate, filterScenario) {
    let filtered = records
    if (filterStrategy) filtered = filtered.filter(r => r.strategy === filterStrategy)
    if (filterGate) filtered = filtered.filter(r => r.gate_status === filterGate)
    if (filterScenario) {
      const q = filterScenario.toLowerCase()
      filtered = filtered.filter(r => (r.scenario_id || '').toLowerCase().includes(q))
    }

    const rows = filtered.map((r, _) => {
      const idx = records.indexOf(r)
      const dur = r.duration_s != null ? r.duration_s.toFixed(1) + 's' : '—'
      const llm = r.llm_judge_score != null ? r.llm_judge_score : '—'
      const vis = r.visual_judge_score != null ? r.visual_judge_score : '—'
      const hasIr = r.diagram_ir != null ? '<span title="IR available" style="color:#86efac">●</span>' : '<span title="No IR" style="color:#555">○</span>'
      const failures = (r.gate_failures || []).slice(0, 3).join(', ')
      return `
        <tr class="clickable" data-idx="${idx}">
          <td>${r.scenario_id || '—'}</td>
          <td style="color:#aaa;font-size:12px">${r.strategy || '—'}</td>
          <td style="color:#888">${r.repeat_index ?? '—'}</td>
          <td>${gateBadge(r.gate_status)}</td>
          <td style="color:#888;font-size:11px">${failures || ''}</td>
          <td style="color:#aaa">${llm}</td>
          <td style="color:#aaa">${vis}</td>
          <td style="color:#888">${dur}</td>
          <td style="text-align:center">${hasIr}</td>
        </tr>
      `
    }).join('')

    document.getElementById('run-tbody').innerHTML = rows || '<tr><td colspan="9" style="color:#888;padding:20px;text-align:center">No records match filters.</td></tr>'

    document.querySelectorAll('#run-tbody tr.clickable').forEach(row => {
      row.addEventListener('click', () => navigate(`#/runs/${runId}/records/${row.dataset.idx}`))
    })
  }

  container.innerHTML = `
    <h2>Run: ${runId} <span style="font-size:14px;color:#888;font-weight:400">(${records.length} records)</span></h2>
    <div class="filters">
      <label>Strategy
        <select id="filter-strategy">
          <option value="">All</option>
          ${strategies.map(s => `<option value="${s}">${s}</option>`).join('')}
        </select>
      </label>
      <label>Gate
        <select id="filter-gate">
          <option value="">All</option>
          ${gateValues.map(g => `<option value="${g}">${g}</option>`).join('')}
        </select>
      </label>
      <label>Scenario
        <input id="filter-scenario" type="text" placeholder="Search…" style="width:160px" />
      </label>
    </div>
    <table>
      <thead>
        <tr>
          <th>Scenario</th>
          <th>Strategy</th>
          <th>#</th>
          <th>Gate</th>
          <th>Failures</th>
          <th>LLM Judge</th>
          <th>Visual Judge</th>
          <th>Duration</th>
          <th title="IR available">IR</th>
        </tr>
      </thead>
      <tbody id="run-tbody"></tbody>
    </table>
  `

  render('', '', '')

  document.getElementById('filter-strategy').addEventListener('change', e => {
    render(e.target.value, document.getElementById('filter-gate').value, document.getElementById('filter-scenario').value)
  })
  document.getElementById('filter-gate').addEventListener('change', e => {
    render(document.getElementById('filter-strategy').value, e.target.value, document.getElementById('filter-scenario').value)
  })
  let searchTimeout
  document.getElementById('filter-scenario').addEventListener('input', e => {
    clearTimeout(searchTimeout)
    searchTimeout = setTimeout(() => {
      render(document.getElementById('filter-strategy').value, document.getElementById('filter-gate').value, e.target.value)
    }, 150)
  })
}
