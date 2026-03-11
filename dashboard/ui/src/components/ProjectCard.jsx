import { useState } from 'react'
import { api } from '../api'
import { TYPE_ICONS, PHASE_LABELS, STATUS_ICONS } from '../utils'

export default function ProjectCard({ project, onClick, onTaskAdded, showToast }) {
  const [showForm, setShowForm] = useState(false)
  const [title, setTitle] = useState('')
  const [type, setType] = useState('other')
  const [priority, setPriority] = useState('medium')

  const tasks = project.tasks || []
  const shown = tasks.slice(0, 4)
  const overflow = tasks.length - shown.length

  const handleAddTask = async (e) => {
    e.stopPropagation()
    if (!title.trim()) { showToast('Title required', 'error'); return }
    try {
      await api.createTask(project.id, { title, type, priority })
      setTitle(''); setShowForm(false)
      showToast(`Task added`)
      onTaskAdded()
    } catch (e) { showToast('Failed: ' + e.message, 'error') }
  }

  return (
    <div className="card" onClick={onClick} title="Click for details">
      <div className="card-header">
        <div>
          <div className="card-title">{TYPE_ICONS[project.type] || ''} {project.name}</div>
          <div className="card-workspace">{project.workspace}</div>
        </div>
        <div className="card-badges">
          <span className={`badge badge-${project.type}`}>{project.type}</span>
          <span className="badge badge-phase">{PHASE_LABELS[project.phase] || project.phase}</span>
        </div>
      </div>

      {project.description && <div className="card-desc">{project.description}</div>}

      <div className="tasks-header">
        <span className="tasks-label">Tasks ({tasks.length})</span>
        <button className="add-task-btn" onClick={e => { e.stopPropagation(); setShowForm(v => !v) }}>
          + Add task
        </button>
      </div>

      <div className="task-list">
        {tasks.length === 0
          ? <div className="no-tasks">No tasks — click to add</div>
          : <>
              {shown.map(t => (
                <div key={t.id} className={`task-item status-${t.status}`}>
                  <span className="task-icon">{STATUS_ICONS[t.status] || '○'}</span>
                  <div style={{ flex: 1 }}>
                    <div className="task-title">{t.title}</div>
                    {t.blocked_reason && <div className="task-blocked-reason">{t.blocked_reason}</div>}
                  </div>
                  <span className={`task-priority priority-${t.priority}`}>{t.priority}</span>
                </div>
              ))}
              {overflow > 0 && <div className="tasks-overflow">+{overflow} more</div>}
            </>
        }
      </div>

      {showForm && (
        <div className="add-task-form visible" onClick={e => e.stopPropagation()}>
          <input
            className="form-input"
            placeholder="Task title…"
            value={title}
            onChange={e => setTitle(e.target.value)}
            onKeyDown={e => e.key === 'Enter' && handleAddTask(e)}
            autoFocus
          />
          <div className="form-row">
            <select className="form-select" value={type} onChange={e => setType(e.target.value)}>
              {['coding','research','review','design','devops','content','other'].map(t => <option key={t} value={t}>{t}</option>)}
            </select>
            <select className="form-select" value={priority} onChange={e => setPriority(e.target.value)}>
              {['high','medium','low'].map(p => <option key={p} value={p}>{p}</option>)}
            </select>
            <button className="form-btn form-btn-submit" onClick={handleAddTask}>Add</button>
            <button className="form-btn form-btn-cancel" onClick={e => { e.stopPropagation(); setShowForm(false) }}>✕</button>
          </div>
        </div>
      )}
    </div>
  )
}
