import { motion, AnimatePresence } from 'framer-motion'
import { phases } from '../data'
import type { Phase } from '../App'
import './PhaseDetails.css'

interface Props {
  activePhase: Phase | null
  setActivePhase: (p: Phase | null) => void
}

const modelColors = {
  opus: 'var(--accent-opus)',
  sonnet: 'var(--accent-sonnet)',
  haiku: 'var(--accent-haiku)',
}

export function PhaseDetails({ activePhase, setActivePhase }: Props) {
  const phase = phases.find((p) => p.id === activePhase)

  return (
    <div className="section phase-details-container">
      <AnimatePresence mode="wait">
        {phase && (
          <motion.div
            key={phase.id}
            className="phase-details"
            style={{ '--phase-color': phase.color } as React.CSSProperties}
            initial={{ opacity: 0, y: 20, height: 0 }}
            animate={{ opacity: 1, y: 0, height: 'auto' }}
            exit={{ opacity: 0, y: -20, height: 0 }}
            transition={{ duration: 0.4, ease: 'easeInOut' }}
          >
            <div className="phase-details-header">
              <div className="phase-details-title-row">
                <span className="phase-details-emoji">{phase.emoji}</span>
                <div>
                  <h3 className="phase-details-title">{phase.name}</h3>
                  <p className="phase-details-tagline">{phase.tagline}</p>
                </div>
              </div>
              <button className="phase-details-close" onClick={() => setActivePhase(null)}>
                &times;
              </button>
            </div>

            <p className="phase-details-description">{phase.description}</p>

            <div className="phase-details-grid">
              <div className="phase-details-column">
                <h4 className="phase-details-column-title">Agents</h4>
                <div className="agent-list">
                  {phase.agents.map((agent, i) => (
                    <motion.div
                      key={agent.name}
                      className="agent-card"
                      initial={{ opacity: 0, x: -20 }}
                      animate={{ opacity: 1, x: 0 }}
                      transition={{ delay: i * 0.05 }}
                    >
                      <span className="agent-card-emoji">{agent.emoji}</span>
                      <div className="agent-card-info">
                        <span className="agent-card-name">{agent.name}</span>
                        <span className="agent-card-role">{agent.role}</span>
                      </div>
                      <span
                        className="agent-card-model"
                        style={{ color: modelColors[agent.model] }}
                      >
                        {agent.model}
                      </span>
                    </motion.div>
                  ))}
                </div>
              </div>

              <div className="phase-details-side">
                <div className="phase-details-column">
                  <h4 className="phase-details-column-title">Outputs</h4>
                  <ul className="output-list">
                    {phase.outputs.map((out) => (
                      <li key={out} className="output-item">
                        <span className="output-check">✦</span>
                        {out}
                      </li>
                    ))}
                  </ul>
                </div>

                <div className="phase-details-column">
                  <h4 className="phase-details-column-title">Gate Criteria</h4>
                  <ul className="output-list">
                    {phase.gateCriteria.map((gc) => (
                      <li key={gc} className="output-item gate-item">
                        <span className="output-check gate-check">◆</span>
                        {gc}
                      </li>
                    ))}
                  </ul>
                </div>
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  )
}
