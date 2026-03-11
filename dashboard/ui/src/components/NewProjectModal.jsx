import { useState } from 'react'
import { api } from '../api'

const TYPES  = ['software','research','content','brainstorm','devops','design']
const PHASES = ['ideation','planning','ready','in_progress','development','review','done','paused']

export default function NewProjectModal({ workspaces, onClose, onCreated, showToast }) {
  const [form, setForm] = useState({ name:'', workspace: workspaces[0] || 'personal', type:'software', phase:'ideation', path:'', description:'' })
  const [loading, setLoading] = useState(false)
  const set = (k, v) => setForm(f => ({ ...f, [k]: v }))

  const handleSubmit = async () => {
    if (!form.name.trim()) { showToast('Name required', 'error'); return }
    setLoading(true)
    try { await api.createProject(form); onCreated() }
    catch (e) { showToast('Failed: ' + e.message, 'error') }
    finally { setLoading(false) }
  }

  const wsOptions = [...new Set(['personal', 'corporate', ...workspaces])]

  return (
    <div className="modal-overlay visible" onClick={e => e.target === e.currentTarget && onClose()}>
      <div className="modal">
        <h2>New Project</h2>
        <div className="field"><label>Name *</label><input placeholder="my-project" value={form.name} onChange={e => set('name', e.target.value)} /></div>
        <div className="field"><label>Workspace</label>
          <select value={form.workspace} onChange={e => set('workspace', e.target.value)}>
            {wsOptions.map(w => <option key={w} value={w}>{w}</option>)}
          </select>
        </div>
        <div className="field"><label>Type</label>
          <select value={form.type} onChange={e => set('type', e.target.value)}>
            {TYPES.map(t => <option key={t} value={t}>{t}</option>)}
          </select>
        </div>
        <div className="field"><label>Phase</label>
          <select value={form.phase} onChange={e => set('phase', e.target.value)}>
            {PHASES.map(p => <option key={p} value={p}>{p}</option>)}
          </select>
        </div>
        <div className="field"><label>Path</label><input placeholder="/absolute/path" value={form.path} onChange={e => set('path', e.target.value)} /></div>
        <div className="field"><label>Description</label><textarea placeholder="Brief description…" value={form.description} onChange={e => set('description', e.target.value)} /></div>
        <div className="modal-actions">
          <button className="btn" onClick={onClose}>Cancel</button>
          <button className="btn btn-primary" onClick={handleSubmit} disabled={loading}>{loading ? 'Creating…' : 'Create Project'}</button>
        </div>
      </div>
    </div>
  )
}
