Single feature daytime preparation pipeline: interactive requirements → framework-native mockups → validation → human approval.

## Usage

```
/prepare-feature <feature-name>
```

Example: `/prepare-feature notification-center`

## Overview

This command runs the full daytime preparation conveyor for a single feature:
1. **Requirements** — product-owner gathers requirements interactively → FEATURE-BRIEF.md
2. **Mockup Design** — mockup-designer creates framework-native screen components
3. **Validation** — mockup-validator cross-checks mockups against requirements
4. **Human Approval** — you review the live mockups in the dev server, approve or request changes

Approved features get STATUS=approved and can be picked up by `/batch-features` for overnight development.

---

## Workflow

### Boot

Read `.claude/scrum-team-config.md`. If it does not exist, STOP:
"No scrum-team config found. Run `dodocs-workflow init` or create `.claude/scrum-team-config.md` from the template."

Extract:
- Feature Docs path (default: `docs/features/`)
- Source Paths — Frontend (for mockup compile path)
- Ports & URLs — Frontend Port
- Commands — Compile Frontend

Derive `<slug>` from `$ARGUMENTS`: lowercase, spaces → hyphens, strip special characters.
Example: "Notification Center" → `notification-center`

Create directory: `docs/features/<slug>/`
Write `draft` to `docs/features/<slug>/STATUS`

Create `docs/features/<slug>/PROGRESS.md` using the template at the bottom of this file.

---

### Phase D1 — Requirements (Interactive)

Spawn product-owner:
```
Spawn Task:
  subagent_type = "product-owner"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/product-owner.md and execute it.
    Feature name: <feature-name>
    Feature slug: <slug>
    AUTO_MODE=false

    The human is present and will answer your questions interactively.
    Write FEATURE-BRIEF.md to docs/features/<slug>/FEATURE-BRIEF.md
    After writing the brief, write 'requirements-ready' to docs/features/<slug>/STATUS
  """
```

Wait for the task to complete.

**Validate:** Read `docs/features/<slug>/FEATURE-BRIEF.md`. Must exist and contain:
- Non-empty Problem Statement (or Background)
- At least one User Story
- At least one Acceptance Criterion

If invalid: re-spawn product-owner with: "FEATURE-BRIEF.md is missing required sections. Regenerate with: problem statement, user stories (as a [role]...), and acceptance criteria." Wait and re-validate.

On valid: Write `requirements-ready` to `docs/features/<slug>/STATUS`.
Update PROGRESS.md: D1 → Done, D2 → In Progress.

---

### Phase D2 — Mockup Design

Spawn mockup-designer:
```
Spawn Task:
  subagent_type = "mockup-designer"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/mockup-designer.md and execute it.
    FEATURE_SLUG=<slug>
    Feature name: <feature-name>

    Read docs/features/<slug>/FEATURE-BRIEF.md for requirements.
    Create mockup components at src/mockups/<slug>/
    Write 'mockups-ready' to docs/features/<slug>/STATUS when done.
  """
```

Wait for the task to complete.

**Compile gate:** Run the Compile Frontend command from config. Capture output.

If compile errors:
```
Re-spawn mockup-designer:
  mode = "bypassPermissions"
  prompt = """
    Read ~/.claude/agents/mockup-designer.md.
    FEATURE_SLUG=<slug>

    The mockup files you created have compile errors. Fix them:

    <compile error output>

    Do not change the component logic — only fix compile/type errors.
    Re-run compile after fixing to confirm clean build.
  """
```
Wait, re-run compile. If still failing after 2 attempts: print error output and ask user to fix manually, then continue when ready.

On clean compile: update PROGRESS.md: D2 → Done, D3 → In Progress.

---

### Phase D3 — Validation

Spawn mockup-validator:
```
Spawn Task:
  subagent_type = "mockup-validator"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/mockup-validator.md and execute it.
    FEATURE_SLUG=<slug>
    Feature name: <feature-name>

    Validate src/mockups/<slug>/ against docs/features/<slug>/FEATURE-BRIEF.md
    Write results to docs/features/<slug>/MOCKUP-VALIDATION.md
  """
```

Wait for the task to complete.

Read `docs/features/<slug>/MOCKUP-VALIDATION.md`. Check overall result.

**If PASS:** update PROGRESS.md: D3 → Done. Go to Phase D4.

**If FAIL:** go to Phase D3.5.

---

### Phase D3.5 — Correction Loop (on validation FAIL)

Read and print the Issues section from MOCKUP-VALIDATION.md.

Ask user:
```
AskUserQuestion:
  "Mockup validation failed with N critical issues (listed above). How would you like to proceed?"
  Options:
    - "Fix automatically" — re-run mockup-designer with the issue list
    - "I'll review files first" — show me the file paths, I'll fix and continue
    - "Override — approve as-is" — skip validation, proceed to human review
```

