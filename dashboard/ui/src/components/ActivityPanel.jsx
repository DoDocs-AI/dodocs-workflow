import { useState, useEffect, useRef, useCallback } from 'react'
import { api } from '../api'

const EVENT_COLORS = {
  SessionStart:       'var(--green)',
  SessionEnd:         'var(--red)',
  Stop:               'var(--yellow)',
  PreToolUse:         'var(--accent)',
  PostToolUse:        'var(--accent)',
  PostToolUseFailure: 'var(--red)',
  SubagentStart:      'var(--purple)',
  SubagentStop:       'var(--purple)',
  UserPromptSubmit:   'var(--orange)',
  Notification:       'var(--text2)',
  TeammateIdle:       'var(--text2)',
  TaskCompleted:      'var(--green)',
}

const EVENT_ICONS = {
  SessionStart:       '>>',
  SessionEnd:         '<<',
  Stop:               '||',
  PreToolUse:         '>',
  PostToolUse:        '<',
  PostToolUseFailure: '!',
  SubagentStart:      '+A',
  SubagentStop:       '-A',
  UserPromptSubmit:   '>>',
  Notification:       'i',
  TeammateIdle:       '~',
  TaskCompleted:      'ok',
}

function formatTime(ts) {
  if (!ts) return ''
  try {
    const d = new Date(ts)
    return d.toLocaleTimeString('en-US', { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' })
  } catch { return ts.slice(11, 19) }
}

function StatusDot({ status }) {
  return <span className={`status-dot status-${status || 'inactive'}`} />
}

function WorktreeBadge({ name }) {
  return <span className="worktree-badge">WT: {name}</span>
}

function EventRow({ event, onClick }) {
  const color = EVENT_COLORS[event.event] || 'var(--text2)'
  const icon = EVENT_ICONS[event.event] || '?'
  return (
    <div className="activity-event" onClick={() => onClick(event)}>
      <span className="activity-event-time">{formatTime(event.ts)}</span>
      <span className="activity-event-icon" style={{ color }}>[{icon}]</span>
      <span className="activity-event-type" style={{ color }}>{event.event}</span>
      {event.tool_name && <span className="activity-event-detail">{event.tool_name}</span>}
      {event.stop_reason && <span className="activity-event-detail">({event.stop_reason})</span>}
      <span className="activity-event-session">{(event.session_id || '').slice(0, 8)}</span>
    </div>
  )
}

export default function ActivityPanel() {
  const [sessions, setSessions] = useState([])
  const [events, setEvents] = useState([])
  const [selectedSession, setSelectedSession] = useState(null)
  const [expandedEvent, setExpandedEvent] = useState(null)
  const [filterType, setFilterType] = useState('all')
  const [autoScroll, setAutoScroll] = useState(true)
  const [dates, setDates] = useState([])
  const [selectedDate, setSelectedDate] = useState('today')
  const streamRef = useRef(null)
  const scrollRef = useRef(null)

  // Load available dates
  useEffect(() => {
    api.eventDates().then(setDates).catch(() => {})
  }, [])

  // Load sessions
  const loadSessions = useCallback(() => {
    api.eventSessions().then(setSessions).catch(() => {})
  }, [])

  useEffect(() => {
    loadSessions()
    const t = setInterval(loadSessions, 5000)
    return () => clearInterval(t)
  }, [loadSessions])

  // Load events based on selected date and session
  useEffect(() => {
    if (selectedDate !== 'today') {
      if (selectedSession) {
        api.sessionHistory(selectedSession, 500).then(setEvents).catch(() => {})
      } else {
        api.events({ limit: 500, date: selectedDate }).then(setEvents).catch(() => {})
      }
    } else {
      if (selectedSession) {
        api.sessionEvents(selectedSession, 200).then(setEvents).catch(() => {})
      } else {
        api.events({ limit: 200 }).then(setEvents).catch(() => {})
      }
    }
  }, [selectedSession, selectedDate])

  // SSE stream (only when viewing today)
  useEffect(() => {
    if (selectedDate !== 'today') return
    const es = api.eventStream()
    streamRef.current = es
    es.onmessage = (msg) => {
      try {
        const evt = JSON.parse(msg.data)
        setEvents(prev => {
          const next = [...prev, evt]
          return next.length > 500 ? next.slice(-500) : next
        })
      } catch {}
    }
    es.onerror = () => {}
    return () => es.close()
  }, [selectedDate])

  // Auto-scroll
  useEffect(() => {
    if (autoScroll && scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight
    }
  }, [events, autoScroll])

  const filteredEvents = events.filter(e => {
    if (selectedSession && e.session_id !== selectedSession) return false
    if (filterType !== 'all' && e.event !== filterType) return false
    return true
  })

  const eventTypes = ['all', ...new Set(events.map(e => e.event).filter(Boolean))]

  // Group sessions by project
  const grouped = {}
  sessions.forEach(s => {
    const key = s.project_path || s.project || 'Unknown'
    if (!grouped[key]) grouped[key] = { name: s.project_name || s.project || 'Unknown', sessions: [] }
    grouped[key].sessions.push(s)
  })

  return (
    <div className="activity-layout">
      {/* Left: Sessions */}
      <div className="activity-sessions">
        <div className="activity-sessions-header">
          <span className="sidebar-label">Sessions</span>
          <span className="activity-sessions-count">{sessions.length}</span>
        </div>

        <div className="activity-date-picker">
          <select
            className="form-select"
            style={{ width: '100%' }}
            value={selectedDate}
            onChange={e => { setSelectedDate(e.target.value); setSelectedSession(null) }}
          >
            <option value="today">Today</option>
            {dates.map(d => <option key={d} value={d}>{d}</option>)}
          </select>
        </div>

        <div
          className={`activity-session-item ${!selectedSession ? 'active' : ''}`}
          onClick={() => setSelectedSession(null)}
        >
          <div className="activity-session-name">All sessions</div>
          <div className="activity-session-meta">{events.length} events</div>
        </div>

        {Object.entries(grouped).map(([projectPath, group]) => (
          <div key={projectPath} className="activity-project-group">
            <div className="activity-project-header">{group.name}</div>
            {group.sessions.map(s => (
              <div
                key={s.session_id}
                className={`activity-session-item ${selectedSession === s.session_id ? 'active' : ''}`}
                onClick={() => setSelectedSession(s.session_id)}
              >
                <div className="activity-session-name">
                  <StatusDot status={s.status} />
                  {s.session_id.slice(0, 8)}
                  {s.is_worktree && <WorktreeBadge name={s.worktree_name} />}
                </div>
                <div className="activity-session-meta">
                  {s.event_count} events &middot; {formatTime(s.last_activity)}
                </div>
                <div className="activity-session-last">{s.last_event}</div>
              </div>
            ))}
          </div>
        ))}

        {sessions.length === 0 && (
          <div className="activity-empty-sessions">No sessions yet. Start a Claude Code session to see activity here.</div>
        )}
      </div>

      {/* Right: Event stream */}
      <div className="activity-stream">
        <div className="activity-toolbar">
          <select
            className="form-select"
            value={filterType}
            onChange={e => setFilterType(e.target.value)}
          >
            {eventTypes.map(t => (
              <option key={t} value={t}>{t === 'all' ? 'All events' : t}</option>
            ))}
          </select>
          <label className="activity-autoscroll">
            <input
              type="checkbox"
              checked={autoScroll}
              onChange={e => setAutoScroll(e.target.checked)}
            />
            Auto-scroll
          </label>
          <span className="text2" style={{ marginLeft: 'auto', fontSize: 12 }}>
            {filteredEvents.length} events
            {selectedDate !== 'today' && <span style={{ marginLeft: 8, color: 'var(--yellow)' }}>{selectedDate}</span>}
          </span>
        </div>

        <div className="activity-events-list" ref={scrollRef}>
          {filteredEvents.length === 0 ? (
            <div className="activity-empty">
              <p>No events yet</p>
              <p className="text2">Events will appear here in real-time as Claude Code sessions run.</p>
            </div>
          ) : (
            filteredEvents.map((evt, i) => (
              <EventRow
                key={`${evt.ts}-${i}`}
                event={evt}
                onClick={(e) => setExpandedEvent(expandedEvent === i ? null : i)}
              />
            ))
          )}
          {expandedEvent !== null && filteredEvents[expandedEvent] && (
            <div className="activity-event-detail-panel">
              <pre className="md-pre">{JSON.stringify(filteredEvents[expandedEvent], null, 2)}</pre>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
