import { motion } from 'framer-motion'
import { phases } from '../data'
import type { Phase } from '../App'
import './PipelineFlow.css'

interface Props {
  activePhase: Phase | null
  setActivePhase: (p: Phase | null) => void
}

export function PipelineFlow({ activePhase, setActivePhase }: Props) {
  return (
    <section className="section pipeline-section">
      <h2 className="section-title">The Pipeline</h2>
      <p className="section-subtitle">Click any phase to explore its agents, outputs, and gate criteria.</p>

      <div className="pipeline">
        {phases.map((phase, i) => (
          <motion.div
            key={phase.id}
            className={`pipeline-phase ${activePhase === phase.id ? 'active' : ''}`}
            style={{ '--phase-color': phase.color } as React.CSSProperties}
            initial={{ opacity: 0, y: 30 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1, duration: 0.5 }}
            whileHover={{ scale: 1.05, y: -4 }}
            whileTap={{ scale: 0.98 }}
            onClick={() => setActivePhase(activePhase === phase.id ? null : phase.id)}
          >
            <div className="pipeline-phase-icon">{phase.emoji}</div>
            <div className="pipeline-phase-name">{phase.name}</div>
            <div className="pipeline-phase-agents">{phase.agents.length} agents</div>
            <div className="pipeline-phase-glow" />
          </motion.div>
        ))}

        {/* Connection lines */}
        <svg className="pipeline-connections" viewBox="0 0 1000 10" preserveAspectRatio="none">
          {[0, 1, 2, 3, 4].map((i) => (
            <line
              key={i}
              x1={i * 200 + 140}
              y1={5}
              x2={i * 200 + 200}
              y2={5}
              stroke="rgba(255,255,255,0.1)"
              strokeWidth="2"
              strokeDasharray="6 4"
            >
              <animate
                attributeName="stroke-dashoffset"
                from="20"
                to="0"
                dur="1.5s"
                repeatCount="indefinite"
              />
            </line>
          ))}
        </svg>
      </div>
    </section>
  )
}
