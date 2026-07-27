Make targeted changes to an existing feature area. Product first assesses the scope of the request, then the change is captured as an OpenSpec change — `openspec/changes/<change-slug>/` with MODIFIED/ADDED/REMOVED delta specs against the living specs in `openspec/specs/` — validated by the pinned CLI, and implemented by the scrum-team modifying the existing code and tests in place.

## Usage

```
/change-request <area-slug-or-domain>
```

Example: `/change-request billing-dashboard`

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent spawned via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

Spawn all agents automatically as their phase begins — do NOT ask the user for permission to spawn any agent.

---

## Core Principle — Delta Docs, In-Place Code

Requirements changes are captured as **deltas**, never by editing history:
- The living specs (`openspec/specs/<domain>/spec.md`) describe current behavior and are
  only updated by `openspec archive` after the change ships.
- Each change request gets its own change folder `openspec/changes/<CR_SLUG>/` with a
  proposal and `## MODIFIED / ADDED / REMOVED Requirements` delta specs. The archived
  change folder is the permanent audit trail (no separate CHANGELOG.md).
- The **code and tests** for the feature are modified IN PLACE — never scaffold a
  parallel implementation.

---

## Workflow

### Boot

**Step 1 — Read config:**
Read `.claude/scrum-team-config.md` using the Read tool.
If the file does not exist, STOP immediately and tell the user:
"No scrum-team config found for this project. Run `dodocs-workflow init` or copy the template from `~/.claude/scrum-team-config.template.md` to `.claude/scrum-team-config.md` and fill in the values for this project."
Extract: Feature Docs path (default: `docs/features/`) and the `## OpenSpec` section
(`<openspec-cli>` invocation, default `npx -y @fission-ai/openspec@1.6.0`; Spec Domains).

If `openspec/` does not exist in the project root, STOP:
"This project is not initialized for the OpenSpec pipeline. Run `dodocs-workflow init` (new project), or bootstrap `openspec/specs/` using the Claude Code `/spec-bootstrap` command or manually (project with existing features), first. To stay on the pre-OpenSpec workflow, pin v1.17.0: `curl -fsSL https://raw.githubusercontent.com/DoDocs-AI/dodocs-workflow/refs/tags/v1.17.0/install-opencode.sh | bash`"

**Step 2 — Parse arguments:**
Parse `$ARGUMENTS` as `AREA_SLUG` verbatim — do NOT re-slug or transform it.
If `$ARGUMENTS` is empty → print usage:
```
Usage: /change-request <area-slug-or-domain>
Example: /change-request billing-dashboard

The argument can be a shipped feature slug (openspec/changes/archive/*-<slug>/),
a spec domain (openspec/specs/<domain>/), or a legacy feature (docs/features/<slug>/).
```
Then STOP.

---

### Phase 1 — Resolve Area

Resolve `AREA_SLUG` against, in order:
1. A spec domain: `openspec/specs/<AREA_SLUG>/spec.md` exists
2. A shipped change: a folder matching `openspec/changes/archive/*-<AREA_SLUG>/` exists
3. An in-flight change: `openspec/changes/<AREA_SLUG>/` exists → STOP:
   "`<AREA_SLUG>` is still in flight (openspec/changes/<AREA_SLUG>/). Amend that change directly (edit its proposal/delta specs and re-run `<openspec-cli> validate <AREA_SLUG> --strict`) instead of opening a change request on top of it."
4. A legacy feature: `docs/features/<AREA_SLUG>/FEATURE-BRIEF.md` exists (pre-OpenSpec history)

Record which of these matched as `AREA_KIND` (domain | shipped | legacy) and derive
`AFFECTED_DOMAINS` candidates:
- domain → that domain
- shipped → domains listed in the archived change's `specs/` subfolders
- legacy → empty (product-owner will propose domains in Phase 4)

**If nothing matched:**
List spec domains (`<openspec-cli> list --specs`), archived change names, and
`docs/features/` subdirectories, then print:
```
Area '<AREA_SLUG>' not found.

Spec domains:      <list>
Shipped changes:   <list>
Legacy features:   <list>

Run /change-request <one-of-the-above>, or /prepare-feature <name> for a brand-new feature.
```
Then STOP.

---

### Phase 2 — Read Context

Read, as applicable to `AREA_KIND`:
- The living specs for each candidate domain: `openspec/specs/<domain>/spec.md`
- The archived change: `openspec/changes/archive/*-<AREA_SLUG>/proposal.md` (+ design.md if present)
- Legacy docs (read-only): `docs/features/<AREA_SLUG>/FEATURE-BRIEF.md`, `UX-DESIGN.md`
- Build artifacts if present: `docs/features/<AREA_SLUG>/STATUS`, `PROGRESS.md`

