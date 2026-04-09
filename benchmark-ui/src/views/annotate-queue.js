export async function renderAnnotateQueue(container, { runId, navigate }) {
  container.innerHTML = '<p style="color:#888;padding:20px">Loading queue…</p>'

  let queue, runMeta
  try {
    const [qRes, rRes] = await Promise.all([
      fetch(`/api/runs/${runId}/queue`),
      fetch(`/api/runs`),
    ])
    queue = await qRes.json()
    const runs = await rRes.json()
    runMeta = runs.find(r => r.run_id === runId) || {}
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171;padding:20px">Failed to load queue: ${e.message}</p>`
    return
  }

  const label = runMeta.label || runId

  const html = `
    <div class="header-bar">
      <div>
        <h2>${label}</h2>
        <div class="meta-row">Run ID: ${runId}${runMeta.benchmark_id ? ` &middot; Benchmark: ${runMeta.benchmark_id}` : ''}</div>
      </div>
      <a href="#/runs/${runId}/irr">View IRR Report</a>
    </div>
    <table>
      <thead>
        <tr>
          <th>#</th>
          <th>Prompt ID</th>
          <th>Generated?</th>
          <th>Annotated?</th>
        </tr>
      </thead>
      <tbody>
        ${queue.map((item, idx) => {
          const generated = item.generation_success
            ? '<span style="color:#4ade80">Yes</span>'
            : '<span style="color:#555">No</span>'
          const annotated = item.annotated
            ? '<span class="badge badge-done">Yes</span>'
            : '<span style="color:#555">No</span>'
          return `
            <tr class="clickable" data-run="${runId}" data-prompt="${item.prompt_id}">
              <td style="color:#555;font-size:12px">${idx + 1}</td>
              <td><a href="#/runs/${runId}/annotate/${item.prompt_id}">${item.prompt_id}</a></td>
              <td>${generated}</td>
              <td>${annotated}</td>
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
      navigate(`#/runs/${row.dataset.run}/annotate/${row.dataset.prompt}`)
    })
  })
}
