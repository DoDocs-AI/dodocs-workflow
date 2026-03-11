import { useState, useEffect } from 'react'
import { api } from './api'
import Sidebar from './components/Sidebar'
import ProjectCard from './components/ProjectCard'
import NewProjectModal from './components/NewProjectModal'
import DetailView from './components/detail/DetailView'
import ActivityPanel from './components/ActivityPanel'

export default function App() {
  const [registry, setRegistry] = useState({ workspaces: [], projects: [] })
  const [activeWorkspace, setActiveWorkspace] = useState('all')
  const [detailId, setDetailId] = useState(null)
  const [showModal, setShowModal] = useState(false)
  const [showActivity, setShowActivity] = useState(false)
  const [toast, setToast] = useState(null)

  const showToast = (msg, type = 'success') => {
    setToast({ msg, type })
    setTimeout(() => setToast(null), 3000)
  }

  const refreshRegistry = () =>
    api.registry().then(setRegistry).catch(e => console.error('Refresh failed:', e))

  useEffect(() => {
    refreshRegistry()
    const t = setInterval(refreshRegistry, 10000)
    return () => clearInterval(t)
  }, [])

  const project = detailId ? registry.projects.find(p => p.id === detailId) ?? null : null

  const filteredProjects = registry.projects.filter(p =>
    activeWorkspace === 'all' || p.workspace === activeWorkspace
  )

  const blockedTasks = registry.projects.flatMap(p =>
    p.tasks.filter(t => t.status === 'blocked').map(t => ({ ...t, projectName: p.name }))
  )

  return (
    <div className="app">
      <Sidebar
        registry={registry}
        activeWorkspace={activeWorkspace}
        onWorkspaceChange={setActiveWorkspace}
        showToast={showToast}
        onSupervisorRun={refreshRegistry}
        showActivity={showActivity}
        onToggleActivity={() => { setShowActivity(!showActivity); if (!showActivity) setDetailId(null) }}
      />

      <main className="main">
        {showActivity ? (
          <ActivityPanel />
        ) : detailId && project ? (
          <DetailView
            project={project}
            onBack={() => setDetailId(null)}
            onUpdate={refreshRegistry}
            showToast={showToast}
          />
        ) : (
          <>
            <div className="topbar">
              <h1>Projects <span className="refresh-dot" title="Auto-refreshes every 10s" /></h1>
              <div className="topbar-actions">
                <button className="btn btn-primary" onClick={() => setShowModal(true)}>+ New Project</button>
              </div>
            </div>

            {blockedTasks.length > 0 && (
              <div className="blocked-banner visible">
                <h3>&#x1F6AB; Blocked &mdash; needs your attention</h3>
                {blockedTasks.map((t, i) => (
                  <div key={i} className="blocked-item">
                    &#x1F6AB; <strong>{t.projectName}</strong> &rarr; {t.title}
                    {t.blocked_reason && `: ${t.blocked_reason}`}
                  </div>
                ))}
              </div>
            )}

            {filteredProjects.length === 0 ? (
              <div className="empty-state">
                <h3>No projects</h3>
                <p>Click "New Project" or use <code>/workspace add</code> in any Claude session.</p>
              </div>
            ) : (
              <div className="projects-grid">
                {filteredProjects.map(p => (
                  <ProjectCard
                    key={p.id}
                    project={p}
                    onClick={() => setDetailId(p.id)}
                    onTaskAdded={refreshRegistry}
                    showToast={showToast}
                  />
                ))}
              </div>
            )}
          </>
        )}
      </main>

      {showModal && (
        <NewProjectModal
          workspaces={registry.workspaces}
          onClose={() => setShowModal(false)}
          onCreated={() => { setShowModal(false); refreshRegistry(); showToast('Project created') }}
          showToast={showToast}
        />
      )}

      {toast && <div className={`toast ${toast.type} show`}>{toast.msg}</div>}
    </div>
  )
}
