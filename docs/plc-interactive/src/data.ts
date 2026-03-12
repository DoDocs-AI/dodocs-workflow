import type { Phase } from './App'

export interface Agent {
  name: string
  emoji: string
  model: 'opus' | 'sonnet' | 'haiku'
  role: string
}

export interface PhaseData {
  id: Phase
  name: string
  emoji: string
  color: string
  tagline: string
  description: string
  agents: Agent[]
  outputs: string[]
  gateCriteria: string[]
}

export const phases: PhaseData[] = [
  {
    id: 'discover',
    name: 'Discover',
    emoji: '🔍',
    color: 'var(--accent-discover)',
    tagline: 'Validate the opportunity',
    description: 'Research the market, define your ideal customer, and validate demand before writing a single line of code.',
    agents: [
      { name: 'Market Scout', emoji: '🔍', model: 'sonnet', role: 'Competitive landscape & opportunity scanning' },
      { name: 'ICP Profiler', emoji: '👤', model: 'sonnet', role: 'Ideal customer profile definition' },
      { name: 'Validation Agent', emoji: '✅', model: 'sonnet', role: 'Demand testing with real prospects' },
    ],
    outputs: ['Market research report', 'ICP profiles', 'Demand validation results'],
    gateCriteria: ['Market data validated', 'ICP defined', 'Demand confirmed'],
  },
  {
    id: 'strategy',
    name: 'Strategy',
    emoji: '📐',
    color: 'var(--accent-strategy)',
    tagline: 'Plan the product',
    description: 'Create the product strategy, plan the roadmap, design pricing, and scope the MVP to the essential core.',
    agents: [
      { name: 'Product Strategist', emoji: '📋', model: 'opus', role: 'Strategy brief creation' },
      { name: 'Roadmap Planner', emoji: '🗺️', model: 'sonnet', role: 'NOW/NEXT/LATER roadmap' },
      { name: 'Pricing Architect', emoji: '💰', model: 'opus', role: 'Pricing model design' },
      { name: 'MVP Scoper', emoji: '🎯', model: 'opus', role: 'MoSCoW classification & core flow' },
    ],
    outputs: ['Strategy brief', 'Product roadmap', 'Pricing model', 'MVP scope document'],
    gateCriteria: ['Strategy brief approved', 'Roadmap created', 'MVP scope locked'],
  },
  {
    id: 'build',
    name: 'Build',
    emoji: '🔨',
    color: 'var(--accent-build)',
    tagline: 'Build the MVP',
    description: 'Full 13-agent scrum team builds the MVP — requirements, design, architecture, development, review, and testing.',
    agents: [
      { name: 'Product Owner', emoji: '📝', model: 'opus', role: 'Requirements & Feature Brief' },
      { name: 'UX Designer', emoji: '🎨', model: 'sonnet', role: 'User flow design' },
      { name: 'Architect', emoji: '🏗️', model: 'opus', role: 'Technical solution design' },
      { name: 'Scrum Master', emoji: '📊', model: 'sonnet', role: 'Task breakdown & assignment' },
      { name: 'Tech Lead', emoji: '⚙️', model: 'sonnet', role: 'Git, compile gates, PR creation' },
      { name: 'Frontend Dev', emoji: '💻', model: 'sonnet', role: 'Frontend implementation' },
      { name: 'Backend Dev', emoji: '🖥️', model: 'sonnet', role: 'Backend & migrations' },
      { name: 'Code Reviewer', emoji: '🔎', model: 'opus', role: 'Quality & security review' },
      { name: 'QA Engineer', emoji: '📋', model: 'sonnet', role: 'Test case documentation' },
      { name: 'Manual Tester', emoji: '🧪', model: 'haiku', role: 'Browser testing via Playwright' },
      { name: 'QA Automation', emoji: '🤖', model: 'sonnet', role: 'E2E Playwright tests' },
      { name: 'Mockup Designer', emoji: '🖼️', model: 'sonnet', role: 'Framework-native UI mockups' },
      { name: 'Mockup Validator', emoji: '✔️', model: 'sonnet', role: 'Validates mockups vs requirements' },
    ],
    outputs: ['Feature branch with atomic commits', 'All docs in docs/features/', 'Tested MVP', 'Pull request'],
    gateCriteria: ['MVP built & tested', 'All stories pass QA', 'PR merged to main'],
  },
  {
    id: 'launch',
    name: 'Launch',
    emoji: '🚀',
    color: 'var(--accent-launch)',
    tagline: 'Ship to users',
    description: 'Set up analytics, write compelling copy, plan distribution channels, and activate monetization.',
    agents: [
      { name: 'Analytics Agent', emoji: '📊', model: 'sonnet', role: 'Analytics setup, event tracking, funnels' },
      { name: 'Copy Agent', emoji: '✍️', model: 'sonnet', role: 'Landing page copywriting' },
      { name: 'Distribution Agent', emoji: '📢', model: 'sonnet', role: 'Channel distribution strategy' },
      { name: 'Revenue Agent', emoji: '💵', model: 'sonnet', role: 'Monetization setup' },
    ],
    outputs: ['Analytics dashboard', 'Landing page copy', 'Distribution plan', 'Revenue integration'],
    gateCriteria: ['Analytics live', 'Landing page up', 'Monetization active'],
  },
  {
    id: 'grow',
    name: 'Grow',
    emoji: '📈',
    color: 'var(--accent-grow)',
    tagline: 'Scale the business',
    description: 'Run growth experiments, build retention loops, and create SEO content to drive organic traffic.',
    agents: [
      { name: 'Growth Hacker', emoji: '🚀', model: 'sonnet', role: 'Growth experiments & optimization' },
      { name: 'Retention Engineer', emoji: '🔁', model: 'sonnet', role: 'Churn reduction, engagement loops' },
      { name: 'SEO Content Agent', emoji: '📝', model: 'sonnet', role: 'SEO content strategy' },
    ],
    outputs: ['Growth experiment results', 'Retention playbook', 'SEO content calendar'],
    gateCriteria: ['Growth metrics tracked', 'Retention loops active', 'SEO content published'],
  },
  {
    id: 'evolve',
    name: 'Evolve',
    emoji: '🔄',
    color: 'var(--accent-evolve)',
    tagline: 'Continuously improve',
    description: 'Invent new features from feedback, monitor competitors, and listen to the voice of the customer.',
    agents: [
      { name: 'Feature Inventor', emoji: '💡', model: 'sonnet', role: 'Feature discovery from feedback' },
      { name: 'Competitive Intel', emoji: '🕵️', model: 'sonnet', role: 'Competitive monitoring' },
      { name: 'Customer Voice', emoji: '🗣️', model: 'sonnet', role: 'Customer feedback analysis' },
    ],
    outputs: ['Feature proposals', 'Competitive reports', 'Customer insights'],
    gateCriteria: ['Feedback loops established', 'Competitive monitoring active', 'Feature backlog updated'],
  },
]

export const totalAgents = phases.reduce((sum, p) => sum + p.agents.length, 0)
