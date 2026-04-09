export async function renderRunList(container, { navigate }) {
  container.innerHTML = '<p style="color:#888;padding:20px">Loading runs…</p>'

  let runs
  try {
    const res = await fetch('/api/runs')
    runs = await res.json()
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171;padding:20px">Failed to load runs: ${e.message}</p>`
    return
  }

  if (runs.length === 0) {
    container.innerHTML = '<p style="color:#888;padding:20px">No benchmark runs found.</p>'
    return
  }

  const html = `
    <h2>Benchmark Runs</h2>
    <table>
      <thead>
        <tr>
          <th>Run ID</th>
          <th>Label</th>
          <th>Benchmark</th>
          <th>Date</th>
          <th>Results</th>
          <th>Annotated</th>
        </tr>
      </thead>
      <tbody>
        ${runs.map(run => {
          const annotated = run.annotated_count || 0
          const total = run.result_count || 0
          const date = run.date ? new Date(run.date).toLocaleDateString() : '—'
          return `
            <tr class="clickable" data-run="${run.run_id}">
              <td><a href="#/runs/${run.run_id}">${run.run_id}</a></td>
              <td style="color:#ccc">${run.label || '—'}</td>
              <td style="color:#aaa;font-size:12px">${run.benchmark || '—'}</td>
              <td style="color:#888;font-size:12px">${date}</td>
              <td>${total}</td>
              <td>${annotated} / ${total}</td>
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
