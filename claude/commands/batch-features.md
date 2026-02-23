Process a list of features autonomously, one after another (or in parallel). Always runs in --auto mode.

## Usage

```
/batch-features --features "user-auth, billing-dashboard, dark-mode"
/batch-features --file docs/backlog.md
/batch-features --features "feat-a, feat-b" --parallel
/batch-features --features "feat-a, feat-b" --size medium
```

## Arguments

- `--features "a, b, c"` — comma-separated feature list (inline)
- `--file <path>` — markdown file with one feature per line (lines starting with `#` are comments)
- `--parallel` — run all features simultaneously; default is sequential
- `--size small|medium|large` — passed to each scrum-team invocation (applies to all features)
- `--auto` is always implied (batch mode is always autonomous)

## Workflow

### Phase 1: Parse

Read `$ARGUMENTS` and extract:
1. Feature list from `--features "..."` (split on `,`, trim whitespace) OR from `--file <path>` (read file, skip lines starting with `#` and blank lines)
2. `--parallel` flag (default: sequential)
3. `--size` flag (default: auto-detect per feature)

Verify `.claude/scrum-team-config.md` exists. If not, STOP and tell the user to run `dodocs-workflow init`.

Derive a kebab-case slug for each feature name (lowercase, spaces → hyphens, strip special characters).

### Phase 2: Plan

Print the batch plan before starting:

```
Batch: N features | Mode: sequential | Size: large
─────────────────────────────────────────────────
1. user-auth
2. billing-dashboard
3. dark-mode
```

### Phase 3: Execute

#### Sequential mode (default)

For each feature in order:
1. Log: `Starting feature N/total: <feature-name>`
2. Run the full scrum-team workflow inline with AUTO_MODE=true and the specified SIZE:
   - Spawn all agents as scrum-team would, following the Team Size Configuration
   - AUTO_MODE=true is always set (batch implies --auto)
3. Wait for Phase 6 (PR creation) to complete before starting the next feature
4. Log completion with PR URL: `Feature <name> complete — PR: <url>`
5. Proceed to next feature

If a feature fails, log the failure with the error, mark it as Failed, and continue to the next feature.

#### Parallel mode (`--parallel`)

Spawn all features simultaneously. For each feature, spawn a Task with `subagent_type="general-purpose"` that runs:
```
/scrum-team --auto [--size <size>] <feature-name>
```
Store all task handles.

Monitor loop (check every 30 seconds and print status):
```
Batch Features: 0/3 complete
─────────────────────────────────────────────────
Feature              Status     Phase
user-auth            running    Phase 4
billing-dashboard    running    Phase 2
dark-mode            running    Phase 1
─────────────────────────────────────────────────
```

Wait for all tasks to complete (success or failure).

### Phase 4: Report

After all features are processed, print the final summary table:

```
═══════════════════════════════════════════════════════
Batch Complete: 3/3 features processed
═══════════════════════════════════════════════════════
Feature              Result   PR
user-auth            Done     #42
billing-dashboard    Done     #43
dark-mode            Failed   —  (see docs/features/dark-mode/PROGRESS.md)
═══════════════════════════════════════════════════════
```

The feature list to process: $ARGUMENTS
