const post = (url, body) =>
  fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) })
    .then(async r => { if (!r.ok) throw new Error(await r.text()); return r.json() })

export const api = {
  registry:      ()         => fetch('/api/registry').then(r => r.json()),
  context:       (id)       => fetch(`/api/projects/${id}/context`).then(r => r.json()),
  docs:          (id)       => fetch(`/api/projects/${id}/docs`).then(r => r.json()),
  doc:           (id, file) => fetch(`/api/projects/${id}/doc?file=${encodeURIComponent(file)}`).then(r => r.json()),
  tree:          (id)       => fetch(`/api/projects/${id}/tree`).then(r => r.json()),
  session:       (id)       => fetch(`/api/projects/${id}/session`).then(r => r.json()),
  createProject: (data)     => post('/api/projects', data),
  updateProject: (id, data) => post(`/api/projects/${id}`, data),
  createTask:    (id, data) => post(`/api/projects/${id}/tasks`, data),
  runSupervisor: ()         => post('/api/supervisor/run', {}),
  supervisorRuns: ()         => fetch('/api/supervisor/runs').then(r => r.json()),
  supervisorRun:  (runId)    => fetch(`/api/supervisor/runs/${encodeURIComponent(runId)}`).then(r => r.json()),
  taskLog:        (projId, taskId) => fetch(`/api/tasks/${projId}/${taskId}/log`).then(r => r.json()),
  eventSessions:  ()              => fetch('/api/events/sessions').then(r => r.json()),
  events:         ({ limit, since, date } = {}) => {
    const params = new URLSearchParams()
    if (limit) params.set('limit', limit)
    if (since) params.set('since', since)
    if (date) params.set('date', date)
    return fetch(`/api/events?${params}`).then(r => r.json())
  },
  sessionEvents:  (sid, limit)    => fetch(`/api/events/session/${encodeURIComponent(sid)}${limit ? `?limit=${limit}` : ''}`).then(r => r.json()),
  sessionHistory: (sid, limit)    => fetch(`/api/events/session/${encodeURIComponent(sid)}/history?limit=${limit || 500}`).then(r => r.json()),
  projectSessions:(projId)        => fetch(`/api/projects/${encodeURIComponent(projId)}/activity-sessions`).then(r => r.json()),
  eventDates:     ()              => fetch('/api/events/dates').then(r => r.json()),
  eventStream:    ()              => new EventSource('/api/events/stream'),
}
