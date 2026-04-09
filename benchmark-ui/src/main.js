import { renderRunList } from './views/run-list.js'
import { renderAnnotateQueue } from './views/annotate-queue.js'
import { renderAnnotateView } from './views/annotate.js'
import { renderIrrReport } from './views/irr-report.js'

const app = document.getElementById('app')
const breadcrumb = document.getElementById('breadcrumb')

function setBreadcrumb(parts) {
  breadcrumb.innerHTML = parts.map((p, i) => {
    if (p.href && i < parts.length - 1) {
      return `<a href="${p.href}">${p.label}</a>`
    }
    return `<span style="color:#ccc">${p.label}</span>`
  }).join(' <span style="color:#555">›</span> ')
}

function getAnnotatorId() {
  let id = localStorage.getItem('annotator_id')
  if (!id) {
    const name = prompt('Enter your annotator name (e.g. gordon):')
    id = name ? `human:${name.trim()}` : 'human:anonymous'
    localStorage.setItem('annotator_id', id)
  }
  return id
}

// Ensure annotator_id is set on first load
getAnnotatorId()

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
    await renderAnnotateQueue(app, { runId, navigate })
  } else if (parts[0] === 'runs' && parts.length === 3 && parts[2] === 'irr') {
    const runId = parts[1]
    setBreadcrumb([
      { label: 'Runs', href: '#/' },
      { label: runId, href: `#/runs/${runId}` },
      { label: 'IRR Report' },
    ])
    await renderIrrReport(app, { runId, navigate })
  } else if (parts[0] === 'runs' && parts.length === 4 && parts[2] === 'annotate') {
    const runId = parts[1]
    const promptId = parts[3]
    setBreadcrumb([
      { label: 'Runs', href: '#/' },
      { label: runId, href: `#/runs/${runId}` },
      { label: promptId },
    ])
    await renderAnnotateView(app, { runId, promptId, navigate })
  } else {
    app.innerHTML = '<p style="color:#888;padding:20px">Not found.</p>'
  }
}

function navigate(path) {
  location.hash = path
}

window.addEventListener('hashchange', route)
route()
