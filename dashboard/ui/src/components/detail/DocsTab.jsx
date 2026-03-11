import { useState, useEffect } from 'react'
import { api } from '../../api'
import { renderMarkdown, fmtSize } from '../../utils'

export default function DocsTab({ project }) {
  const [docs, setDocs] = useState(null)
  const [selected, setSelected] = useState(null)
  const [content, setContent] = useState(null)
  const [loading, setLoading] = useState(false)

  useEffect(() => {
    api.docs(project.id).then(d => {
      setDocs(d)
      if (d.length > 0) loadDoc(d[0])
    }).catch(() => setDocs([]))
  }, [project.id])

  const loadDoc = async (doc) => {
    setSelected(doc.rel_path)
    setContent(null)
    setLoading(true)
    try {
      const d = await api.doc(project.id, doc.rel_path)
      setContent(d)
    } catch (e) { setContent({ error: e.message }) }
    finally { setLoading(false) }
  }

  if (!docs) return <div className="loading">Loading documentation…</div>
  if (docs.length === 0) return <div className="empty-state" style={{ padding: 40 }}><h3>No docs found</h3><p>No .md or .txt files in project directory</p></div>

  return (
    <div className="docs-layout">
      <div className="docs-filelist">
        {docs.map(d => (
          <div
            key={d.rel_path}
            className={`docs-file-item${selected === d.rel_path ? ' active' : ''}`}
            onClick={() => loadDoc(d)}
          >
            <div className="docs-fname">{d.name}</div>
            <div className="docs-fmeta">{d.rel_path} · {fmtSize(d.size)}</div>
          </div>
        ))}
      </div>
      <div className="docs-viewer">
        {loading && <div className="loading">Loading…</div>}
        {!loading && content && (
          content.error
            ? <div className="error-msg">{content.error}</div>
            : <>
                <div className="docs-viewer-header">
                  <strong>{content.name}</strong>
                  <span className="text2" style={{ fontSize: 11 }}>{fmtSize(content.size || 0)}</span>
                </div>
                {content.rel_path?.endsWith('.jsonl')
                  ? <pre className="md-pre" style={{ marginTop: 12 }}>{content.content}</pre>
                  : <div dangerouslySetInnerHTML={{ __html: renderMarkdown(content.content) }} />
                }
              </>
        )}
        {!loading && !content && <div className="text2" style={{ padding: 24, textAlign: 'center' }}>Select a file</div>}
      </div>
    </div>
  )
}
