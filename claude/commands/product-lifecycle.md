Orchestrate the Full-Cycle Product Lifecycle pipeline — 20+ agents across 6 phases taking a product from raw concept to profitable, self-evolving business (Discover → Strategy → Build → Launch → Grow → Evolve). Build phase delegates to the full plc-scrum-team pipeline with 13 agents.

## MANDATORY: Agent Execution Mode

**CRITICAL**: Every agent you spawn via the Agent tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution.

Spawn all agents automatically as their phase begins — do NOT ask the user for permission.

<boot>
BEFORE doing anything else:

**Step 1 — Parse $ARGUMENTS:**
- Extract flags first, then treat the remainder as the product name.
- If `--auto` is present: set AUTO_MODE=true; otherwise AUTO_MODE=false.
- If `--skip-discover` is present: set SKIP_DISCOVER=true; otherwise false.
- If `--skip-build` is present: set SKIP_BUILD=true; otherwise false.
- If `--skip-test` is present: set SKIP_TEST=true; otherwise false.
- If `--resume` is present: resume from existing PLC-STATE.md instead of starting fresh.
- Strip all parsed flags from $ARGUMENTS to obtain the clean product name.

**Step 2 — Derive slug:**
- Convert product name to kebab-case, max 40 characters.

**Step 3 — Create directory structure:**
```bash
mkdir -p docs/plc/<slug>/discover docs/plc/<slug>/strategy docs/plc/<slug>/build docs/plc/<slug>/launch docs/plc/<slug>/grow docs/plc/<slug>/grow/content docs/plc/<slug>/evolve docs/plc/<slug>/evolve/feedback docs/plc/<slug>/gates
```

**Step 4 — Write or read PLC-STATE.md:**
If --resume and `docs/plc/<slug>/PLC-STATE.md` exists, read it and resume from current phase.
Otherwise, write initial state:

```markdown
# Product Lifecycle: <Product Name>

## Current Phase
Phase 1 — Discover

## Phase Status
| Phase | Status | Gate Criteria | Met? |
|---|---|---|---|
| Discover | IN PROGRESS | 1 paid OR 3 clicked payment OR 10 waitlist with pain | NO |
| Strategy | PENDING | Strategy brief approved + pricing selected + MVP scoped | NO |
| Build | PENDING | Non-tech person completed core flow <5 min (via plc-scrum-team) | NO |
| Launch | PENDING | 100 visitors + 10 signups + 1 paying | NO |
| Grow | PENDING | MRR growing WoW OR churn <5% MoM | NO |
| Evolve | PENDING | Continuous | NO |

## Decision Log
| Date | Decision | By | Reasoning |

## KPI History
| Date | MRR | Users | Conversion | Churn | CAC |

## Agent Outputs
(Updated after each agent completes)

## Active Experiments
(Tracked by Growth Hacker)
```

**Step 5 — Launch orchestrator:**
Spawn `plc-orchestrator` agent with the product name, slug, and all flags. Pass the full PLC-STATE.md path.
</boot>
