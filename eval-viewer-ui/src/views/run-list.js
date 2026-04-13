import { fetchRuns } from '../api.js'

export async function renderRunList(container, { navigate }) {
  container.innerHTML = '<p style="color:#888;padding:20px">Loading runs…</p>'

  let runs
  try {
    runs = await fetchRuns()
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171;padding:20px">Failed to load runs: ${e.message}</p>`
    return
  }

  if (runs.length === 0) {
    container.innerHTML = '<p style="color:#888;padding:20px">No eval runs found in evals/results/.</p>'
    return
  }

  const html = `
    <h2>Eval Runs</h2>
    <table>
      <thead>
        <tr>
          <th>Run ID</th>
          <th>Records</th>
          <th>Strategies</th>
          <th>Pass</th>
          <th>Soft Pass</th>
          <th>Fail</th>
        </tr>
      </thead>
      <tbody>
        ${runs.map(run => {
          const gc = run.gate_counts || {}
          const pass = gc['pass'] || 0
          const soft = gc['soft_pass'] || 0
          const fail = gc['fail'] || 0
          return `
            <tr class="clickable" data-run="${run.run_id}">
              <td><a href="#/runs/${run.run_id}">${run.run_id}</a></td>
              <td>${run.record_count}</td>
              <td style="color:#aaa;font-size:12px">${(run.strategies || []).join(', ')}</td>
              <td>${pass > 0 ? `<span class="badge badge-pass">${pass}</span>` : '<span style="color:#555">—</span>'}</td>
              <td>${soft > 0 ? `<span class="badge badge-soft_pass">${soft}</span>` : '<span style="color:#555">—</span>'}</td>
              <td>${fail > 0 ? `<span class="badge badge-fail">${fail}</span>` : '<span style="color:#555">—</span>'}</td>
            </tr>
          `
        }).join('')}
      </tbody>
    </table>
  `

  container.innerHTML = html

  container.querySelectorAll('tr.clickable').forEach(row => {
    row.addEventListener('click', (e) => {
      if (e.target.tagName === 'A') return
      navigate(`#/runs/${row.dataset.run}`)
    })
  })
}
