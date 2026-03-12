/**
 * Line-based diff using LCS (Myers-style, O(nm) table).
 * Returns array of {type: 'equal'|'add'|'remove', line: string}.
 */
export function computeDiff(oldText, newText) {
  const a = oldText.split('\n')
  const b = newText.split('\n')
  const m = a.length, n = b.length

  // Build LCS table
  const dp = Array.from({ length: m + 1 }, () => new Int32Array(n + 1))
  for (let i = m - 1; i >= 0; i--) {
    for (let j = n - 1; j >= 0; j--) {
      if (a[i] === b[j]) {
        dp[i][j] = dp[i + 1][j + 1] + 1
      } else {
        dp[i][j] = Math.max(dp[i + 1][j], dp[i][j + 1])
      }
    }
  }

  // Trace back
  const result = []
  let i = 0, j = 0
  while (i < m || j < n) {
    if (i < m && j < n && a[i] === b[j]) {
      result.push({ type: 'equal', line: a[i] })
      i++; j++
    } else if (j < n && (i >= m || dp[i][j + 1] >= dp[i + 1][j])) {
      result.push({ type: 'add', line: b[j] })
      j++
    } else {
      result.push({ type: 'remove', line: a[i] })
      i++
    }
  }
  return result
}

/**
 * Renders a diff as an HTML string with colored lines and line numbers.
 * Shows only changed sections with a few lines of context around them.
 */
export function renderDiff(oldText, newText, contextLines = 3) {
  const entries = computeDiff(oldText, newText)

  if (entries.every(e => e.type === 'equal')) {
    return '<div style="color:#888;font-size:12px;padding:8px">No changes.</div>'
  }

  // Collapse unchanged runs that are far from any change
  const changed = new Set()
  entries.forEach((e, i) => { if (e.type !== 'equal') changed.add(i) })

  const visible = new Set()
  changed.forEach(ci => {
    for (let k = Math.max(0, ci - contextLines); k <= Math.min(entries.length - 1, ci + contextLines); k++) {
      visible.add(k)
    }
  })

  let oldLine = 1, newLine = 1
  const lines = []
  let prevVisible = true

  entries.forEach((e, i) => {
    const isVisible = visible.has(i)

    if (!isVisible && prevVisible) {
      lines.push('<div class="diff-line-hunk">···</div>')
    }
    prevVisible = isVisible

    if (!isVisible) {
      if (e.type !== 'add') oldLine++
      if (e.type !== 'remove') newLine++
      return
    }

    const esc = escapeHtml(e.line)
    if (e.type === 'equal') {
      lines.push(`<div class="diff-line diff-line-equal"><span class="diff-gutter">${oldLine}</span><span class="diff-gutter">${newLine}</span><span class="diff-prefix"> </span><span class="diff-content">${esc}</span></div>`)
      oldLine++; newLine++
    } else if (e.type === 'add') {
      lines.push(`<div class="diff-line diff-line-add"><span class="diff-gutter"> </span><span class="diff-gutter">${newLine}</span><span class="diff-prefix">+</span><span class="diff-content">${esc}</span></div>`)
      newLine++
    } else {
      lines.push(`<div class="diff-line diff-line-remove"><span class="diff-gutter">${oldLine}</span><span class="diff-gutter"> </span><span class="diff-prefix">-</span><span class="diff-content">${esc}</span></div>`)
      oldLine++
    }
  })

  return `<div class="diff-view">${lines.join('')}</div>`
}

function escapeHtml(str) {
  return str
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
}
