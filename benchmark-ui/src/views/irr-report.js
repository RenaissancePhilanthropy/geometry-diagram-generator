export async function renderIrrReport(container, { runId, navigate }) {
  container.innerHTML = '<p style="color:#888;padding:20px">Loading IRR report…</p>'

  let report
  try {
    const res = await fetch(`/api/irr/${runId}`)
    report = await res.json()
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171;padding:20px">Failed to load IRR report: ${e.message}</p>`
    return
  }

  if (report.error) {
    container.innerHTML = `
      <h2>IRR Report</h2>
      <p style="color:#888;margin-top:16px">
        Inter-rater reliability analysis is not yet available for this run.
        At least two annotators must complete annotations before IRR can be computed.
      </p>
    `
    return
  }

  const kappa = report.kappa !== undefined ? report.kappa.toFixed(3) : '—'

  const categoryRows = Object.entries(report.by_category || {}).map(([catName, cat]) => `
    <tr>
      <td>${catName}</td>
      <td>${cat.kappa !== undefined ? cat.kappa.toFixed(3) : '—'}</td>
      <td>${cat.percent_agreement !== undefined ? (cat.percent_agreement * 100).toFixed(1) + '%' : '—'}</td>
      <td style="color:#888;font-size:12px">${cat.n_pairs || 0} pairs</td>
    </tr>
  `).join('')

  const itemRows = (report.by_item || []).map(item => `
    <tr>
      <td style="font-size:12px;color:#aaa">${item.rubric_item_id}</td>
      <td>${item.category || ''}</td>
      <td>${item.n_pairs || 0}</td>
      <td>${item.agreement !== undefined ? (item.agreement * 100).toFixed(1) + '%' : '—'}</td>
    </tr>
  `).join('')

  container.innerHTML = `
    <h2>IRR Report — ${runId}</h2>

    <div style="margin-bottom:24px;">
      <div style="color:#888;font-size:12px;text-transform:uppercase;letter-spacing:0.05em;">Overall Cohen's Kappa</div>
      <div class="kappa-display">${kappa}</div>
      <div style="color:#888;font-size:12px">${report.n_annotators || 0} annotators &middot; ${report.n_pairs || 0} pairs</div>
    </div>

    ${categoryRows ? `
      <h3 style="margin-bottom:8px;">By Category</h3>
      <table style="margin-bottom:24px;">
        <thead>
          <tr>
            <th>Category</th>
            <th>Kappa</th>
            <th>Agreement</th>
            <th>Pairs</th>
          </tr>
        </thead>
        <tbody>${categoryRows}</tbody>
      </table>
    ` : ''}

    ${itemRows ? `
      <h3 style="margin-bottom:8px;">By Item</h3>
      <table>
        <thead>
          <tr>
            <th>Item ID</th>
            <th>Category</th>
            <th>Pairs</th>
            <th>Agreement</th>
          </tr>
        </thead>
        <tbody>${itemRows}</tbody>
      </table>
    ` : ''}
  `
}
