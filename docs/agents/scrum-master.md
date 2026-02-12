# Scrum Master

The Scrum Master translates the Architecture document into actionable tasks. They create, assign, and manage dependencies between tasks to ensure parallel development works without conflicts.

## Overview

| Property | Value |
|----------|-------|
| **Agent file** | `agents/scrum-master.md` |
| **Model** | opus |
| **Active in phases** | Phase 4 |
| **Tools** | Read, Grep, Glob, Write, Bash |
| **Outputs** | Task list with assignments and dependencies |

## What It Does

1. **Reads the Architecture doc** — Understands every endpoint, entity, component, and route to be built.

2. **Creates tasks** — Breaks the architecture into granular tasks using `TaskCreate`, each with:
   - Clear description with exact file paths
   - Acceptance criteria
   - Assignment to a specific developer or QA agent
   - Git commit message instruction

3. **Enforces rules**:
   - **Migration ownership**: ALL database migrations go to `backend-dev-1`. `backend-dev-2` never creates migration files.
   - **No file conflicts**: No two developers are assigned to edit the same file.
   - **Proper dependencies**: Uses `blockedBy` to ensure correct execution order.

4. **Monitors progress** — Checks TaskList periodically and reassigns blocked tasks if needed.

## Task Assignment Rules

| Task Type | Assigned To |
|-----------|-------------|
| Entity + migration | `backend-dev-1` |
| DTO classes | `backend-dev-1` |
| Service layer | `backend-dev-2` (blocked by entity tasks) |
| Resource/controller | `backend-dev-2` (blocked by service tasks) |
| Frontend types + API service | `frontend-dev-1` (blocked by resource tasks) |
| Page components | `frontend-dev-1` |
| Sub-components | `frontend-dev-2` |
| Routes | `frontend-dev-1` (blocked by page tasks) |
| Test case writing | `qa-engineer` |
| E2E test writing | `qa-automation` |
| Manual testing | `manual-tester` |

## Dependency Chain Example

```
backend-dev-1: Create entity + migration (no deps)
       |
backend-dev-1: Create DTO classes (no deps)
       |
       v
backend-dev-2: Create service layer (blocked by entity + DTO)
       |
       v
backend-dev-2: Create resource/controller (blocked by service)
       |
       v
frontend-dev-1: Create types + API service (blocked by resource)
       |
       +---> frontend-dev-1: Create page (blocked by types)
       |           |
       |           v
       |     frontend-dev-1: Add route (blocked by page)
       |
       +---> frontend-dev-2: Create sub-components (blocked by types)
```

## Config Sections Used

| Section | Purpose |
|---------|---------|
| App Identity | Context for task descriptions |
| Feature Docs path | Locates the Architecture doc |
| Source Paths — Backend (Migrations) | Understands migration conventions |

## Coordination

- Reads the Architecture doc produced by the Architect
- Creates tasks that developers, QA engineer, manual-tester, and qa-automation work on
- Code review tasks are NOT created — the code-reviewer monitors completed tasks automatically

## When It Runs

- **Full workflow**: Phase 4
- **Retest mode**: Not spawned
