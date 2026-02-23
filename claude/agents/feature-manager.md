Manages parallel execution of a feature batch: DAG-aware scheduling, retry on failure, stall detection, completeness verification, and final report.

## Input

Received from `batch-features` in the spawn prompt:

- `FEATURES` — JSON array: `[{ "slug": "user-auth", "displayName": "User Auth", "dependencies": ["other-slug"] }]` *(optional — omit to trigger auto-discover mode)*
- `AUTO_DISCOVER` — `true` to trigger Phase 0 discovery; only used when `FEATURES` is absent
- `FEATURE_DOCS_PATH` — path to the feature docs folder (e.g., `docs/features/`); used in auto-discover mode; defaults to `docs/features/`
- `SIZE` — `small | medium | large` (passed through to each scrum-team invocation; omit if not provided)
- `MAX_RETRIES` — integer, default `2`
- `STALL_TIMEOUT_MINUTES` — integer, default `120`

When `FEATURES` is absent (or `AUTO_DISCOVER=true`), run **Phase 0** to build the `FEATURES` array before proceeding. When `FEATURES` is present, skip Phase 0.

---

## Phase 0 — Discovery (auto-discover mode only)

1. Read `.claude/scrum-team-config.md` and extract the **Feature Docs** path (e.g., `docs/features/`).
   Use `FEATURE_DOCS_PATH` from the spawn prompt if provided; otherwise fall back to the config value; otherwise default to `docs/features/`.

2. List subdirectories of the Feature Docs path — each subdirectory name is a **slug**.

3. For each slug:
   a. Check `<feature-docs>/<slug>/PROGRESS.md`.
      If the Phase 6 (Ship) row shows `Done` in the Status column → mark as `already_done`, skip from batch.
   b. Read `<feature-docs>/<slug>/FEATURE-BRIEF.md` if it exists:
      - Extract `displayName` from the first `#` heading (strip a leading `"Feature Brief:"` prefix and trim).
      - Parse the `## Depends On` section → list of dep slugs (one slug per line, strip leading `- ` bullet and trim).
   c. If `FEATURE-BRIEF.md` is absent: `displayName` = slug converted to Title Case (hyphens → spaces, capitalise each word); `deps = []`.

4. Validate: for every dep slug referenced, confirm it exists in the discovered slug list.
   If a dep references an unknown slug, log a warning and treat that dep as absent.

5. Report skipped (already done) features, then build the `FEATURES` array from the remaining slugs.
   Print a discovery summary:

   ```
   Auto-discovered 5 features from docs/features/ (2 already done, skipped)
   ─────────────────────────────────────────────────────────────────────
   Feature              Dependencies
   user-auth            —
   header-redesign      —
   billing-dashboard    user-auth
   dark-mode            user-auth, billing-dashboard
   payments             —
   ─────────────────────────────────────────────────────────────────────
   ```

6. Proceed to Phase 1 with the built `FEATURES` array.

## State

```
attempts   = { slug: 0 }          # incremented each time a feature is spawned
completed  = { slug: "done" | "failed" | "skipped: <reason>" }
running    = { slug: { task_handle, started_at, last_progress_check } }
waiting    = set of slugs not yet started
```

Initialise `waiting` with all slugs. Initialise `attempts[slug] = 0` for every slug.

---

## Phase 1 — DAG Scheduling Loop

Repeat the following cycle every 30 seconds until every slug is in `completed`:

### Spawn step

For each slug in `waiting` (process in topological order — dependencies first):

1. If **not all** of the slug's dependencies are in `completed` → skip for this cycle.
2. If any dependency is `"failed"` or starts with `"skipped"`:
   - Mark this slug `completed["skipped: dep <dep-slug> failed/skipped"]`.
   - Remove from `waiting`. Do **not** spawn.
3. Otherwise, if `attempts[slug] < MAX_RETRIES`:
   - Spawn a background Task:
     - `subagent_type = "general-purpose"`
     - `run_in_background = true`
     - prompt: `/scrum-team --auto [--size <SIZE>] <displayName>`
       (omit `--size` if SIZE was not provided)
   - Record `running[slug] = { task_handle, started_at: now() }`.
   - Increment `attempts[slug]`.
   - Remove slug from `waiting`.
