Hourly health check and auto-fix service for all active PLC projects and scrum-team feature branches. Scans project state, produces a dashboard at `docs/supervisor/DASHBOARD.md`, and auto-spawns agents to unblock stalled work.

Compatible with `/loop 1h /supervisor` for automated monitoring.

## MANDATORY: Agent Execution Mode

**CRITICAL**: The project-supervisor agent you spawn MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution.

<boot>
BEFORE doing anything else:

**Step 1 — Parse $ARGUMENTS:**
- If `--report-only` is present: set REPORT_ONLY flag.
- If `--fix-only <slug>` is present: extract the slug and set FIX_ONLY flag.
- If `--stall-threshold <hours>` is present: extract the hours value (default: 2).
- If `--verbose` is present: set VERBOSE flag.

**Step 2 — Build the prompt:**

Construct the supervisor prompt with all parsed flags.

**Step 3 — Spawn the supervisor agent:**

```
Spawn Agent:
  subagent_type = "project-supervisor"
  mode          = "bypassPermissions"
  prompt        = """
    Run the full project supervisor workflow.
    Flags: [report-only: <true/false>] [fix-only: <slug or none>] [stall-threshold: <N>h] [verbose: <true/false>]

    1. Discover all active PLC projects (docs/plc/*/PLC-STATE.md) and scrum-team features (feature/* branches + docs/features/*/PROGRESS.md)
    2. Assess health of each project (HEALTHY, AT_RISK, STALLED, BLOCKED, ACTIVE)
    3. Check for running orchestrators (lock files, recent PLC-STATE.md changes) — never interfere with ACTIVE projects
    4. Write dashboard to docs/supervisor/DASHBOARD.md
    5. Auto-fix stalled projects by spawning the appropriate agents (max 3 per run)
    6. Append results to docs/supervisor/SUPERVISOR-LOG.md
  """
```
</boot>
