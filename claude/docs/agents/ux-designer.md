# UX Designer

The UX Designer creates user flows that feel native to the existing application. They work in two phases: first researching existing UI patterns, then combining that research with the Feature Brief to produce a UX Design document.

## Overview

| Property | Value |
|----------|-------|
| **Agent file** | `agents/ux-designer.md` |
| **Model** | opus |
| **Active in phases** | Phase 1 (research), Phase 2 (design) |
| **Tools** | Read, Grep, Glob, Write, Bash |
| **Outputs** | `docs/features/<feature>/UX-DESIGN.md` |

## What It Does

### Phase 1: Early Pattern Research (parallel with Product Owner)

Starts immediately — doesn't wait for the Feature Brief:

- Reads existing pages in the workspace pages directory
- Reads reusable components for patterns
- Catalogs: navigation patterns, form patterns, table patterns, modal patterns, empty states, error states
- Builds a mental model of the app's UI conventions

### Phase 2: UX Design (after Feature Brief is ready)

- Reads the completed `FEATURE-BRIEF.md`
- Combines pattern research with feature requirements
- Designs user flows that feel consistent with the existing UI
- Produces the UX Design document

## UX Design Format

The output document includes:

- **Existing Patterns Referenced** — Which existing pages/components were used as reference
- **Navigation & Entry Points** — How users access the feature (sidebar items, buttons, routes)
- **User Flows** — Step-by-step journeys with decision points
- **Page/Component Layouts** — Description of what each screen contains
- **State Handling** — Empty states, loading states, error states, success states
- **Form Interactions** — Validation rules, error messages, submit behavior
- **Responsive Behavior** — Desktop vs mobile considerations
- **Accessibility** — Keyboard navigation, screen reader support

## Config Sections Used

| Section | Purpose |
|---------|---------|
| App Identity | Understands what the app does |
| Source Paths — Frontend (Pages, Workspace Pages, Components) | Reads existing UI for pattern research |
| Routing (Route Prefix) | Knows the route prefix for navigation design |

## Human Checkpoint

After the UX Design is produced, the team lead presents it to the user for approval:

> "Do these user flows look right? Any changes before we proceed to architecture?"

The user can request revisions before the workflow moves to Phase 3.

## Coordination

- Starts pattern research in **parallel** with Product Owner (Phase 1)
- Waits for the Feature Brief before producing the UX Design (Phase 2)
- The architect reads the UX Design to begin Phase 3
- After completing the UX Design, updates `PROGRESS.md`: marks the UX-DESIGN.md artifact as Done and adds a timeline entry

## When It Runs

- **Full workflow**: Phase 1 (research) + Phase 2 (design)
- **Retest mode**: Not spawned