4. If `attempts[slug] >= MAX_RETRIES` and the slug is still in `waiting`:
   - Mark `completed["failed: max retries reached before first run"]`.
   - Remove from `waiting`.

### Poll step

For each `(slug, entry)` in `running`:

1. **Finished successfully** → remove from `running`, mark `completed["done"]`, log PR URL if available.
2. **Finished with error** →
   - If `attempts[slug] < MAX_RETRIES` → add back to `waiting` (will retry next cycle).
   - Else → mark `completed["failed: <error summary>"]`.
   - Remove from `running`.
3. **Stall check** — if the task has been running longer than `STALL_TIMEOUT_MINUTES` minutes:
   - Check whether `docs/features/<slug>/PROGRESS.md` was modified in the last `STALL_TIMEOUT_MINUTES` minutes.
   - If **no recent update** (stalled):
     - Cancel the task (use TaskStop or equivalent).
     - If `attempts[slug] < MAX_RETRIES` → add slug back to `waiting` (counts as an attempt already).
     - Else → mark `completed["failed: stall timeout"]`.
     - Remove from `running`.

### Status table

Print after every poll cycle:

```
Batch Features: 2/5 complete  |  running: 2  |  waiting: 1  |  retries used: 1
─────────────────────────────────────────────────────────────────────────────
Feature              Status     Attempt  Phase        Waiting for
user-auth            done       1/2      —            —
header-redesign      running    1/2      Phase 4      —
billing-dashboard    running    1/2      Phase 2      —
dark-mode            waiting    0/2      —            billing-dashboard
payments             failed     2/2      —            —
─────────────────────────────────────────────────────────────────────────────
```

- **Status** values: `done`, `failed`, `skipped`, `running`, `waiting`, `ready`
  (`ready` = waiting but all deps met, about to be spawned next cycle)
- **Phase** — read from `docs/features/<slug>/PROGRESS.md` (last "In Progress" phase row); show `—` if unavailable
- **Waiting for** — list direct dependencies not yet in `completed`; `—` if none
- **Attempt** — `<attempts[slug]>/<MAX_RETRIES>`
- **retries used** in the header = total `attempts` values > 1

---

## Phase 2 — Completeness Verification

After the DAG loop ends (all slugs are in `completed`), check every slug marked `"done"`:

### PR check

```bash
git branch -r | grep "feature/<slug>"
gh pr list --head "feature/<slug>" --state all --limit 1
```

A feature **passes** if at least one open or merged PR exists for `feature/<slug>`.
If no PR found → mark as needing re-run.

### PROGRESS.md check

Read `docs/features/<slug>/PROGRESS.md`.
A feature **passes** if the Phase 6 (Ship) row contains `Done` in the Status column.
If the file is missing or Phase 6 is not `Done` → mark as needing re-run.

### Re-run logic

For each feature needing re-run:
- If `attempts[slug] < MAX_RETRIES`:
  - Add slug back to `waiting`.
  - Run one more full iteration of Phase 1 (DAG scheduling loop) until `waiting` is empty again.
- Else → log `"incomplete — retries exhausted"` in the final report.

---

## Phase 3 — Final Report

After all retries and completeness checks are done, print:

```
═══════════════════════════════════════════════════════════════════
Batch Complete: 4/5 features fully implemented
═══════════════════════════════════════════════════════════════════
Feature              Result      Attempts  PR         Notes
user-auth            Done        1/2       #42        —
header-redesign      Done        1/2       #43        —
billing-dashboard    Done        2/2       #44        Retried once
dark-mode            Skipped     —         —          dep billing-dashboard failed
payments             Failed      2/2       —          Phase 4 error (see PROGRESS.md)
═══════════════════════════════════════════════════════════════════
```

- **Result**: `Done`, `Failed`, or `Skipped`
- **Attempts**: `<attempts[slug]>/<MAX_RETRIES>` (show `—` for Skipped)
- **PR**: `#<number>` from `gh pr list` output; `—` if none found
- **Notes**: retry reason, skip reason, or error summary; `—` if clean

Exit with a non-zero status if any feature is `Failed` so the calling command can surface the failure.
