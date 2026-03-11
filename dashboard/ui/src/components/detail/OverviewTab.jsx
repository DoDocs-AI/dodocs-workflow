import { useState, useEffect } from 'react'
import { api } from '../../api'
import { fmtDate, renderMarkdown } from '../../utils'

export default function OverviewTab({ project }) {
  const [context, setContext] = useState(null)

  useEffect(() => {
    api.context(project.id).then(d => setContext(d.content)).catch(() => setContext(''))
  }, [project.id])

  const tasks   = project.tasks || []
  const done    = tasks.filter(t => t.status === 'done')
  const inprog  = tasks.filter(t => t.status === 'in_progress')
  const pending = tasks.filter(t => t.status === 'pending')
  const blocked = tasks.filter(t => t.status === 'blocked')

  return (
    <div className="overview-layout">
      <div className="overview-main">
        <div className="detail-info-grid">
          <div className="info-row"><span className="info-label">Path</span><code className="info-path">{project.path || '—'}</code></div>
          <div className="info-row"><span className="info-label">Description</span><span>{project.description || '—'}</span></div>
          <div className="info-row"><span className="info-label">Created</span><span>{fmtDate(project.created_at)}</span></div>
          <div className="info-row"><span className="info-label">Updated</span><span>{fmtDate(project.updated_at)}</span></div>
          <div className="info-row">
            <span className="info-label">Tasks</span>
            <span>
              <span className="mini-badge green">{done.length} done</span>
              <span className="mini-badge blue">{inprog.length} in progress</span>
              <span className="mini-badge yellow">{pending.length} pending</span>
              {blocked.length > 0 && <span className="mini-badge red">{blocked.length} blocked</span>}
            </span>
          </div>
        </div>

        {done.length > 0 && (
          <div className="overview-section">
            <div className="overview-section-title">Features Implemented ({done.length})</div>
            {done.map(t => <div key={t.id} className="feature-item">✓ {t.title}</div>)}
          </div>
        )}
        {inprog.length > 0 && (
          <div className="overview-section">
            <div className="overview-section-title">In Progress ({inprog.length})</div>
            {inprog.map(t => <div key={t.id} className="feature-item inprog">⏳ {t.title}</div>)}
          </div>
        )}
        {blocked.length > 0 && (
          <div className="overview-section blocked-section">
            <div className="overview-section-title">Blocked ({blocked.length})</div>
            {blocked.map(t => (
              <div key={t.id} className="feature-item blocked">
                🚫 {t.title}{t.blocked_reason && <span className="text2"> — {t.blocked_reason}</span>}
              </div>
            ))}
          </div>
        )}
      </div>

      <div className="overview-context">
        <div className="overview-section-title">Context Notes</div>
        {context === null
          ? <div className="text2" style={{ fontSize: 12 }}>Loading…</div>
          : <div dangerouslySetInnerHTML={{ __html: renderMarkdown(context) }} />
        }
      </div>
    </div>
  )
}
