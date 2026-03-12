import { useState } from 'react'
import { motion, AnimatePresence } from 'framer-motion'
import { phases } from '../data'
import type { Phase } from '../App'
import './AgentRoster.css'

const modelInfo = {
  opus: { label: 'Opus', color: 'var(--accent-opus)', desc: 'Reasoning & Strategy' },
  sonnet: { label: 'Sonnet', color: 'var(--accent-sonnet)', desc: 'Execution & Speed' },
  haiku: { label: 'Haiku', color: 'var(--accent-haiku)', desc: 'High-Frequency' },
}

export function AgentRoster() {
  const [filter, setFilter] = useState<Phase | 'all'>('all')

  const filteredPhases = filter === 'all' ? phases : phases.filter((p) => p.id === filter)
  const allAgents = filteredPhases.flatMap((p) =>
    p.agents.map((a) => ({ ...a, phase: p.id, phaseColor: p.color, phaseEmoji: p.emoji }))
  )

  return (
    <section className="section">
      <h2 className="section-title">Agent Roster</h2>
      <p className="section-subtitle">
        Every AI agent in the PLC framework, organized by phase.
      </p>

      <div className="roster-filters">
        <button
          className={`roster-filter ${filter === 'all' ? 'active' : ''}`}
          onClick={() => setFilter('all')}
        >
          All ({phases.reduce((s, p) => s + p.agents.length, 0)})
        </button>
        {phases.map((p) => (
          <button
            key={p.id}
            className={`roster-filter ${filter === p.id ? 'active' : ''}`}
            style={{ '--filter-color': p.color } as React.CSSProperties}
            onClick={() => setFilter(p.id)}
          >
            {p.emoji} {p.name} ({p.agents.length})
          </button>
        ))}
      </div>

      <div className="roster-grid">
        <AnimatePresence mode="popLayout">
          {allAgents.map((agent) => (
            <motion.div
              key={`${agent.phase}-${agent.name}`}
              className="roster-card"
              style={{ '--card-color': agent.phaseColor } as React.CSSProperties}
              layout
              initial={{ opacity: 0, scale: 0.9 }}
              animate={{ opacity: 1, scale: 1 }}
              exit={{ opacity: 0, scale: 0.9 }}
              transition={{ duration: 0.25 }}
              whileHover={{ y: -4 }}
            >
              <div className="roster-card-top">
                <span className="roster-card-emoji">{agent.emoji}</span>
                <span
                  className="roster-card-model"
                  style={{ color: modelInfo[agent.model].color }}
                >
                  {modelInfo[agent.model].label}
                </span>
              </div>
              <div className="roster-card-name">{agent.name}</div>
              <div className="roster-card-role">{agent.role}</div>
              <div className="roster-card-phase">
                {agent.phaseEmoji} {agent.phase}
              </div>
            </motion.div>
          ))}
        </AnimatePresence>
      </div>
    </section>
  )
}
