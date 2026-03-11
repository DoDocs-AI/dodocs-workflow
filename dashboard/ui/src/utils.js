export const TYPE_ICONS   = { software:'⚙️', research:'🔬', content:'✍️', brainstorm:'💡', devops:'🚀', design:'🎨' }
export const PHASE_LABELS = { ideation:'ideation', planning:'planning', ready:'ready', in_progress:'in progress', development:'development', review:'review', done:'done', paused:'paused' }
export const STATUS_ICONS = { pending:'○', in_progress:'⏳', done:'✓', blocked:'🚫', cancelled:'✗' }

export function esc(s) {
  if (!s) return ''
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
}
export function fmtSize(b) {
  if (b < 1024) return b + 'B'
  if (b < 1048576) return (b/1024).toFixed(1) + 'KB'
  return (b/1048576).toFixed(1) + 'MB'
}
export function fmtDate(iso) {
  if (!iso) return ''
  return new Date(iso).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' })
}
export function fmtTs(ts) {
  if (!ts) return ''
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts)
  return d.toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' })
}

export function renderMarkdown(raw) {
  if (!raw) return '<em>Empty</em>'
  const segments = raw.split(/(```(?:[a-z]*\n)?[\s\S]*?```)/g)
  let html = ''
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i]
    if (i % 2 === 1) {
      const inner = seg.replace(/^```[a-z]*\n?/, '').replace(/```$/, '')
      html += `<pre class="md-pre">${esc(inner)}</pre>`
    } else {
      let t = esc(seg)
      t = t.replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>')
      t = t.replace(/^#{3} (.+)$/gm, '<h3 class="md-h3">$1</h3>')
      t = t.replace(/^#{2} (.+)$/gm, '<h2 class="md-h2">$1</h2>')
      t = t.replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>')
      t = t.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
      t = t.replace(/\*([^*\n]+)\*/g, '<em>$1</em>')
      t = t.replace(/^&gt; (.+)$/gm, '<blockquote class="md-quote">$1</blockquote>')
      t = t.replace(/^[-*] (.+)$/gm, '<li class="md-li">$1</li>')
      t = t.replace(/(<li[^>]*>[\s\S]*?<\/li>\n?)+/g, m => `<ul class="md-ul">${m}</ul>`)
      t = t.replace(/^---+$/gm, '<hr class="md-hr">')
      t = t.replace(/\n{2,}/g, '</p><p class="md-p">')
      t = t.replace(/\n/g, '<br/>')
      html += `<p class="md-p">${t}</p>`
    }
  }
  return html
}
