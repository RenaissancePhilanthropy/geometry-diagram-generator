import { escapeHtml } from './html.js'

export function gateBadge(status) {
  const cls = status ? `badge-${escapeHtml(status)}` : 'badge-null'
  return `<span class="badge ${cls}">${escapeHtml(status || 'unknown')}</span>`
}

export function checkBadge(passed, skipped) {
  if (skipped) return '<span class="badge" style="background:#1a1a1a;color:#888">skip</span>'
  if (passed) return '<span class="badge badge-pass">pass</span>'
  return '<span class="badge badge-fail">fail</span>'
}
