import { useState, useEffect, useRef } from 'react'
import { api } from '../../api'
import { fmtDate, STATUS_ICONS } from '../../utils'

const TASK_TYPES = ['coding','research','review','design','devops','content','other']
const PRIORITIES = ['high','medium','low']

function TaskLogViewer({ task, projectId }) {
  const [log, setLog] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [running, setRunning] = useState(false)
  const intervalRef = useRef(null)

  const fetchLog = async () => {
    try {
      let data
      if (task.run_id) {
        data = await api.supervisorRun(task.run_id)
      } else {
        data = await api.taskLog(projectId, task.id)
      }
      if (data.error) {
        setError(data.error)
        setLog(null)
      } else {
        setLog(data.log || '')
        setRunning(!!data.running)
        setError(null)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchLog()
    // Auto-refresh while task is in_progress
    if (task.status === 'in_progress') {
      intervalRef.current = setInterval(fetchLog, 5000)
    }
    return () => {
      if (intervalRef.current) clearInterval(intervalRef.current)
    }
  }, [task.run_id, task.id, task.status])

  // Stop polling once no longer running
  useEffect(() => {
    if (task.status !== 'in_progress' && intervalRef.current) {
      clearInterval(intervalRef.current)
      intervalRef.current = null
    }
  }, [task.status])

  return (
    <div className="task-log-viewer">
      <div className="task-log-header">
        <span className="overview-section-title" style={{ marginBottom: 0 }}>Session Output</span>
        {running && <span className="mini-badge blue">running</span>}
        {task.run_id && <span className="text2" style={{ fontSize: 11 }}>run: {task.run_id}</span>}
      </div>
      {loading && <div className="text2" style={{ padding: 8, fontSize: 12 }}>Loading...</div>}
      {error && <div className="text2" style={{ padding: 8, fontSize: 12 }}>No session output available</div>}
      {log !== null && (
        <pre className="task-log-pre">{log || '(empty log)'}</pre>
      )}
    </div>
  )
}

export default function TasksTab({ project, onUpdate, showToast }) {
  const [title, setTitle] = useState('')
  const [type, setType] = useState('other')
  const [priority, setPriority] = useState('medium')
  const [loading, setLoading] = useState(false)
  const [expanded, setExpanded] = useState(null)

  const tasks = project.tasks || []

  const handleAdd = async () => {
    if (!title.trim()) { showToast('Title required', 'error'); return }
    setLoading(true)
    try {
      await api.createTask(project.id, { title, type, priority })
      setTitle('')
      showToast('Task added')
      onUpdate()
    } catch (e) { showToast('Failed: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  const toggleExpand = (taskId) => {
    setExpanded(prev => prev === taskId ? null : taskId)
  }

  return (
    <div>
      <div className="tasks-list-detail">
        {tasks.length === 0
          ? <div className="no-tasks" style={{ padding: 24 }}>No tasks yet</div>
          : tasks.map(t => (
              <div key={t.id} className={`detail-task-item task-status-${t.status}`}>
                <div className="detail-task-main detail-task-clickable" onClick={() => toggleExpand(t.id)}>
                  <span className="detail-task-icon">{STATUS_ICONS[t.status] || '○'}</span>
                  <div className="detail-task-info">
                    <div className="detail-task-title">
                      {t.title}
                      <span className="task-expand-arrow">{expanded === t.id ? '▾' : '▸'}</span>
                    </div>
                    <div className="detail-task-meta">
                      <span className="mini-badge">{t.type || 'other'}</span>
                      <span className={`mini-badge priority-${t.priority}`}>{t.priority}</span>
                      {t.agent_spawned && <span className="mini-badge blue">agent: {t.agent_spawned}</span>}
                      <span className="text2" style={{ fontSize: 11 }}>{fmtDate(t.created_at)}</span>
                    </div>
                    {t.result && <div className="task-result">Result: {t.result}</div>}
                    {t.blocked_reason && <div className="task-blocked-reason">Blocked: {t.blocked_reason}</div>}
                  </div>
                </div>
                {expanded === t.id && (
                  <div className="task-expanded-panel">
                    <div className="task-expanded-meta">
                      <div className="task-meta-row">
                        <span className="text2">Status:</span>
                        <span className={`mini-badge ${t.status === 'done' ? 'green' : t.status === 'blocked' ? 'red' : t.status === 'in_progress' ? 'blue' : ''}`}>{t.status}</span>
                      </div>
                      {t.agent_spawned && (
                        <div className="task-meta-row">
                          <span className="text2">Agent:</span>
                          <span>{t.agent_spawned}</span>
                        </div>
                      )}
                      {t.result && (
                        <div className="task-meta-row">
                          <span className="text2">Result:</span>
                          <span style={{ color: 'var(--green)' }}>{t.result}</span>
                        </div>
                      )}
                      {t.blocked_reason && (
                        <div className="task-meta-row">
                          <span className="text2">Blocked:</span>
                          <span style={{ color: 'var(--red)' }}>{t.blocked_reason}</span>
                        </div>
                      )}
                      <div className="task-meta-row">
                        <span className="text2">Created:</span>
                        <span>{fmtDate(t.created_at)}</span>
                      </div>
                    </div>
                    <TaskLogViewer task={t} projectId={project.id} />
                  </div>
                )}
              </div>
            ))
        }
      </div>

      <div className="detail-add-task-section">
        <div className="overview-section-title">Add Task</div>
        <div className="detail-add-task-form">
          <input
            className="form-input"
            placeholder="Task title…"
            value={title}
            onChange={e => setTitle(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAdd()}
            style={{ flex: 1 }}
          />
          <select className="form-select" value={type} onChange={e => setType(e.target.value)}>
            {TASK_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
          <select className="form-select" value={priority} onChange={e => setPriority(e.target.value)}>
            {PRIORITIES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
          <button className="form-btn form-btn-submit" onClick={handleAdd} disabled={loading}>
            {loading ? '…' : 'Add Task'}
          </button>
        </div>
      </div>
    </div>
  )
}