Print a context summary box:
```
+-----------------------------------------------------------------+
|  Area: <AREA_SLUG>   (kind: domain | shipped change | legacy)
|  Affected domains (candidate): <list or "to be determined">
|
|  Current behavior (excerpt from living specs / legacy brief):
|  <2-3 line excerpt>
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

**Derive `CHANGE_SLUG`:**
- Take 2–4 meaningful words from `USER_CHANGE_DESCRIPTION`
- Strip stop words: a, an, the, for, to, of, in, on, with, and, or, by, from, that, this, is, are, be, it
- Lowercase, spaces → hyphens, strip non-alphanumeric characters
- Examples: "add CSV export for invoices" → `add-csv-export`; "allow changing email address" → `change-email-address`

Set `CR_SLUG = <AREA_SLUG>-<CHANGE_SLUG>` — this is the OpenSpec change name AND the branch slug.

---

### Phase 4 — Product Scope Gate

**This is the "product checks first" step.** Before writing anything, product assesses
which spec domains the request touches and how heavy the change is.

Spawn `product-owner` agent with `mode: "bypassPermissions"` in SCOPE-ASSESSMENT MODE:

```
Spawn Task:
  subagent_type = "product-owner"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/product-owner.md and execute its boot + research phases.

    You are operating in SCOPE-ASSESSMENT MODE. Do NOT write or edit any files.
    Do NOT ask the user any questions. Return your verdict as text only.

    AREA: <AREA_SLUG> (kind: <AREA_KIND>)
    CHANGE DESCRIPTION: <USER_CHANGE_DESCRIPTION>

    STEP 1 — Read current behavior:
      - openspec/specs/<domain>/spec.md for each candidate domain (<AFFECTED_DOMAINS>)
      - the archived change or legacy docs for the area (see AREA kind)
      - openspec/changes/ — check for in-flight changes touching the same domains

    STEP 2 — Assess:
      - AFFECTED_DOMAINS: which spec domains the deltas will touch (existing ones
        preferred; propose a new domain only for genuinely new capability)
      - SCOPE:
        * TARGETED = modifies/extends existing requirements; no new user journey;
          few new screens → capture the change here and go straight to scrum-team.
        * FEATURE_SIZED = introduces a distinct user journey or substantial new UI
          → better served by the full /prepare-feature path (interactive
          requirements + mockups + human approval).
      - CONFLICTS: any in-flight change touching the same domains.

    STEP 3 — Return EXACTLY this format as your final message (no files):
      AFFECTED_DOMAINS: <comma-separated>
      SCOPE: TARGETED            (or)   SCOPE: FEATURE_SIZED
      REASONING: <1-2 sentences>
      CONFLICTS: <in-flight change names, or "none">
  """
```

Wait for the task to complete. Parse `AFFECTED_DOMAINS`, `SCOPE`, `REASONING`, `CONFLICTS`.

If `CONFLICTS` is not "none", warn the user in the next question's description text.

**Present the verdict to the user** with `AskUserQuestion`:

**If SCOPE = TARGETED:**
"Product's assessment: a **targeted change** to domains: <AFFECTED_DOMAINS>.
Reason: <REASONING>

How would you like to proceed?"
Options:
1. "Proceed — capture the change and implement" (default)
2. "Route through /prepare-feature instead (mockups + human gates)"

**If SCOPE = FEATURE_SIZED:**
"Product's assessment: this is **feature-sized** — a distinct journey or substantial new UI.
Reason: <REASONING>

How would you like to proceed?"
Options:
1. "Run the full preparation path" (default) → print and STOP (do not auto-run):
   ```
   This is better prepared as a full feature. Run:

     /prepare-feature <CR_SLUG>

   and describe the change there — it will produce the OpenSpec change with
   mockups and human approval gates. <AREA_SLUG>'s current specs stay untouched
   until that change ships.
   ```
2. "Capture it here anyway as a targeted change" → continue to Phase 5.

---

### Phase 5 — Write the OpenSpec Change

Spawn `product-owner` agent with `mode: "bypassPermissions"` in CHANGE-PROPOSAL MODE:

```
Spawn Task:
  subagent_type = "product-owner"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/agents/product-owner.md and execute it.

    You are operating in CHANGE-PROPOSAL MODE for a change request against an
    existing area. Create a NEW OpenSpec change — do NOT edit the living specs
    in openspec/specs/ and do NOT edit any archived change.

    CHANGE NAME: <CR_SLUG>
    AREA: <AREA_SLUG>
    AFFECTED DOMAINS: <AFFECTED_DOMAINS>
    CHANGE DESCRIPTION: <USER_CHANGE_DESCRIPTION>

    STEP 1 — Read the living specs for the affected domains and the area context
    (archived change / legacy docs).

    STEP 2 — Ask ONLY incremental clarifying questions about the change
    (2-4 max, via AskUserQuestion). Do NOT re-gather requirements already
    covered by the living specs.

    STEP 3 — Write openspec/changes/<CR_SLUG>/:
      - proposal.md per the conventions doc. In `## Why`, name the area and what
        prompted the change. In `## Impact`, list the affected domains and note
        this modifies existing behavior.
      - specs/<domain>/spec.md delta files:
        * `## MODIFIED Requirements` for requirements that change — the name must
          EXACTLY match the living spec, restate the full requirement + ALL its
          scenarios (with your edits applied)
        * `## ADDED Requirements` for new behavior
        * `## REMOVED Requirements` (with **Reason**:) for retired behavior
      - Do NOT write design.md or tasks.md (architect/scrum-master own those).

    STEP 4 — Validate: `<openspec-cli> validate <CR_SLUG> --strict` must pass.
    Fix and re-run until it does (max 3 attempts, then report the output).
  """
