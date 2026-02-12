# Product Owner

The Product Owner is the first point of contact for new features. They gather requirements from the user through interactive conversation and produce a structured Feature Brief that drives all downstream work.

## Overview

| Property | Value |
|----------|-------|
| **Agent file** | `agents/product-owner.md` |
| **Model** | opus |
| **Active in phases** | Phase 1 |
| **Tools** | Read, Grep, Glob, Write, Bash |
| **Outputs** | `docs/features/<feature>/FEATURE-BRIEF.md` |

## What It Does

1. **Reads existing documentation** — Studies `SPECIFICATION.md` and `docs/specs/*.md` to understand what's already built. This prevents duplicate features and ensures the new feature fits the existing product.

2. **Interviews the user** — Asks detailed questions via the team lead:
   - What problem does the feature solve?
   - Who are the target users?
   - What are the acceptance criteria?
   - What edge cases should be handled?
   - How does it interact with existing features?

3. **Validates fit** — Confirms the feature doesn't conflict with existing functionality and identifies dependencies on current systems.

4. **Produces the Feature Brief** — Writes a comprehensive document that becomes the source of truth for UX design and architecture.

## Feature Brief Format

The output document includes:

- **Problem Statement** — What user problem this solves
- **Target Users** — Who will use this feature
- **User Stories** — Structured as "As a [role], I want [action], so that [benefit]"
- **Acceptance Criteria** — Clear, testable criteria for "done"
- **Edge Cases** — Known edge cases and how to handle them
- **Out of Scope** — What the feature explicitly does NOT include
- **Dependencies** — What existing features/systems this depends on
- **Impact on Existing Features** — Any changes needed to current functionality

## Config Sections Used

| Section | Purpose |
|---------|---------|
| App Identity | Understands the app name and what it does |
| Feature Docs path | Knows where to write the Feature Brief |

## Coordination

- Runs **in parallel** with the UX designer's early research phase
- Sends a message to the team lead when the brief is complete
- The UX designer reads the brief to begin Phase 2 (UX Design)

## When It Runs

- **Full workflow**: Phase 1 (always)
- **Retest mode**: Not spawned