**If "Fix automatically":**
Re-spawn mockup-designer with:
```
prompt = """
  Read ~/.claude/agents/mockup-designer.md.
  FEATURE_SLUG=<slug>

  The mockup validation failed. Fix these critical issues:

  <paste critical issues from MOCKUP-VALIDATION.md>

  After fixing, the validator will re-run automatically.
"""
```
Wait, re-run compile gate, re-run validator (Phase D3). Loop up to 3 times.
If still failing after 3 loops: fall through to manual review option.

**If "I'll review files first":**
Print:
```
Mockup files: src/mockups/<slug>/
Feature brief: docs/features/<slug>/FEATURE-BRIEF.md
Validation report: docs/features/<slug>/MOCKUP-VALIDATION.md

Make your changes, then tell me to "continue" when ready.
```
Wait for user "continue" message → re-run validator (Phase D3). Loop as needed.

**If "Override — approve as-is":**
Print: "Validation overridden by user. Proceeding to human review."
Update PROGRESS.md: D3 → Overridden. Go to Phase D4.

---

### Phase D4 — Human Review

Print:
```
Mockups are ready for review.

Start the dev server if not already running:
  npm run dev
  — or —
  make dev-frontend

Then visit:
  http://localhost:<Frontend Port>/mockups/<slug>

Source files: src/mockups/<slug>/
  - index.tsx          — navigation hub (all screens)
  - US01*.tsx          — screen for user story 01
  - US02*.tsx          — screen for user story 02
  (etc.)

Switch between screens using the navigation buttons at the top.
Toggle between states (default/empty/loading/error) using the yellow buttons in each screen.
```

Update PROGRESS.md: D4 → In Progress.

Ask user:
```
AskUserQuestion:
  "How do the mockups look?"
  Options:
    - "Approve — looks good, ready for development"
    - "Request changes — I'll describe what to fix"
    - "Reject — start over with requirements"
```

**If "Approve":**
Write `approved` to `docs/features/<slug>/STATUS`.
Update PROGRESS.md: D4 → Done, all daytime phases complete.
Print:
```
Feature '<slug>' approved and queued for development.

Run /batch-features when ready to start overnight development.
Only approved features will be picked up by batch-features.
```

**If "Request changes":**
Ask user to describe the changes needed (plain text follow-up).
Re-spawn mockup-designer with:
```
prompt = """
  Read ~/.claude/agents/mockup-designer.md.
  FEATURE_SLUG=<slug>

  The human has reviewed the mockups and requested changes:

  <user's change description>

  Update the mockup components at src/mockups/<slug>/ accordingly.
  Follow the same patterns — use real project components, keep state toggles.
"""
```
Wait, re-run compile gate, re-run validator (Phase D3). Then return to Phase D4.

**If "Reject":**
Write `draft` to `docs/features/<slug>/STATUS`.
Update PROGRESS.md: D1–D4 → Reset.

Ask user:
```
AskUserQuestion:
  "Feature rejected. What would you like to do?"
  Options:
    - "Start fresh — gather new requirements for this feature"
    - "Abandon this feature entirely"
```

If "Start fresh": go back to Phase D1.
If "Abandon": print "Feature '<slug>' abandoned. Folder kept at docs/features/<slug>/ for reference."

---

## PROGRESS.md Template

```markdown
# Progress: <feature-name>

## Current Phase: D1 — Requirements

## Daytime Preparation
| Phase | Status | Agent |
|-------|--------|-------|
| D1: Requirements | In Progress | product-owner |
| D2: Mockup Design | Pending | mockup-designer |
| D3: Mockup Validation | Pending | mockup-validator |
| D4: Human Approval | Pending | — |

## Artifacts
| File | Status | Author |
|------|--------|--------|
| FEATURE-BRIEF.md | Pending | product-owner |
| src/mockups/<slug>/ | Pending | mockup-designer |
| MOCKUP-VALIDATION.md | Pending | mockup-validator |
| UX-DESIGN.md | Pending | ux-designer |
| ARCHITECTURE.md | Pending | architect |

## Nighttime Development Phases
| Phase | Status |
|-------|--------|
| Phase 1: Requirements + UX Research | Pending |
| Phase 2: UX Design + Architecture | Pending |
| Phase 3: Task Breakdown + Git Setup | Pending |
| Phase 4: Build + Test | Pending |
| Phase 5: Integration Verification | Pending |
| Phase 6: Ship | Pending |

## Timeline
- [timestamp] prepare-feature: Feature folder created, STATUS=draft
```

The feature to prepare: $ARGUMENTS
