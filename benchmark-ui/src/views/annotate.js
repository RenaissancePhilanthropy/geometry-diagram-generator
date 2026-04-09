export async function renderAnnotateView(container, { runId, promptId, navigate }) {
  container.innerHTML = '<p style="color:#888;padding:20px">Loading…</p>'

  const annotatorId = localStorage.getItem('annotator_id') || 'human:anonymous'

  let result, queue
  try {
    const [rRes, qRes] = await Promise.all([
      fetch(`/api/runs/${runId}/results/${promptId}`),
      fetch(`/api/runs/${runId}/queue`),
    ])
    result = await rRes.json()
    queue = await qRes.json()
  } catch (e) {
    container.innerHTML = `<p style="color:#f87171;padding:20px">Failed to load: ${e.message}</p>`
    return
  }

  const queueIndex = queue.findIndex(q => q.prompt_id === promptId)
  const prevPrompt = queueIndex > 0 ? queue[queueIndex - 1].prompt_id : null
  const nextPrompt = queueIndex < queue.length - 1 ? queue[queueIndex + 1].prompt_id : null

  const rubricItems = result.rubric || []
  const customItems = rubricItems.filter(item => item.category !== 'visual_quality')
  const visualItems = rubricItems.filter(item => item.category === 'visual_quality')

  // Build answer state from existing annotations
  const answers = {}
  if (result.annotations) {
    for (const ann of result.annotations) {
      if (ann.annotator_id === annotatorId) {
        answers[ann.rubric_item_id] = ann.value
      }
    }
  }

  let focusedIndex = 0

  function countAnswered() {
    return rubricItems.filter(item => answers[item.id] !== undefined).length
  }

  function renderRubricItem(item, displayIndex) {
    const val = answers[item.id]
    const yActive = val === 1 ? 'active-y' : ''
    const nActive = val === 0 ? 'active-n' : ''
    const focused = focusedIndex === displayIndex ? 'focused' : ''
    return `
      <div class="rubric-item ${focused}" data-index="${displayIndex}" data-item-id="${item.id}">
        <span class="item-number">${displayIndex + 1}</span>
        <span class="item-text">${item.text}</span>
        <div class="yn-buttons">
          <button class="yn-btn ${yActive}" data-vote="1" data-item-id="${item.id}">Y</button>
          <button class="yn-btn ${nActive}" data-vote="0" data-item-id="${item.id}">N</button>
        </div>
      </div>
    `
  }

  function buildRubricHtml() {
    let html = ''
    customItems.forEach((item, i) => {
      html += renderRubricItem(item, i)
    })
    if (visualItems.length > 0) {
      html += `<div class="rubric-divider">Visual Quality</div>`
      visualItems.forEach((item, i) => {
        html += renderRubricItem(item, customItems.length + i)
      })
    }
    return html
  }

  function allItemsInOrder() {
    return [...customItems, ...visualItems]
  }

  function buildLayout() {
    const answered = countAnswered()
    const total = rubricItems.length
    const promptText = result.prompt_text || promptId
    const benchmarkId = result.benchmark_id || ''

    return `
      <div class="annotate-layout">
        <div style="padding: 12px 0 8px;">
          <div class="prompt-text">${promptText}</div>
          <div class="svgs-row">
            <div class="svg-panel">
              <h3>Generated Diagram</h3>
              <div class="svg-container">
                <img src="/api/runs/${runId}/results/${promptId}/svg" alt="Generated diagram" style="max-width:100%;max-height:100%;" onerror="this.parentElement.innerHTML='<span class=\\'no-ref\\'>No diagram generated</span>'" />
              </div>
            </div>
            <div class="svg-panel">
              <h3>Reference Diagram</h3>
              <div class="svg-container" id="ref-container">
                <img src="/api/references/${benchmarkId}/${promptId}" alt="Reference diagram" style="max-width:100%;max-height:100%;" onerror="this.parentElement.innerHTML='<span class=\\'no-ref\\'>No reference</span>'" />
              </div>
            </div>
          </div>
        </div>
        <div class="rubric-section" id="rubric-section">
          ${buildRubricHtml()}
        </div>
        <div class="nav-row">
          <button class="btn" id="btn-prev" ${!prevPrompt ? 'disabled' : ''}>← Prev</button>
          <div style="display:flex;align-items:center;gap:16px;">
            <span class="progress-badge">Progress ${answered} / ${total}</span>
            <button class="btn" id="btn-skip">Skip</button>
          </div>
          <button class="btn btn-primary" id="btn-next" ${!nextPrompt ? 'disabled' : ''}>Next →</button>
        </div>
      </div>
    `
  }

  function render() {
    container.innerHTML = buildLayout()
    attachListeners()
  }

  function refreshRubric() {
    const section = container.querySelector('#rubric-section')
    if (section) {
      section.innerHTML = buildRubricHtml()
      attachRubricListeners()
    }
    const badge = container.querySelector('.progress-badge')
    if (badge) {
      badge.textContent = `Progress ${countAnswered()} / ${rubricItems.length}`
    }
  }

  async function vote(itemId, value) {
    answers[itemId] = value
    refreshRubric()

    try {
      await fetch('/api/annotate', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          result_id: result.result_id || promptId,
          rubric_item_id: itemId,
          annotator_id: annotatorId,
          value: value,
        }),
      })
    } catch (e) {
      console.error('Failed to save annotation:', e)
    }
  }

  function goNext() {
    if (nextPrompt) navigate(`#/runs/${runId}/annotate/${nextPrompt}`)
  }

  function goPrev() {
    if (prevPrompt) navigate(`#/runs/${runId}/annotate/${prevPrompt}`)
  }

  function attachRubricListeners() {
    container.querySelectorAll('.yn-btn').forEach(btn => {
      btn.addEventListener('click', (e) => {
        e.stopPropagation()
        const itemId = btn.dataset.itemId
        const value = parseInt(btn.dataset.vote, 10)
        vote(itemId, value)
      })
    })

    container.querySelectorAll('.rubric-item').forEach(row => {
      row.addEventListener('click', () => {
        focusedIndex = parseInt(row.dataset.index, 10)
        refreshRubric()
      })
    })
  }

  function attachListeners() {
    attachRubricListeners()

    const btnPrev = container.querySelector('#btn-prev')
    const btnNext = container.querySelector('#btn-next')
    const btnSkip = container.querySelector('#btn-skip')

    if (btnPrev) btnPrev.addEventListener('click', goPrev)
    if (btnNext) btnNext.addEventListener('click', goNext)
    if (btnSkip) btnSkip.addEventListener('click', goNext)
  }

  async function onKeydown(e) {
    const tag = document.activeElement?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA') return

    const items = allItemsInOrder()

    const num = parseInt(e.key, 10)
    if (!isNaN(num) && num >= 1 && num <= items.length) {
      const idx = num - 1
      focusedIndex = idx
      await vote(items[idx].id, 1)
    } else if (e.key === 'y' || e.key === 'Y') {
      if (focusedIndex < items.length) {
        vote(items[focusedIndex].id, 1)
      }
    } else if (e.key === 'n' || e.key === 'N') {
      if (focusedIndex < items.length) {
        vote(items[focusedIndex].id, 0)
      }
    } else if (e.key === 'Tab') {
      e.preventDefault()
      if (e.shiftKey) {
        focusedIndex = Math.max(0, focusedIndex - 1)
      } else {
        focusedIndex = Math.min(items.length - 1, focusedIndex + 1)
      }
      refreshRubric()
    } else if (e.key === 'Enter' || e.key === 'ArrowRight') {
      goNext()
    } else if (e.key === 'ArrowLeft') {
      goPrev()
    } else if (e.key === 's' || e.key === 'S') {
      goNext()
    }
  }

  document.addEventListener('keydown', onKeydown)
  window.addEventListener('hashchange', () => {
    document.removeEventListener('keydown', onKeydown)
  }, { once: true })

  render()
}
