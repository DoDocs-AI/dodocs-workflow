Make targeted changes to an existing feature area. Points at a feature that already has docs (FEATURE-BRIEF.md, ARCHITECTURE.md, UX-DESIGN.md). Product first decides whether the request is a CHANGE to that feature or a genuinely NEW feature. When it is a change, the existing feature's docs, code, and tests are updated IN PLACE — no new feature brief, no sibling folder.

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

## Core Principle — Change In Place

A change request modifies the **existing** feature. Do NOT create a new `<area-slug>-<change>` folder and do NOT write a fresh delta FEATURE-BRIEF. Instead:
- **Edit** `docs/features/<AREA_SLUG>/FEATURE-BRIEF.md`, `ARCHITECTURE.md`, and `UX-DESIGN.md` in place.
- **Append** a dated entry to `docs/features/<AREA_SLUG>/CHANGELOG.md` (the audit trail).
- **Modify** the current feature's code and tests in place — never scaffold a parallel implementation.

A new folder/brief is only ever created if product decides the request is actually a NEW feature, in which case the user is handed off to `/scrum-team`.

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
- `CHANGELOG.md` (if present)
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

**Derive `CHANGE_SLUG`** (used later for the branch name and for a new-feature suggestion):
- Take 2–4 meaningful words from `USER_CHANGE_DESCRIPTION`
- Strip stop words: a, an, the, for, to, of, in, on, with, and, or, by, from, that, this, is, are, be, it
- Lowercase, spaces → hyphens, strip non-alphanumeric characters
- Examples: "add CSV export for invoices" → `add-csv-export`; "allow changing email address" → `change-email-address`

---

### Phase 4 — Product Decision Gate (Change vs New Feature)

**This is the "product checks first" step.** Before touching any docs, product decides whether this request is a change to the existing feature or is really a new feature.

Spawn `product-owner` agent with `mode: "bypassPermissions"` in CLASSIFICATION MODE:

```
Spawn Task:
  subagent_type = "product-owner"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/product-owner.md and execute it.

    You are operating in CLASSIFICATION MODE. Do NOT write or edit any files.
    Do NOT ask the user any questions. Return your verdict as text only.

    AREA SLUG (existing feature): <AREA_SLUG>
    CHANGE DESCRIPTION: <USER_CHANGE_DESCRIPTION>

    STEP 1 — Read the existing documents:
      - docs/features/<AREA_SLUG>/FEATURE-BRIEF.md
      - docs/features/<AREA_SLUG>/ARCHITECTURE.md  (if it exists)
      - docs/features/<AREA_SLUG>/UX-DESIGN.md     (if it exists)

    STEP 2 — Classify the request:
      - CHANGE = it modifies or extends the existing feature's user stories,
        screens, endpoints, or data model, and fits inside this feature's
        current problem statement.
      - NEW_FEATURE = it introduces a distinct user journey, an independent
        data model, or a separate module only loosely related to this area.

    STEP 3 — Return EXACTLY this format as your final message (no files):
      VERDICT: CHANGE            (or)   VERDICT: NEW_FEATURE
      REASONING: <1-2 sentences>
      SUGGESTED_NAME: <only if NEW_FEATURE — a short human feature name>
  """
```

Wait for the task to complete. Parse `VERDICT`, `REASONING`, and (if present) `SUGGESTED_NAME` from the agent's returned text.

**Present the verdict to the user** with `AskUserQuestion`:

**If VERDICT = CHANGE:**
"Product's assessment: this is a **change** to `<AREA_SLUG>`.
Reason: <REASONING>

How would you like to proceed?"
Options:
1. "Proceed as a change to `<AREA_SLUG>`" (default)
2. "Actually make this a new feature"

- If option 1 → continue to Phase 5.
- If option 2 → treat as NEW_FEATURE handoff (see below).

**If VERDICT = NEW_FEATURE:**
"Product's assessment: this looks like a **new feature**, not a change to `<AREA_SLUG>`.
Reason: <REASONING>

How would you like to proceed?"
Options:
1. "Create as a new feature via `/scrum-team`" (default)
2. "No — treat it as a change to `<AREA_SLUG>` anyway"

- If option 1 → **NEW_FEATURE handoff**: print and STOP (do not auto-run):
  ```
  This is better built as a new feature. Run:

    /scrum-team "<SUGGESTED_NAME, or a name derived from the change>"

  That will stand up a fresh feature with its own docs at
  docs/features/<suggested-slug>/, leaving <AREA_SLUG> untouched.
  ```
- If option 2 → continue to Phase 5 (proceed as a change).

---

### Phase 5 — Update Product Docs In Place

Spawn `product-owner` agent with `mode: "bypassPermissions"` in CHANGE-UPDATE MODE:

