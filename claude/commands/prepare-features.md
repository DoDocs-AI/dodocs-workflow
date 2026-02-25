Batch daytime preparation: run the full preparation pipeline (requirements → mockups → validation → approval) for multiple features sequentially.

## Usage

```
/prepare-features                                          # auto-discover pending features
/prepare-features --features "feat-a, feat-b, feat-c"     # explicit list
/prepare-features --file docs/backlog.md                  # from file
```

## Arguments

- *(no args)* — auto-discover features from `docs/features/` where STATUS is `draft`, `requirements-ready`, or `mockups-ready`
- `--features "a, b, c"` — comma-separated feature list
- `--file <path>` — markdown file with one feature per line (lines starting with `#` are comments)

Features are processed **sequentially** — human reviews and approves each feature's mockups before the next feature begins.

---

## Workflow

### Phase 1: Parse

Read `$ARGUMENTS` and extract:
1. Feature list from `--features "..."` (split on `,`, trim whitespace)
2. OR from `--file <path>` (read file, skip lines starting with `#` and blank lines)
3. OR auto-discover (neither flag present)

Verify `.claude/scrum-team-config.md` exists. If not, STOP and tell the user to run `dodocs-workflow init`.

**Auto-discover detection:**
If neither `--features` nor `--file` is present → set `AUTO_DISCOVER=true`.
Read `.claude/scrum-team-config.md` and extract the Feature Docs path (default: `docs/features/`).

Scan `<FEATURE_DOCS_PATH>` for subdirectories. For each:
- Read `docs/features/<slug>/STATUS`
- Include if STATUS is: `draft`, `requirements-ready`, or `mockups-ready`
- Skip if STATUS is: `approved`, `in-progress`, or `completed`
- Skip if STATUS file does not exist (legacy feature without STATUS tracking)

**Derive slugs:**
For each raw feature name, derive kebab-case slug: lowercase, spaces → hyphens, strip special characters.

### Phase 2: Confirm

If no features found (auto-discover returned empty list), print:
```
No features pending preparation found in <FEATURE_DOCS_PATH>.

To prepare a new feature: /prepare-feature <feature-name>
To start overnight development: /batch-features
```
Stop.

Otherwise, print the list and confirm:
```
Features to prepare (N total):
  1. <feature-name> (status: draft)
  2. <feature-name> (status: mockups-ready — will resume from validation)
  3. <feature-name> (status: requirements-ready — will resume from mockup design)

Features will be prepared sequentially. You will review each feature's mockups
before the next feature begins.
```

Ask user:
```
AskUserQuestion:
  "Prepare these N features?"
  Options:
    - "Yes, start preparation"
    - "Let me adjust the list first"
    - "Cancel"
```

If "Let me adjust": ask user to specify which features to include/exclude, update list, re-confirm.
If "Cancel": stop.

### Phase 3: Sequential Preparation Loop

For each feature in order:

1. Print: `Starting preparation N/total: <feature-name>`

2. Spawn a Task that reads and executes `prepare-feature.md`:
   ```
   Spawn Task:
     subagent_type = "general-purpose"
     mode          = "bypassPermissions"
     prompt        = """
       Read the file ~/.claude/commands/prepare-feature.md and execute
       the full workflow described in it.
       Set $ARGUMENTS to: <feature-name>

       This is feature N of <total> in a batch preparation session.
       The human is present and will interact with product-owner questions
       and the final mockup approval step.
     """
   ```

3. Wait for the Task to complete (including human approval interaction).

4. Read `docs/features/<slug>/STATUS`:
   - `approved` → print: `Feature '<slug>' approved. (N/total complete)`
   - `draft` → print: `Feature '<slug>' was rejected or abandoned. Moving to next feature.`
   - Other → print: `Feature '<slug>' preparation ended with status: <status>.`

5. If there are more features remaining: continue to the next one.

### Phase 4: Final Summary

After all features are processed:

```
═══════════════════════════════════════════════════════
Preparation Complete: N/total features approved
═══════════════════════════════════════════════════════
Feature              Status
<feat-a>             approved
<feat-b>             approved
<feat-c>             rejected
═══════════════════════════════════════════════════════

Approved features are ready for overnight development.
Run /batch-features to start autonomous development.
```

The features to prepare: $ARGUMENTS
