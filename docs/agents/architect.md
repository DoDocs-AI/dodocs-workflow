# Architect

The Architect designs the complete technical solution for new features without changing the existing architecture. They study the codebase to understand current patterns and produce an Architecture document that serves as the blueprint for all development tasks.

## Overview

| Property | Value |
|----------|-------|
| **Agent file** | `agents/architect.md` |
| **Model** | opus |
| **Active in phases** | Phase 3 |
| **Tools** | Read, Grep, Glob, Write, Bash |
| **Mode** | `plan` (requires approval) |
| **Outputs** | `docs/features/<feature>/ARCHITECTURE.md` |

## What It Does

1. **Reads upstream documents** — Studies the Feature Brief and UX Design to understand what needs to be built.

2. **Researches existing code** — Reads existing controllers, entities, services, DTOs, pages, and components to understand current conventions. Every design decision follows existing patterns.

3. **Designs the technical solution** — Produces a comprehensive Architecture doc covering backend and frontend.

4. **Submits for approval** — Runs in `plan` mode, so the team lead must approve the architecture before development begins.

## Architecture Document Format

The output includes:

- **Backend Endpoints** — HTTP method, path, request/response bodies, auth requirements
- **Database Entities** — New tables/columns, migration SQL
- **Services** — Business logic layer design
- **DTOs** — Request/Response objects
- **Frontend Components** — New pages, components, their props and state
- **Frontend Services** — API call functions following the project's existing pattern
- **Frontend Types** — TypeScript interfaces
- **Routes** — New routes under the route prefix
- **API Contracts** — Full request/response examples for each endpoint
- **File Inventory** — Exact list of files to create or modify

## Config Sections Used

| Section | Purpose |
|---------|---------|
| App Identity | Context about the application |
| Tech Stack | Framework, DB, auth, API pattern details |
| Source Paths — Backend | Locates existing backend code for pattern study |
| Source Paths — Frontend | Locates existing frontend code for pattern study |
| Routing | Route prefix for new routes |

## Constraints

- Must work within the existing architecture — no stack changes
- All designs follow patterns found in the existing codebase
- The Architecture doc must be specific enough for the Scrum Master to create tasks and developers to implement without ambiguity

## Plan Approval

The architect is the only agent that runs with `mode: "plan"`. This means:
- The architect produces the plan
- The team lead reviews and either approves or requests changes
- If rejected, the architect revises based on feedback
- Development does not begin until architecture is approved

## Coordination

- Reads Feature Brief (from Product Owner) and UX Design (from UX Designer)
- The Scrum Master reads the Architecture doc to create tasks (Phase 4)
- Developers reference the Architecture doc while implementing

## When It Runs

- **Full workflow**: Phase 3
- **Retest mode**: Not spawned
