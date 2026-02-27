Make targeted changes to an existing feature area. Points at a feature that already has docs (FEATURE-BRIEF.md, ARCHITECTURE.md, UX-DESIGN.md), describes what to change, and runs the full scrum-team on the delta only — without losing the baseline context.

## Usage

```
/change-request <area-slug>
```

Example: `/change-request billing-dashboard`

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent spawned via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

Spawn all agents automatically as their phase begins — do NOT ask the user for permission to spawn any agent.

---

## Workflow

### Boot

**Step 1 — Read config:**
Read `.claude/scrum-team-config.md` using the Read tool.
If the file does not exist, STOP immediately and tell the user:
"No scrum-team config found for this project. Run `dodocs-workflow init` or copy the template from `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md` and fill in the values for this project."
Extract: Feature Docs path (default: `docs/features/`).

**Step 2 — Parse arguments:**
Parse `$ARGUMENTS` as `AREA_SLUG` verbatim — do NOT re-slug or transform it.
If `$ARGUMENTS` is empty → print usage:
```
Usage: /change-request <area-slug>
Example: /change-request billing-dashboard

Run /prepare-feature <area-slug> first if the feature docs don't exist yet.
```
Then STOP.

---

### Phase 1 — Validate Area

Check that `docs/features/<AREA_SLUG>/` directory exists.
Check that `docs/features/<AREA_SLUG>/FEATURE-BRIEF.md` exists.

**If directory missing:**
List all subdirectories under `docs/features/` and print:
```
Area '<AREA_SLUG>' not found under docs/features/.

Available areas:
  - <area-1>
  - <area-2>
  ...

Run /change-request <one-of-the-above> to target an existing area.
```
Then STOP.

**If FEATURE-BRIEF.md missing:**
Print:
```
Area '<AREA_SLUG>' exists but has no FEATURE-BRIEF.md.
Run /prepare-feature <AREA_SLUG> first to create the feature documentation,
then come back to /change-request <AREA_SLUG>.
```
Then STOP.

---

### Phase 2 — Read Context

Read all files that exist in `docs/features/<AREA_SLUG>/`:
- `FEATURE-BRIEF.md`
- `ARCHITECTURE.md` (if present)
- `UX-DESIGN.md` (if present)
- `PROGRESS.md` (if present)
- `STATUS` (if present)

Print a context summary box:
```
+-----------------------------------------------------------------+
|  Area: <AREA_SLUG>
|  Status: <value from STATUS file, or "unknown">
|  Docs present: FEATURE-BRIEF [Y]  ARCHITECTURE [Y/N]  UX-DESIGN [Y/N]
|
|  Problem Statement (excerpt):
|  <first paragraph of the Problem Statement from FEATURE-BRIEF.md>
+-----------------------------------------------------------------+
```

---

### Phase 3 — Change Intake

Use `AskUserQuestion` to ask:
"What changes would you like to make to `<AREA_SLUG>`?"
(free-text, no predefined chips)

Store the answer as `USER_CHANGE_DESCRIPTION`.

Then confirm with a follow-up `AskUserQuestion`:
"You described: **<USER_CHANGE_DESCRIPTION>**

Is this correct, or would you like to refine your description?"
Options:
- "Proceed with this description"
- "Let me refine it"

If "Refine" → ask again for the new description, loop back to confirm. Repeat until "Proceed".

---

### Phase 4 — Derive CR Slug

Derive `CR_SLUG` from the confirmed description:
- Start with `<AREA_SLUG>-`
- Take 2–4 meaningful words from `USER_CHANGE_DESCRIPTION`
- Strip stop words: a, an, the, for, to, of, in, on, with, and, or, by, from, that, this, is, are, be, it
- Lowercase, spaces → hyphens, strip non-alphanumeric characters
- Truncate total slug to max 50 characters

Examples:
- `billing-dashboard` + "add CSV export for invoices" → `billing-dashboard-add-csv-export`
- `user-settings` + "allow changing email address" → `user-settings-change-email-address`
- `notifications` + "add push notifications via Firebase" → `notifications-add-push-firebase`

