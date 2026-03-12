import { renderRunList } from './views/run-list.js'
import { renderRunDetail } from './views/run-detail.js'
import { renderRecordDetail } from './views/record-detail.js'

const app = document.getElementById('app')
const breadcrumb = document.getElementById('breadcrumb')

function setBreadcrumb(parts) {
  // parts: [{label, href?}, ...]
  breadcrumb.innerHTML = parts.map((p, i) => {
    if (p.href && i < parts.length - 1) {
      return `<a href="${p.href}">${p.label}</a>`
    }
    return `<span style="color:#ccc">${p.label}</span>`
  }).join(' <span style="color:#555">›</span> ')
}

async function route() {
  const hash = location.hash.replace(/^#\/?/, '') || ''
  const parts = hash.split('/').filter(Boolean)

  app.innerHTML = ''

  if (parts.length === 0) {
    setBreadcrumb([{ label: 'Runs' }])
    await renderRunList(app, { navigate })
  } else if (parts[0] === 'runs' && parts.length === 2) {
    const runId = parts[1]
    setBreadcrumb([
      { label: 'Runs', href: '#/' },
      { label: runId },
    ])
    await renderRunDetail(app, { runId, navigate })
  } else if (parts[0] === 'runs' && parts.length === 4 && parts[2] === 'records') {
    const runId = parts[1]
    const index = parseInt(parts[3], 10)
    setBreadcrumb([
      { label: 'Runs', href: '#/' },
      { label: runId, href: `#/runs/${runId}` },
      { label: `Record ${index}` },
    ])
    await renderRecordDetail(app, { runId, index, navigate })
  } else {
    app.innerHTML = '<p style="color:#888;padding:20px">Not found.</p>'
  }
}

function navigate(path) {
  location.hash = path
}

window.addEventListener('hashchange', route)
route()
