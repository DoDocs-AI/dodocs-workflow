# Ideas from OpenAI Symphony

> Source: https://github.com/openai/symphony/blob/main/SPEC.md
> Date: 2026-03-05

## What is Symphony?

Symphony is a **long-running orchestration daemon** that continuously polls an issue tracker (Linear), creates isolated per-issue workspaces, and runs single coding agent sessions within those environments. Key design: `WORKFLOW.md` file (YAML front matter + prompt template) defines the entire workflow declaratively.

## Comparison with dodocs-workflow (Workspace OS)

| Aspect | Symphony | dodocs-workflow |
|--------|----------|-----------------|
| Trigger | Polls issue tracker continuously | Human-invoked slash commands |
| Unit of work | Single issue → single agent | Feature → 13+ agent team |
| Agent model | 1 agent per issue (Codex) | Specialized role-based agents |
| Orchestration | Daemon service with state machine | Team lead + task dependencies |
| Config | `WORKFLOW.md` (YAML front matter) | `.claude/scrum-team-config.md` |
| Workspace | Filesystem directory per issue | Git branches + feature doc dirs |
| Persistence | Filesystem-based (no DB) | `registry.json` + feature docs |
| Concurrency | Pool of N agents, per-state limits | Phase-based parallelism |

### Where dodocs-workflow is stronger
- Multi-agent collaboration (13 specialized agents vs 1)
- Full SDLC coverage (requirements → testing → PR)
- Story-level testing (testing runs in parallel with dev)
- Production audits (10 parallel quality auditors)
- Richer dashboard (project management, docs, sessions)

### Where Symphony has ideas worth borrowing
- Continuous daemon polling (vs manual `/workspace run`)
- Declarative workflow definitions (`WORKFLOW.md`)
- Issue tracker integration (Linear-native)
- Formal run state machine (idle → dispatched → running → success/failure → retry)
- Exponential backoff retry policy
- Workspace lifecycle hooks (before_run, after_run, etc.)
- SSE event stream for real-time monitoring
- Per-state concurrency limits
- Dynamic configuration reload

---

## High-Impact Ideas to Implement

### 1. Issue Tracker Integration (GitHub Issues → auto-dispatch)
**The biggest gap.** Symphony is Linear-native. We should support GitHub Issues.

- When an issue gets labeled `ai-ready`, auto-trigger `/fix-the-issue` or `/scrum-team`
- Post results (PR links, status) back as issue comments
- Closes the loop between project management and agent execution
- See: `PLAN-ISSUE-TRACKER.md`

### 2. Daemon Mode for Workspace Supervisor
**Makes the system truly autonomous.** Symphony runs as a persistent daemon polling every 30s.

- Persistent background process watching `registry.json` for new tasks
- Auto-dispatches without manual `/workspace run`
- Runs as launchd service on macOS
- See: `PLAN-DAEMON-MODE.md`

### 3. SSE Event Stream (Real-time Dashboard)
**Better real-time experience.** Symphony has `/api/events/stream` SSE endpoint.

- We already have the SSE infrastructure in `server.py` (EventStore + subscribers)
- Need to wire the dashboard frontend to use it instead of 10s polling
- See: `PLAN-SSE-STREAM.md`

---

## Medium-Impact Ideas (Future)

### 4. Lifecycle Hooks in scrum-team-config
Formalize `before_feature`, `after_feature`, `before_phase`, `after_phase` hooks defined in config.

### 5. Run State Machine
Formal state machine per feature: `idle → dispatched → running → success/failure → retry_scheduled`.
Stored as `docs/features/<slug>/RUN-STATE.json`.

### 6. Concurrency Limits for Batch Features
`max_concurrent_features` for `/batch-features`, per-phase agent limits.

### 7. Declarative Workflows (WORKFLOW.md equivalent)
User-defined workflows in `workflows/` directory. Each = YAML config + prompt template.
Make `/scrum-team`, `/fix-the-issue`, `/change-request` just built-in workflows.

### 8. Dynamic Config Reload
Hot-reload `.claude/scrum-team-config.md` changes, dashboard-driven config toggles.