```
Spawn Task:
  subagent_type = "product-owner"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/product-owner.md and execute it.

    You are operating in CHANGE-UPDATE MODE for an existing feature area.
    You UPDATE the existing docs in place. Do NOT create a new folder and do
    NOT write a separate delta brief.

    AREA SLUG: <AREA_SLUG>
    CHANGE DESCRIPTION: <USER_CHANGE_DESCRIPTION>

    STEP 1 — Read the existing documents:
      - docs/features/<AREA_SLUG>/FEATURE-BRIEF.md
      - docs/features/<AREA_SLUG>/ARCHITECTURE.md  (if it exists)
      - docs/features/<AREA_SLUG>/UX-DESIGN.md     (if it exists)
      - docs/features/<AREA_SLUG>/CHANGELOG.md      (if it exists)

    STEP 2 — Ask ONLY incremental clarifying questions about the change
    (2-4 max). Do NOT re-gather requirements already covered by the existing
    FEATURE-BRIEF.md.

    STEP 3 — EDIT docs/features/<AREA_SLUG>/FEATURE-BRIEF.md IN PLACE.
      Use the Edit tool for targeted changes — do NOT rewrite the whole file.
      Fold the change into the existing sections:
        - Problem Statement: extend only if the change alters the problem
        - User Stories: add new stories, modify affected ones, keep the rest
        - Acceptance Criteria: add/modify only the criteria this change touches
        - Edge Cases: add any new edge cases the change introduces
      Everything not touched by the change must remain intact.

    STEP 4 — APPEND a dated entry to docs/features/<AREA_SLUG>/CHANGELOG.md
    (create the file with a `# Changelog` heading if it does not exist).
    Prepend the new entry directly under the heading, format:

      ## <YYYY-MM-DD> — <short change title>
      **Change:** <USER_CHANGE_DESCRIPTION>
      **What changed:** <bulleted summary of the brief/story/criteria edits>
      **Impact on existing functionality:** <regressions / migration / UX notes>

    Use the current date. If you cannot determine it, run `date +%F` via Bash.
  """
```

Wait for the task to complete.

**Validate:**
- `docs/features/<AREA_SLUG>/FEATURE-BRIEF.md` — still contains a Problem Statement and at least one User Story.
- `docs/features/<AREA_SLUG>/CHANGELOG.md` — exists and contains a new dated entry referencing this change.

If validation fails: re-spawn `product-owner` with `bypassPermissions`, appending:
"The in-place FEATURE-BRIEF.md edit or the CHANGELOG.md entry is missing or incomplete. Apply the edits and append the changelog entry as specified."
Wait and re-validate. Retry up to 2 times total.

---

### Phase 6 — Present and Confirm

Print a short summary of what changed in `FEATURE-BRIEF.md` and print the new `CHANGELOG.md` entry in full.

Then use `AskUserQuestion`:
"The feature docs for `<AREA_SLUG>` have been updated in place (summary above). How would you like to proceed?"
Options:
1. "Launch scrum-team — implement the change now"
2. "Save for later — I'll run `/change-request <AREA_SLUG>` again or `/scrum-team <AREA_SLUG>` manually"
3. "Something is wrong — revise"

**If "Save for later":**
Print:
```
Change saved. Updated in place:
  docs/features/<AREA_SLUG>/FEATURE-BRIEF.md
  docs/features/<AREA_SLUG>/CHANGELOG.md  (new entry)

When ready to implement, run:
  /scrum-team <AREA_SLUG>

The scrum-team will read the updated docs and modify the existing
code and tests for this feature.
```
Then STOP.

**If "Revise":**
Use `AskUserQuestion` to ask: "What should be revised?"
Re-spawn `product-owner` with `bypassPermissions`, appending the revision feedback:
"The user reviewed the updated docs and requested revisions: <revision feedback>. Update FEATURE-BRIEF.md in place and adjust the latest CHANGELOG.md entry accordingly."
Wait for completion. Then loop back to Phase 6.

**If "Launch":**
Proceed to Phase 7.

---

### Phase 7 — Scrum-Team Launch (In Place)

Spawn a `general-purpose` agent with `mode: "bypassPermissions"` to run the scrum-team workflow against the **existing** feature folder:

```
Spawn Task:
  subagent_type = "general-purpose"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/commands/scrum-team.md and execute it fully.

    $ARGUMENTS = <AREA_SLUG>

    This is a CHANGE to an existing feature. The docs already live at
    docs/features/<AREA_SLUG>/ and the FEATURE-BRIEF.md has ALREADY been
    updated to describe the change. Update everything IN PLACE — do not
    create any new feature folder.

    BRANCH OVERRIDE:
      - Use branch feature/<AREA_SLUG>-<CHANGE_SLUG> instead of
        feature/<AREA_SLUG>, so this change gets its own scoped PR.

    PHASE 1 OVERRIDE (product-owner):
      - docs/features/<AREA_SLUG>/FEATURE-BRIEF.md is ALREADY UPDATED and
        PRE-APPROVED. Do NOT regenerate, re-ask, or overwrite it.
      - Also read docs/features/<AREA_SLUG>/CHANGELOG.md (latest entry) to
        understand exactly what is changing.

    PHASE 2 OVERRIDE (architect):
      - EDIT docs/features/<AREA_SLUG>/ARCHITECTURE.md IN PLACE to reflect the
        change (targeted edits with the Edit tool — not a delta file, not a
        full rewrite). Leave unaffected sections intact.

    PHASE 2 OVERRIDE (ux-designer):
      - EDIT docs/features/<AREA_SLUG>/UX-DESIGN.md IN PLACE for the flows and
        states that change or are new. Leave unaffected flows intact.
      - Skip mockup regeneration unless the change adds or removes screens.

    PHASE 4 OVERRIDE (developers + QA):
      - Modify the existing feature's CODE and TESTS in place to implement the
        change. Do NOT scaffold a parallel implementation.
      - Update this feature's existing test cases to match the new behavior.

    PHASES 3, 5-6: Run normally per the scrum-team workflow.
  """
```

After spawning, report to the user:
```
Scrum-team launched for change to '<AREA_SLUG>'.

Docs, code, and tests for this feature are being updated IN PLACE.
Changelog entry: docs/features/<AREA_SLUG>/CHANGELOG.md

Feature branch: feature/<AREA_SLUG>-<CHANGE_SLUG>
```

---

The area to apply a change request to: $ARGUMENTS
