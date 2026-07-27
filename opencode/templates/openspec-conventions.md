# OpenSpec Conventions for dodocs-workflow

This document is the single source of truth for how dodocs-workflow agents and commands
use OpenSpec. Agents are pointed here by their boot blocks — read it before reading or
writing any requirements artifact.

## The CLI

The workflow depends on the OpenSpec terminal CLI only — never on `/opsx:*` slash
commands or OpenSpec-installed skills (that surface churns between releases).

- **Invocation**: read the **OpenSpec CLI** line from `.opencode/scrum-team-config.md`
  (`## OpenSpec` section). If the line is absent, fall back to the pinned default:
  `npx -y @fission-ai/openspec@1.6.0`
- The npm package is `@fission-ai/openspec` (bin name: `openspec`). The bare `openspec`
  npm package is an unrelated placeholder — never install it.
- Requires Node.js >= 20.

Commands you will use:

| Command | Purpose |
|---|---|
| `openspec init --tools none [path]` | Scaffold `openspec/config.yaml` non-interactively (no AI-tool files) |
| `openspec validate <change> --strict` | Validate one change (exit 0 = valid) |
| `openspec validate --all --strict --json` | Validate everything, machine-readable |
| `openspec list --json` | List active changes |
| `openspec list --specs --json` | List spec domains |
| `openspec show <change|spec> --json` | Dump one item |
| `openspec archive <change> --yes` | Merge delta specs into `openspec/specs/` and move the change to `changes/archive/<DATE>-<name>/` |
| `openspec archive <change> --yes --skip-specs` | Archive a tooling/doc-only change without touching specs |

Facts about `archive` (verified against v1.6.0):
- It refuses to archive until every checkbox in the change's `tasks.md` is `[x]`.
- It creates missing `openspec/specs/<domain>/spec.md` files with `Purpose: TBD` —
  fill the Purpose in the same commit.
- **Archive only after the feature's code is merged to main, never on a feature branch.**
  Archiving early would fold requirements into the living specs before the code exists,
  and parallel branches touching the same domain would conflict.

## Directory layout — the split rule

Requirements truth and build-process artifacts live in different trees. This split is
load-bearing: `openspec archive` RELOCATES the change folder, so anything stored there
that isn't one of OpenSpec's own artifacts would vanish from its expected path mid-build.

```
openspec/
├── config.yaml                    # schema + project context for artifact authoring
├── project.md                     # optional: project notes, legacy slug → domain map
├── specs/<domain>/spec.md         # LIVING SPECS — current behavior, per capability.
│                                  # Updated ONLY via `openspec archive`. Never edit
│                                  # directly except to fill a TBD Purpose.
└── changes/
    ├── <slug>/                    # ONE IN-FLIGHT CHANGE == one dodocs feature slug
    │   ├── proposal.md            # why / what changes / impact  (replaces FEATURE-BRIEF.md)
    │   ├── design.md              # technical design             (replaces ARCHITECTURE.md)
    │   ├── tasks.md               # implementation checklist     (canonical task breakdown)
    │   └── specs/<domain>/spec.md # DELTA specs (ADDED/MODIFIED/REMOVED requirements)
    └── archive/<DATE>-<slug>/     # completed changes — the immutable audit trail

docs/features/<slug>/              # BUILD-PROCESS artifacts (never touched by archive)
    ├── STATUS                     # draft → requirements-ready → mockups-ready → approved → completed
    ├── PROGRESS.md                # live dashboard, phase gates
    ├── UX-DESIGN.md               # user flows (reads proposal + deltas)
    ├── mockups/                   # framework-native mockups
    ├── MOCKUP-VALIDATION.md
    ├── REQ-UX-REVIEW.md           # requirements critic outputs
    ├── REQ-BUSINESS-REVIEW.md
    ├── REQUIREMENTS-VALIDATION.md
    └── QUALITY-METRICS.md
```

Rules:
- **Identity**: the dodocs feature `<slug>` IS the OpenSpec change name. `openspec/changes/<slug>/`
  and `docs/features/<slug>/` always pair.
- Only OpenSpec's four artifact kinds (proposal, design, tasks, delta specs) go inside
  `openspec/changes/<slug>/`. Everything else goes in `docs/features/<slug>/`.
