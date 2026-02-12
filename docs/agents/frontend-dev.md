# Frontend Dev

Implements frontend tasks — pages, components, services, types, routes — following existing patterns. Makes atomic git commits per task. Two instances run in parallel: `frontend-dev-1` and `frontend-dev-2`.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/frontend-dev.md` |
| **Model** | sonnet |
| **Active in phases** | 5 (build) |
| **Instances** | 2 (`frontend-dev-1`, `frontend-dev-2`) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Outputs** | Frontend code + atomic git commits |

## Workflow Per Task

1. Read TaskList and TaskGet for assigned work.
2. Study existing patterns — reads similar files in Pages, Components, Services, Types, Router.
3. Implement the task following existing patterns exactly.
4. Compile: run Compile Frontend command, fix any errors.
5. Atomic git commit: `frontend: <description>`.
6. Mark task completed, check TaskList for next assignment.

## Multi-Instance Coordination

- `frontend-dev-1` and `frontend-dev-2` work on different files/components.
- Scrum Master assigns tasks to avoid file conflicts.
- If a developer needs to edit a file assigned to the other, they create a conflict task and notify via SendMessage.

## Post-Task Flow

After marking task complete:
- Code-reviewer reviews the code.
- If approved: moves to testing.
- If changes requested: developer fixes and re-commits.

## Config Sections Used

- Tech Stack (Frontend Framework)
- Source Paths — Frontend (Pages, Workspace Pages, Components, Services, Types, Router)
- Commands (Compile Frontend)
- Routing (Route Prefix)

## When It Runs

- **Full workflow**: Phase 5 (both instances)
- **Retest mode**: `frontend-dev-1` only — stands by for UI bug fixes
