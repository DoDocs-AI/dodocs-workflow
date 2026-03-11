import { useState, useEffect, useCallback } from 'react'
import { api } from '../../api'
import { fmtSize, fmtTs } from '../../utils'

const FILE_ICONS = { 'session-txt': '\uD83D\uDCDD', 'task-md': '\u2705', 'jsonl': '\uD83D\uDDC2\uFE0F' }

function formatTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return '' }
}

function StatusDot({ status }) {
  return <span className={`status-dot status-${status || 'inactive'}`} />
}

export default function SessionTab({ project }) {
  const [data, setData] = useState(null)
  const [selectedFile, setSelectedFile] = useState(null)
  const [fileContent, setFileContent] = useState(null)
  const [codeSessions, setCodeSessions] = useState([])

  const loadData = useCallback(() => {
    api.session(project.id)
      .then(setData)
      .catch(() => setData({ log: [], sessions: [] }))
  }, [project.id])

  const loadCodeSessions = useCallback(() => {
    api.projectSessions(project.id)
      .then(setCodeSessions)
      .catch(() => setCodeSessions([]))
  }, [project.id])

  useEffect(() => {
    loadData()
    loadCodeSessions()
    const t = setInterval(() => { loadData(); loadCodeSessions() }, 5000)
    return () => clearInterval(t)
  }, [loadData, loadCodeSessions])

  const loadFile = async (session) => {
    setSelectedFile(session.rel_path)
    setFileContent(null)
    try {
      const d = await api.doc(project.id, session.rel_path)
      setFileContent(d)
    } catch (e) { setFileContent({ error: e.message }) }
  }

  if (!data) return <div className="loading">Loading session data…</div>

  return (
    <div className="session-layout">
      <div className="session-left">
        {/* Claude Code Sessions */}
        {codeSessions.length > 0 && (
          <>
            <div className="session-section-title">
              Claude Code Sessions <span className="refresh-dot" />
            </div>
            <div className="code-sessions-list">
              {codeSessions.map(s => (
                <div key={s.session_id} className="code-session-item">
                  <StatusDot status={s.status} />
                  <span className="code-session-id">{s.session_id.slice(0, 8)}</span>
                  <span className="code-session-count">{s.event_count} events</span>
                  <span className="code-session-time">{formatTime(s.last_activity)}</span>
                  {s.is_worktree && <span className="worktree-badge">WT: {s.worktree_name}</span>}
                </div>
              ))}
            </div>
          </>
        )}

        <div className="session-section-title" style={codeSessions.length > 0 ? { marginTop: 20 } : {}}>
          Agent Activity Log <span className="refresh-dot" />
        </div>
        <div className="session-log">
          {data.log.length === 0
            ? <div className="no-tasks">No agent activity logged yet</div>
            : [...data.log].reverse().map((e, i) => (
                <div key={i} className="session-entry">
                  <span className="session-ts">{fmtTs(e.ts)}</span>
                  <span className="session-task">{e.task_id || ''}</span>
                  <span className="session-agent">{e.agent || ''}</span>
                  <span className={`session-status session-status-${e.status}`}>{e.status || ''}</span>
                  <span className="session-summary">{e.summary || ''}</span>
                </div>
              ))
          }
        </div>

        <div className="session-section-title" style={{ marginTop: 20 }}>Session Files in Project</div>
        <div className="session-files">
          {data.sessions.length === 0
            ? <div className="no-tasks">No session files found</div>
            : data.sessions.map((f, i) => (
                <div
                  key={i}
                  className="session-file-item"
                  onClick={() => loadFile(f)}
                  style={{ background: selectedFile === f.rel_path ? 'var(--surface2)' : '' }}
                >
                  <span>{FILE_ICONS[f.type] || '\uD83D\uDCC4'} {f.name}</span>
                  <span className="text2" style={{ fontSize: 11 }}>{fmtSize(f.size)} · {fmtTs(f.modified)}</span>
                </div>
              ))
          }
        </div>
      </div>

      <div className="session-right">
        {!selectedFile && <div className="text2" style={{ padding: 24, textAlign: 'center' }}>Select a file to view</div>}
        {selectedFile && !fileContent && <div className="loading">Loading…</div>}
        {fileContent && (
          fileContent.error
            ? <div className="error-msg">{fileContent.error}</div>
            : <div style={{ padding: 16 }}>
                <div className="docs-viewer-header">
                  <strong>{fileContent.name}</strong>
                  <span className="text2" style={{ fontSize: 11 }}>{fmtSize(fileContent.size || 0)}</span>
                </div>
                <pre className="md-pre" style={{ marginTop: 12, maxHeight: 600, overflowY: 'auto' }}>
                  {fileContent.content}
                </pre>
              </div>
        )}
      </div>
    </div>
  )
}
