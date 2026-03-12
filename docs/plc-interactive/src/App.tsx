import { useState } from 'react'
import { Hero } from './components/Hero'
import { PipelineFlow } from './components/PipelineFlow'
import { PhaseDetails } from './components/PhaseDetails'
import { AgentRoster } from './components/AgentRoster'
import { ModelStrategy } from './components/ModelStrategy'
import { GateEnforcement } from './components/GateEnforcement'
import { CommandReference } from './components/CommandReference'
import './App.css'

export type Phase = 'discover' | 'strategy' | 'build' | 'launch' | 'grow' | 'evolve'

function App() {
  const [activePhase, setActivePhase] = useState<Phase | null>(null)

  return (
    <div className="app">
      <div className="bg-grid" />
      <div className="bg-glow bg-glow-1" />
      <div className="bg-glow bg-glow-2" />
      <div className="bg-glow bg-glow-3" />
      <Hero />
      <PipelineFlow activePhase={activePhase} setActivePhase={setActivePhase} />
      <PhaseDetails activePhase={activePhase} setActivePhase={setActivePhase} />
      <GateEnforcement />
      <AgentRoster />
      <ModelStrategy />
      <CommandReference />
      <footer className="footer">
        <p>dodocs-workflow v1.6.0 &middot; Product Lifecycle Framework</p>
        <p className="footer-sub">20+ AI agents &middot; 6 phases &middot; Concept to Profit</p>
      </footer>
    </div>
  )
}

export default App
