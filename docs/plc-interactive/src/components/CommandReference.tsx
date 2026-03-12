import { motion } from 'framer-motion'
import './CommandReference.css'

const flags = [
  { flag: '--auto', effect: 'Skip human approval gates', icon: '🤖' },
  { flag: '--skip-discover', effect: 'Jump past discovery phase', icon: '⏭️' },
  { flag: '--skip-build', effect: 'Skip build phase', icon: '🔧' },
  { flag: '--resume', effect: 'Resume from existing PLC-STATE.md', icon: '▶️' },
]

const outputs = [
  { path: 'docs/plc/<slug>/gates/', desc: 'Gate check reports', icon: '🚦' },
  { path: 'docs/plc/<slug>/PLC-STATE.md', desc: 'Current pipeline state', icon: '📄' },
  { path: 'docs/features/<feature>/', desc: 'Feature docs & architecture', icon: '📁' },
  { path: 'Pull Request', desc: 'Auto-created PR with all changes', icon: '🔀' },
]

export function CommandReference() {
  return (
    <section className="section">
      <h2 className="section-title">Quick Reference</h2>
      <p className="section-subtitle">
        Everything you need to run the PLC pipeline.
      </p>

      <div className="cmd-grid">
        <motion.div
          className="cmd-block"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
        >
          <h3 className="cmd-block-title">Command</h3>
          <div className="cmd-code-block">
            <code className="cmd-code">
              <span className="cmd-slash">/</span>product-lifecycle{' '}
              <span className="cmd-arg">&lt;product-name&gt;</span>
            </code>
          </div>
        </motion.div>

        <motion.div
          className="cmd-block"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.1 }}
        >
          <h3 className="cmd-block-title">Flags</h3>
          <div className="cmd-flag-list">
            {flags.map((f) => (
              <div key={f.flag} className="cmd-flag-item">
                <span className="cmd-flag-icon">{f.icon}</span>
                <code className="cmd-flag-name">{f.flag}</code>
                <span className="cmd-flag-desc">{f.effect}</span>
              </div>
            ))}
          </div>
        </motion.div>

        <motion.div
          className="cmd-block"
          initial={{ opacity: 0, y: 20 }}
          whileInView={{ opacity: 1, y: 0 }}
          viewport={{ once: true }}
          transition={{ delay: 0.2 }}
        >
          <h3 className="cmd-block-title">Outputs</h3>
          <div className="cmd-flag-list">
            {outputs.map((o) => (
              <div key={o.path} className="cmd-flag-item">
                <span className="cmd-flag-icon">{o.icon}</span>
                <code className="cmd-output-path">{o.path}</code>
                <span className="cmd-flag-desc">{o.desc}</span>
              </div>
            ))}
          </div>
        </motion.div>
      </div>
    </section>
  )
}