Create directory: `docs/features/<CR_SLUG>/`
Write `draft` to `docs/features/<CR_SLUG>/STATUS`
Create `docs/features/<CR_SLUG>/PROGRESS.md` with this content:
```markdown
# Progress: <CR_SLUG>

## Change Request
This is a change request targeting area: <AREA_SLUG>
Description: <USER_CHANGE_DESCRIPTION>

## Current Phase
Phase CR1 — Change Intake

## Phase Status

| Phase | Status | Agent(s) |
|-------|--------|----------|
| CR1: Change Intake | In Progress | product-owner |
| CR2: Delta Architecture + UX | Pending | architect, ux-designer |
| CR3: Task Breakdown | Pending | scrum-master |
| CR4: Build + Test | Pending | all |
| CR5: Integration Verification | Pending | — |
| CR6: Ship | Pending | — |

## Artifacts

| Document | Status | Author |
|----------|--------|--------|
| CHANGE-REQUEST.md | Pending | product-owner |
| FEATURE-BRIEF.md (delta) | Pending | product-owner |
| UX-DESIGN.md (delta) | Pending | ux-designer |
| ARCHITECTURE.md (delta) | Pending | architect |

## Baseline Reference

| Document | Location |
|----------|----------|
| Original FEATURE-BRIEF.md | docs/features/<AREA_SLUG>/FEATURE-BRIEF.md |
| Original ARCHITECTURE.md | docs/features/<AREA_SLUG>/ARCHITECTURE.md |
| Original UX-DESIGN.md | docs/features/<AREA_SLUG>/UX-DESIGN.md |

## Timeline
- [start] change-request: CR folder created for area <AREA_SLUG>, STATUS=draft
```

---

### Phase 5 — Product-Owner (Change Mode)

Spawn `product-owner` agent with `mode: "bypassPermissions"`:

```
Spawn Task:
  subagent_type = "product-owner"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/product-owner.md and execute it.

    You are operating in CHANGE REQUEST MODE for an existing feature area.

    AREA SLUG (baseline): <AREA_SLUG>
    CR SLUG (this change request): <CR_SLUG>
    CHANGE DESCRIPTION: <USER_CHANGE_DESCRIPTION>

    STEP 1 — Read the baseline documents:
      - docs/features/<AREA_SLUG>/FEATURE-BRIEF.md
      - docs/features/<AREA_SLUG>/ARCHITECTURE.md  (if it exists)
      - docs/features/<AREA_SLUG>/UX-DESIGN.md     (if it exists)

    STEP 2 — Ask ONLY incremental clarifying questions about the change.
    Do NOT re-ask anything that is already covered by the baseline documents.
    Focus your questions solely on what is new, different, or ambiguous about
    the requested change. 2-4 questions maximum.

    STEP 3 — Write TWO files to docs/features/<CR_SLUG>/:

    File 1: CHANGE-REQUEST.md
    Sections (in order):
      ## Original Area Summary
        One-paragraph summary of what the baseline feature does.
      ## Change Description
        The user's change description verbatim, plus any clarifications.
      ## Problem Being Solved
        Why this change is needed.
      ## What Stays the Same
        Parts of the baseline feature that are NOT being changed.
      ## What Changes
        Specific modifications: UI changes, new endpoints, schema changes, etc.
      ## New Acceptance Criteria
        Criteria that are NEW or MODIFIED (delta only — do not repeat unchanged criteria).
      ## Impact on Existing Functionality
        Potential regressions, migration needs, or UX disruptions.
      ## Dependencies
        Depends On: <AREA_SLUG>

    File 2: FEATURE-BRIEF.md
    Standard FEATURE-BRIEF.md format but scoped to the DELTA only.
    Required sections:
      - Problem Statement (explain the gap this change fills)
      - User Stories (new/modified stories only)
      - Acceptance Criteria (new/modified criteria only)
      - Out of Scope: see docs/features/<AREA_SLUG>/FEATURE-BRIEF.md for baseline
      - Depends On: <AREA_SLUG>

    After writing both files, write 'cr-ready' to docs/features/<CR_SLUG>/STATUS.
  """
```

Wait for the task to complete.

