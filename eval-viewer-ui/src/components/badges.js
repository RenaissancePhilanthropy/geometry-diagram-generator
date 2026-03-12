export function gateBadge(status) {
  const cls = status ? `badge-${status}` : 'badge-null'
  return `<span class="badge ${cls}">${status || 'unknown'}</span>`
}

export function checkBadge(passed, skipped) {
  if (skipped) return '<span class="badge" style="background:#1a1a1a;color:#888">skip</span>'
  if (passed) return '<span class="badge badge-pass">pass</span>'
  return '<span class="badge badge-fail">fail</span>'
}
