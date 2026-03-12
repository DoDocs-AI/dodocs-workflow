import { motion } from 'framer-motion'
import { phases } from '../data'
import './ModelStrategy.css'

const models = [
  {
    name: 'Opus',
    color: 'var(--accent-opus)',
    purpose: 'Reasoning & Strategy',
    description: 'Used for planning, reviewing, and strategic decisions that require deep reasoning.',
    icon: '🧠',
  },
  {
    name: 'Sonnet',
    color: 'var(--accent-sonnet)',
    purpose: 'Execution & Speed',
    description: 'Powers execution roles — development, QA, design — where speed and cost efficiency matter.',
    icon: '⚡',
  },
  {
    name: 'Haiku',
    color: 'var(--accent-haiku)',
    purpose: 'High-Frequency Interactions',
    description: 'Handles frequent browser interactions for manual testing via Playwright.',
    icon: '🏃',
  },
]

export function ModelStrategy() {
  const allAgents = phases.flatMap((p) => p.agents)
  const counts = {
    opus: allAgents.filter((a) => a.model === 'opus').length,
    sonnet: allAgents.filter((a) => a.model === 'sonnet').length,
    haiku: allAgents.filter((a) => a.model === 'haiku').length,
  }
  const total = allAgents.length

  return (
    <section className="section">
      <h2 className="section-title">Model Strategy</h2>
      <p className="section-subtitle">
        Each agent uses the optimal Claude model for its role.
      </p>

      <div className="model-bar">
        {(['opus', 'sonnet', 'haiku'] as const).map((m) => (
          <motion.div
            key={m}
            className="model-bar-segment"
            style={{
              '--model-color': models.find((x) => x.name.toLowerCase() === m)?.color,
              width: `${(counts[m] / total) * 100}%`,
            } as React.CSSProperties}
            initial={{ width: 0 }}
            whileInView={{ width: `${(counts[m] / total) * 100}%` }}
            viewport={{ once: true }}
            transition={{ duration: 0.8, ease: 'easeOut' }}
          >
            <span className="model-bar-label">
              {m} ({counts[m]})
            </span>
          </motion.div>
        ))}
      </div>

      <div className="model-cards">
        {models.map((model, i) => (
          <motion.div
            key={model.name}
            className="model-card"
            style={{ '--model-color': model.color } as React.CSSProperties}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true }}
            transition={{ delay: i * 0.1 }}
            whileHover={{ y: -4 }}
          >
            <div className="model-card-icon">{model.icon}</div>
            <div className="model-card-name">{model.name}</div>
            <div className="model-card-purpose">{model.purpose}</div>
            <div className="model-card-desc">{model.description}</div>
            <div className="model-card-count">
              {counts[model.name.toLowerCase() as keyof typeof counts]} agents
            </div>
          </motion.div>
        ))}
      </div>
    </section>
  )
}