**Validate:** Read both files.
- `docs/features/<CR_SLUG>/CHANGE-REQUEST.md` — must exist and contain all 8 sections
- `docs/features/<CR_SLUG>/FEATURE-BRIEF.md` — must exist, must contain Problem Statement and at least one User Story

If either file is missing or incomplete: re-spawn `product-owner` with `bypassPermissions` appending:
"CHANGE-REQUEST.md or FEATURE-BRIEF.md is incomplete or missing. Regenerate both files with all required sections as specified in your prompt."
Wait and re-validate. Retry up to 2 times total.

---

### Phase 6 — Present and Confirm

Read and print the full content of `docs/features/<CR_SLUG>/CHANGE-REQUEST.md`.

Then use `AskUserQuestion`:
"The change request document is ready (printed above). How would you like to proceed?"
Options:
1. "Launch scrum-team — implement now"
2. "Save for later — I'll run `/scrum-team <CR_SLUG>` manually"
3. "Something is wrong — revise"

**If "Save for later":**
Print:
```
Change request saved. Files created:
  docs/features/<CR_SLUG>/CHANGE-REQUEST.md
  docs/features/<CR_SLUG>/FEATURE-BRIEF.md
  docs/features/<CR_SLUG>/STATUS  (cr-ready)

When ready to implement, run:
  /scrum-team <CR_SLUG>

The scrum-team will use these docs as its starting point.
```
Then STOP.

**If "Revise":**
Use `AskUserQuestion` to ask: "What should be revised in the change request?"
Re-spawn `product-owner` with `bypassPermissions`, appending the revision feedback to the original prompt:
"The user has reviewed CHANGE-REQUEST.md and requested revisions: <revision feedback>. Update both CHANGE-REQUEST.md and FEATURE-BRIEF.md accordingly."
Wait for completion. Then loop back to Phase 6 (re-read and re-present CHANGE-REQUEST.md).

**If "Launch":**
Proceed to Phase 7.

---

### Phase 7 — Scrum-Team Launch

Spawn a `general-purpose` agent with `mode: "bypassPermissions"` to run the scrum-team workflow:

```
Spawn Task:
  subagent_type = "general-purpose"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/commands/scrum-team.md and execute it fully.

    $ARGUMENTS = <CR_SLUG>

    CHANGE REQUEST CONTEXT — inject these instructions into each phase:

    PHASE 1 OVERRIDE (product-owner):
      - Read docs/features/<AREA_SLUG>/FEATURE-BRIEF.md as the baseline context
      - Read docs/features/<CR_SLUG>/CHANGE-REQUEST.md for the change description
      - Treat docs/features/<CR_SLUG>/FEATURE-BRIEF.md as PRE-APPROVED — do NOT re-ask the user for requirements that are already documented there
      - Your role is to clarify implementation details only, not to re-gather baseline requirements

    PHASE 2 OVERRIDE (architect):
      - Read docs/features/<AREA_SLUG>/ARCHITECTURE.md as the baseline architecture
      - Produce a DELTA ARCHITECTURE.md at docs/features/<CR_SLUG>/ARCHITECTURE.md
      - Structure it as: sections that are UNCHANGED (reference only), sections that are MODIFIED (show diff), and sections that are NEW
      - Do NOT reproduce the full baseline architecture verbatim

    PHASE 2 OVERRIDE (ux-designer):
      - Read docs/features/<AREA_SLUG>/UX-DESIGN.md as the baseline UX
      - Produce a DELTA UX-DESIGN.md at docs/features/<CR_SLUG>/UX-DESIGN.md
      - Document only flows and states that CHANGE or are NEW
      - Reference baseline flows by name rather than reproducing them

    PHASES 3-6: Run normally per the scrum-team workflow.

    Baseline area: <AREA_SLUG>
    CR docs: docs/features/<CR_SLUG>/
  """
```

After spawning, report to the user:
```
Scrum-team launched for change request '<CR_SLUG>'.
Baseline area: <AREA_SLUG>

The team will implement only the delta described in CHANGE-REQUEST.md,
using the original <AREA_SLUG> docs as baseline context.

Feature branch: feature/<CR_SLUG>
```

---

The area to apply a change request to: $ARGUMENTS
