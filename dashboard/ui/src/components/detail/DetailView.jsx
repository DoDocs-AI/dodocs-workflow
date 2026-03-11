import { useState } from 'react'
import { api } from '../../api'
import { PHASE_LABELS, TYPE_ICONS } from '../../utils'
import OverviewTab from './OverviewTab'
import TasksTab from './TasksTab'
import DocsTab from './DocsTab'
import SourcesTab from './SourcesTab'
import SessionTab from './SessionTab'

const TABS = [
  { id: 'overview', label: 'Overview' },
  { id: 'tasks',    label: 'Tasks' },
  { id: 'docs',     label: 'Documentation' },
  { id: 'sources',  label: 'Sources' },
  { id: 'session',  label: 'Session' },
]

const PHASES = ['ideation','planning','ready','in_progress','development','review','done','paused']

export default function DetailView({ project, onBack, onUpdate, showToast }) {
  const [activeTab, setActiveTab] = useState('overview')

  const handlePhaseChange = async (phase) => {
    try {
      await api.updateProject(project.id, { phase })
      onUpdate()
      showToast()
    } catch (e) { showToast('Failed: ' + e.message, 'error') }
  }

  const tabProps = { project, onUpdate, showToast }

  return (
    <>
      <div className="detail-topbar">
        <button className="btn" onClick={onBack}>← Back</button>
        <div className="detail-title-wrap">
          <span className="detail-name">{project.name}</span>
          <div className="detail-meta">
            <span className={`badge badge-type badge-type-${project.type}`}>{TYPE_ICONS[project.type] || ''} {project.type}</span>
            <span className="badge badge-phase">{PHASE_LABELS[project.phase] || project.phase}</span>
            <span className="badge" style={{ background: 'var(--surface2)', color: 'var(--text2)' }}>{project.workspace}</span>
          </div>
        </div>
        <div className="detail-phase-wrap">
          <label className="info-label" style={{ marginRight: 6 }}>Phase</label>
          <select className="form-select" value={project.phase} onChange={e => handlePhaseChange(e.target.value)}>
            {PHASES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
      </div>

      <div className="tabs">
        {TABS.map(tab => (
          <button
            key={tab.id}
            className={`tab-btn${activeTab === tab.id ? ' active' : ''}`}
            onClick={() => setActiveTab(tab.id)}
          >
            {tab.label}
            {tab.id === 'tasks' && (project.tasks || []).length > 0 && (
              <span className="tab-count">{(project.tasks || []).length}</span>
            )}
          </button>
        ))}
      </div>

      <div className="tab-content" style={{ display: 'block' }}>
        {activeTab === 'overview' && <OverviewTab {...tabProps} />}
        {activeTab === 'tasks'    && <TasksTab    {...tabProps} />}
        {activeTab === 'docs'     && <DocsTab     {...tabProps} />}
        {activeTab === 'sources'  && <SourcesTab  {...tabProps} />}
        {activeTab === 'session'  && <SessionTab  {...tabProps} />}
      </div>
    </>
  )
}
