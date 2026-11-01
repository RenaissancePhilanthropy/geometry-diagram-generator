import DOMPurify from 'dompurify'

export function escapeHtml(value) {
  return String(value ?? '')
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;')
}

// Sanitize server-provided SVG before innerHTML. data-* attributes are kept
// (DOMPurify's default) because the viewer relies on data-label-text and
// data-bbox; <style> is allowed for the font-family rules the renderer emits.
export function sanitizeSvg(svg) {
  return DOMPurify.sanitize(svg, {
    USE_PROFILES: { svg: true, svgFilters: true },
    ADD_TAGS: ['style'],
    ALLOW_DATA_ATTR: true,
  })
}
