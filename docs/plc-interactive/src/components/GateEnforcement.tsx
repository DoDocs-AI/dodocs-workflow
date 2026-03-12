import { motion } from 'framer-motion'
import { phases } from '../data'
import './GateEnforcement.css'

export function GateEnforcement() {
  return (
    <section className="section">
      <h2 className="section-title">Phase Gates</h2>
      <p className="section-subtitle">
        Enforced quality gates between each phase — criteria must pass before advancing.
      </p>

      <div className="gates-timeline">
        {phases.map((phase, i) => (
          <motion.div
            key={phase.id}
            className="gate-step"
            style={{ '--phase-color': phase.color } as React.CSSProperties}
            initial={{ opacity: 0, x: -30 }}
            whileInView={{ opacity: 1, x: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1 }}
          >
            <div className="gate-step-line">
              <div className="gate-step-dot" />
              {i < phases.length - 1 && <div className="gate-step-connector" />}
            </div>

            <div className="gate-step-content">
              <div className="gate-step-header">
                <span className="gate-step-emoji">{phase.emoji}</span>
                <span className="gate-step-name">{phase.name}</span>
                <span className="gate-step-number">Phase {i + 1}</span>
              </div>

              {i < phases.length - 1 && (
                <div className="gate-criteria-box">
                  <div className="gate-criteria-label">Gate {i + 1} Requirements</div>
                  {phase.gateCriteria.map((gc) => (
                    <div key={gc} className="gate-criteria-item">
                      <span className="gate-criteria-check">✓</span>
                      {gc}
                    </div>
                  ))}
                </div>
              )}
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