- Cross-links: `proposal.md` ends with a `## Build Artifacts` section linking to
  `docs/features/<slug>/`; `PROGRESS.md` links to the change folder (updated to the
  archive path at ship time).

## Where do I read requirements for slug X?

1. `openspec/changes/<slug>/` exists → it's in flight: read `proposal.md` + every
   `specs/<domain>/spec.md` delta under it (plus `design.md` / `tasks.md` if present).
2. Otherwise search `openspec/changes/archive/*-<slug>/` → it shipped: the archived
   folder is the historical record; **current behavior** is `openspec/specs/<domain>/spec.md`.
3. Otherwise, legacy pre-OpenSpec feature: `docs/features/<slug>/FEATURE-BRIEF.md`
   (read-only history — never write new content there).

## Artifact formats

`openspec validate --strict` mechanically enforces these. Get them exactly right.

### proposal.md

```markdown
## Why

<1–3 paragraphs: the problem, who has it, why now>

## What Changes

- <bullet list of behavior changes, user-visible first>

## Impact

- Affected specs: <domain>, <domain>
- Affected code: <areas/paths>

## Out of Scope

- <explicit non-goals>

## Assumptions

- <decisions inferred without user input — AUTO_MODE runs must fill this>

## Build Artifacts

- Process docs: `docs/features/<slug>/` (STATUS, PROGRESS.md, UX-DESIGN.md, mockups/)
```

### Delta spec — `openspec/changes/<slug>/specs/<domain>/spec.md`

Delta specs contain ONLY what changes, under these exact headers:

```markdown
## ADDED Requirements

### Requirement: <name>

The system SHALL <observable behavior>.

#### Scenario: <case name>

- GIVEN <precondition>
- WHEN <action>
- THEN <outcome>

## MODIFIED Requirements

### Requirement: <exact name of the existing requirement>

<the full modified requirement text + ALL of its scenarios, restated>

## REMOVED Requirements

### Requirement: <exact name of the existing requirement>

**Reason**: <why it is removed>
```

Format rules (strict-validation enforced):
- Requirement text uses RFC-2119 keywords: SHALL / MUST (mandatory), SHOULD (recommended), MAY (optional).
- Every `### Requirement:` needs at least one `#### Scenario:` (GIVEN/WHEN/THEN bullets).
- Requirements state WHAT (observable behavior), never HOW (implementation).
- A `MODIFIED` requirement's name must exactly match the name in the living spec.
- Omit any of the three sections if empty.
- User stories map to Requirements; acceptance criteria and edge cases map to Scenarios
  (one scenario per AC / edge case — this is what makes them testable).

### design.md

Technical design for the change. Mandatory sections (same content the legacy
ARCHITECTURE.md carried — downstream automation parses the File Inventory):

```markdown
## Context

<constraints, existing patterns to follow, integration points>

## Backend

### Endpoints        <method, path, request/response DTOs>
### Entities         <new/changed entities + migrations>
### Services         <service-layer changes>

## Frontend

### Components       <new/changed components, which existing ones to reuse>
### Routes           <new routes + navigation entry points>

## API Contracts

<request/response shapes shared between backend and frontend tasks>

## File Inventory

### New Files        <full paths>
### Modified Files   <full paths>
```

### tasks.md

The canonical implementation checklist. Developers tick items as they commit;
`openspec archive` refuses to run while any box is unchecked.

```markdown
## 1. <Group — usually one user story / requirement>

- [ ] 1.1 <task — small, atomic, one commit>
- [ ] 1.2 <task>

## 2. <Group>

- [ ] 2.1 <task>
```

## Spec domains

- Domains are per-capability (e.g. `auth`, `billing`, `notifications`), NOT per-feature.
  A feature usually touches 1–3 domains.
- The domain list lives in `.opencode/scrum-team-config.md` (`## OpenSpec` → Spec Domains)
  and grows over time. Check `openspec list --specs` and the config before inventing a
  new domain; prefer extending an existing one.
- New domain names: short kebab-case nouns for capabilities, not slugs of features.

## Validation gates

- After authoring or editing any change artifact:
  `<openspec-cli> validate <slug> --strict` must exit 0. On failure, fix and re-run
  (max 3 attempts, then report the validator output).
- Ship flow (post-merge, on main): `<openspec-cli> archive <slug> --yes`, commit the
  resulting spec updates + archive move, fill any `TBD` Purpose lines.
