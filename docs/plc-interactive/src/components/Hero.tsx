import { motion } from 'framer-motion'
import { totalAgents, phases } from '../data'
import './Hero.css'

export function Hero() {
  return (
    <section className="hero">
      <motion.div
        className="hero-content"
        initial={{ opacity: 0, y: 40 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.8, ease: 'easeOut' }}
      >
        <div className="hero-badge">
          <span className="hero-badge-dot" />
          dodocs-workflow
        </div>
        <h1 className="hero-title">
          Product Lifecycle
          <br />
          <span className="hero-title-gradient">Framework</span>
        </h1>
        <p className="hero-description">
          From raw concept to profitable business. {totalAgents}+ AI agents across {phases.length} phases
          orchestrate the entire product lifecycle — market research, strategy, development, launch, growth, and evolution.
        </p>
        <div className="hero-stats">
          <div className="hero-stat">
            <span className="hero-stat-value">{totalAgents}+</span>
            <span className="hero-stat-label">AI Agents</span>
          </div>
          <div className="hero-stat-divider" />
          <div className="hero-stat">
            <span className="hero-stat-value">{phases.length}</span>
            <span className="hero-stat-label">Phases</span>
          </div>
          <div className="hero-stat-divider" />
          <div className="hero-stat">
            <span className="hero-stat-value">1</span>
            <span className="hero-stat-label">Command</span>
          </div>
        </div>
        <div className="hero-command">
          <code>/product-lifecycle my-product</code>
        </div>
      </motion.div>

      <motion.div
        className="hero-orbit"
        initial={{ opacity: 0, scale: 0.8 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ duration: 1, delay: 0.3 }}
      >
        <div className="orbit-ring orbit-ring-1">
          {phases.slice(0, 3).map((p, i) => (
            <div
              key={p.id}
              className="orbit-node"
              style={{
                '--color': p.color,
                '--delay': `${i * -3.3}s`,
              } as React.CSSProperties}
            >
              <span>{p.emoji}</span>
            </div>
          ))}
        </div>
        <div className="orbit-ring orbit-ring-2">
          {phases.slice(3).map((p, i) => (
            <div
              key={p.id}
              className="orbit-node"
              style={{
                '--color': p.color,
                '--delay': `${i * -3.3}s`,
              } as React.CSSProperties}
            >
              <span>{p.emoji}</span>
            </div>
          ))}
        </div>
        <div className="orbit-center">
          <span>🎯</span>
          <small>PLC</small>
        </div>
      </motion.div>
    </section>
  )
}
