import { useState } from 'react'
import { api } from '../api'

export default function Sidebar({ registry, activeWorkspace, onWorkspaceChange, showToast, onSupervisorRun, showActivity, onToggleActivity }) {
  const [running, setRunning] = useState(false)
  const { workspaces = [], projects = [] } = registry

  const stats = {
    total:   projects.length,
    active:  projects.filter(p => p.status === 'active').length,
    pending: projects.reduce((s, p) => s + p.tasks.filter(t => t.status === 'pending').length, 0),
    blocked: projects.reduce((s, p) => s + p.tasks.filter(t => t.status === 'blocked').length, 0),
  }

  const handleRun = async () => {
    setRunning(true)
    try {
      const res = await api.runSupervisor()
      showToast(`Supervisor started (PID ${res.pid})`)
      setTimeout(onSupervisorRun, 3000)
      setTimeout(onSupervisorRun, 8000)
    } catch (e) {
      showToast('Failed: ' + e.message, 'error')
    } finally {
      setRunning(false)
    }
  }

  const wsOptions = ['all', ...workspaces]

  return (
    <aside className="sidebar">
      <div className="sidebar-logo"><span>⚡</span> Workspace OS</div>

      <div className="sidebar-section">
        <div className="sidebar-label">Workspaces</div>
        <div>
          {wsOptions.map(ws => {
            const count = ws === 'all' ? projects.length : projects.filter(p => p.workspace === ws).length
            return (
              <button
                key={ws}
                className={['chip', ws === 'all' ? 'all' : '', activeWorkspace === ws ? 'active' : ''].filter(Boolean).join(' ')}
                onClick={() => onWorkspaceChange(ws)}
              >
                {ws} <small>({count})</small>
              </button>
            )
          })}
        </div>
      </div>

      <button className={`run-btn${running ? ' running' : ''}`} onClick={handleRun} disabled={running}>
        <div className="spinner" />
        <span className="btn-label">{running ? 'Running…' : 'Run Supervisor'}</span>
      </button>

      <button
        className={`run-btn activity-btn${showActivity ? ' active' : ''}`}
        onClick={onToggleActivity}
      >
        <span className="btn-label">{showActivity ? 'Hide Activity' : 'Activity'}</span>
      </button>

      <div className="sidebar-stats">
        {[['Total projects', stats.total], ['Active', stats.active], ['Pending tasks', stats.pending], ['Blocked', stats.blocked]].map(([label, val]) => (
          <div key={label} className="stat">
            <span>{label}</span>
            <span className="stat-val">{val}</span>
          </div>
        ))}
      </div>
    </aside>
  )
}
