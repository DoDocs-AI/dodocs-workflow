# Backend Dev

Implements backend tasks — controllers, entities, services, DTOs, migrations — and writes integration tests. Makes atomic git commits per task. Two instances run in parallel: `backend-dev-1` (owns migrations) and `backend-dev-2` (services/endpoints only).

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/backend-dev.md` |
| **Model** | sonnet |
| **Active in phases** | 5 (build) |
| **Instances** | 2 (`backend-dev-1`, `backend-dev-2`) |
| **Tools** | Read, Write, Edit, Bash, Grep, Glob |
| **Outputs** | Backend code + migrations + tests + atomic git commits |

## Workflow Per Task

1. Read TaskList and TaskGet for assigned work.
2. Study existing patterns — reads similar files in Resources, Entities, Services, DTOs, Migrations, Tests.
3. Implement the task following existing patterns exactly.
4. Write integration tests for new endpoints/services.
5. Compile: run Compile Backend command, fix any errors.
6. Atomic git commit: `backend: <description>`.
7. Mark task completed, check TaskList for next assignment.

## Progress Tracking

After completing each task, updates the Development Tasks table in `PROGRESS.md` (sets task status to Done) and adds a timeline entry.

## Migration Ownership Rules

| Developer | Can Create Migrations | Can Create Entities | Can Create Services/Endpoints |
|-----------|----------------------|--------------------|-----------------------------|
| `backend-dev-1` | Yes | Yes | Yes |
| `backend-dev-2` | **No** | No (blocked by dev-1) | Yes (after dev-1 creates entities) |

- `backend-dev-1` owns ALL database migrations: entity creation, migration SQL files, schema changes.
- `backend-dev-2` handles services, endpoints, DTOs that depend on entities created by dev-1.
- Migration files follow the naming convention of the Migration Tool in the config.
- Never modify existing migration files — always create new ones.
- Check existing migrations for the next version number.

## Multi-Instance Coordination

- Scrum Master assigns tasks to avoid file conflicts.
- `backend-dev-2` tasks that need new tables/columns are `blockedBy` the migration task assigned to `backend-dev-1`.
- If a developer needs to edit a file assigned to the other, they create a conflict task and notify via SendMessage.

## Config Sections Used

- Tech Stack (Backend Framework, Database, Migration Tool, Storage, Auth, API Pattern)
- Source Paths — Backend (Resources, Entities, Services, DTOs, Migrations, Tests)
- Commands (Compile Backend)

## When It Runs

- **Full workflow**: Phase 5 (both instances)
- **Retest mode**: `backend-dev-1` only — stands by for API/DB bug fixes