```

Wait for the task to complete.

**Validate:**
- `<openspec-cli> validate <CR_SLUG> --strict` exits 0.
- `openspec/changes/<CR_SLUG>/proposal.md` has a non-empty `## Why`.
- At least one delta spec exists under `openspec/changes/<CR_SLUG>/specs/`, and for a
  TARGETED change at least one `## MODIFIED Requirements` or `## REMOVED Requirements`
  section references the existing behavior (a change request that only ADDs and touches
  nothing existing is suspicious — warn if so).

If validation fails: re-spawn `product-owner` with `bypassPermissions`, appending:
"The OpenSpec change <CR_SLUG> is missing sections or fails validation: <validator output>. Fix it and re-validate."
Wait and re-validate. Retry up to 2 times total.

---

### Phase 6 — Present and Confirm

Print the proposal.md `## Why` and `## What Changes` sections, plus a per-domain summary
of the deltas (counts of MODIFIED / ADDED / REMOVED requirements with their names).

Then use `AskUserQuestion`:
"The change is captured at `openspec/changes/<CR_SLUG>/` (validated). How would you like to proceed?"
Options:
1. "Launch scrum-team — implement the change now"
2. "Save for later — I'll run `/scrum-team <CR_SLUG>` when ready"
3. "Something is wrong — revise"

**If "Save for later":**
Print:
```
Change captured and validated:
  openspec/changes/<CR_SLUG>/proposal.md
  openspec/changes/<CR_SLUG>/specs/<domain>/spec.md

When ready to implement, run:
  /scrum-team <CR_SLUG>

The scrum-team will read the change and modify the existing code and tests
in place. After the PR merges, /ship archives the change into the living specs.
```
Then STOP.

**If "Revise":**
Use `AskUserQuestion` to ask: "What should be revised?"
Re-spawn `product-owner` with `bypassPermissions`, appending the revision feedback:
"The user reviewed the change and requested revisions: <revision feedback>. Update openspec/changes/<CR_SLUG>/ accordingly and re-validate with `<openspec-cli> validate <CR_SLUG> --strict`."
Wait for completion. Then loop back to Phase 6.

**If "Launch":**
Proceed to Phase 7.

---

### Phase 7 — Scrum-Team Launch

Spawn a `general-purpose` agent with `mode: "bypassPermissions"` to run the scrum-team
workflow on the change:

```
Spawn Task:
  subagent_type = "general-purpose"
  mode          = "bypassPermissions"
  prompt        = """
    Read ~/.claude/commands/scrum-team.md and execute it fully.

    $ARGUMENTS = <CR_SLUG>

    This is a CHANGE REQUEST against existing area '<AREA_SLUG>'. The OpenSpec
    change already exists at openspec/changes/<CR_SLUG>/ and is PRE-APPROVED.

    PHASE 1 OVERRIDE (product-owner):
      - openspec/changes/<CR_SLUG>/ (proposal.md + delta specs) is ALREADY
        WRITTEN and validated. Do NOT regenerate, re-ask, or overwrite it.
        Treat the Phase 1 validate gate as the only Phase 1 step.

    PHASE 2 OVERRIDE (architect + ux-designer):
      - The change modifies existing behavior. architect writes
        openspec/changes/<CR_SLUG>/design.md focused on the delta — which
        existing files change (File Inventory: mostly Modified Files).
      - ux-designer: if docs/features/<AREA_SLUG>/UX-DESIGN.md exists, EDIT it
        in place for the affected flows and save the updated copy as the change's
        UX reference; skip mockup regeneration unless the change adds or removes
        screens.

    PHASE 4 OVERRIDE (developers + QA):
      - Modify the existing feature's CODE and TESTS in place to implement the
        deltas. Do NOT scaffold a parallel implementation.
      - Update the area's existing test cases to match MODIFIED requirements;
        add test cases for ADDED requirements; remove/retire tests only for
        REMOVED requirements.

    PHASES 3, 5-6: Run normally per the scrum-team workflow (scrum-master writes
    tasks.md; tech-lead creates the PR; NO archiving — /ship archives post-merge).
  """
```

After spawning, report to the user:
```
Scrum-team launched for change '<CR_SLUG>' (area: <AREA_SLUG>).

Requirements deltas: openspec/changes/<CR_SLUG>/specs/
Code and tests are modified IN PLACE on branch: feature/<CR_SLUG>

After the PR merges, run /ship to archive the change — that folds the deltas
into openspec/specs/ and moves the change to the archive audit trail.
```

---

The area to apply a change request to: $ARGUMENTS
