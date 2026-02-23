Process a list of features autonomously, one after another (or in parallel). Always runs in --auto mode.

## Usage

```
/batch-features --features "user-auth, billing-dashboard, dark-mode"
/batch-features --file docs/backlog.md
/batch-features --features "feat-a, feat-b" --parallel
/batch-features --features "feat-a, feat-b" --size medium
```

## Arguments

- `--features "a, b, c"` — comma-separated feature list (inline); supports dependency annotations (see below)
- `--file <path>` — markdown file with one feature per line (lines starting with `#` are comments); supports dependency annotations (see below)
- `--parallel` — run all features simultaneously with DAG-aware scheduling; default is sequential
- `--size small|medium|large` — passed to each scrum-team invocation (applies to all features)
- `--auto` is always implied (batch mode is always autonomous)

## Dependency Declaration

Features can declare dependencies using an inline `[depends-on: ...]` annotation.

**In `--features` mode:**
```
/batch-features --features "user-auth, billing-dashboard[depends-on:user-auth], dark-mode[depends-on:user-auth,billing-dashboard]"
```

**In `--file` mode** — add `[depends-on: feat-a, feat-b]` after the feature name on the same line:
```
user-auth
billing-dashboard [depends-on: user-auth]
dark-mode [depends-on: user-auth, billing-dashboard]
header-redesign
```
Lines starting with `#` and blank lines remain ignored.

Spaces inside the bracket annotation are optional — `[depends-on:user-auth]` and `[depends-on: user-auth]` are both valid.

## Workflow

### Phase 1: Parse

Read `$ARGUMENTS` and extract:
1. Feature list from `--features "..."` (split on `,`, trim whitespace) OR from `--file <path>` (read file, skip lines starting with `#` and blank lines)
2. `--parallel` flag (default: sequential)
3. `--size` flag (default: auto-detect per feature)

Verify `.claude/scrum-team-config.md` exists. If not, STOP and tell the user to run `dodocs-workflow init`.

**Parse dependency annotations:**

For each raw entry, check for a `[depends-on: ...]` bracket (case-insensitive, spaces optional):
- Extract the dependency list by splitting on `,` and trimming whitespace
- Strip the entire `[depends-on: ...]` portion from the display name
- Derive a kebab-case slug for each feature name (lowercase, spaces → hyphens, strip special characters)
- Build an adjacency list mapping each feature slug to its list of dependency slugs: `{ feature -> [dependencies] }`

**Validate dependencies:**

For every dependency referenced in any `[depends-on: ...]` annotation, verify that the dependency slug is itself present in the feature list. If any referenced dependency is missing, STOP immediately with:
```
Error: 'billing-dashboard' depends on 'user-auth' which is not in the feature list.
```

**Topological sort (Kahn's algorithm):**

1. Compute in-degree for each feature (number of features that must complete before it)
2. Enqueue all features with in-degree 0 into a processing queue
3. While the queue is non-empty:
   a. Dequeue a feature and append it to the sorted execution order
   b. For each feature that depends on the just-dequeued feature, decrement its in-degree
   c. If any dependent feature's in-degree reaches 0, enqueue it
4. If the sorted list length is less than the total number of features, a cycle exists — STOP with:
```
Error: Circular dependency detected: billing-dashboard → user-auth → billing-dashboard
```
   (Trace the cycle by following back-edges from any feature that was never dequeued.)

All subsequent phases operate on the **topologically sorted** feature list.

### Phase 2: Plan

Print the batch plan before starting, showing the resolved execution order and dependency relationships:

```
Batch: 4 features | Mode: sequential | Size: large
Execution order (dependency-sorted):
─────────────────────────────────────────────────
1. user-auth
2. header-redesign
3. billing-dashboard         [after: user-auth]
4. dark-mode                 [after: user-auth, billing-dashboard]
─────────────────────────────────────────────────
```

Features with no dependencies show no `[after: ...]` annotation. Features with dependencies list their direct dependencies in the `[after: ...]` column.

### Phase 3: Execute

#### Sequential mode (default)

For each feature in **topologically sorted order**:
1. Log: `Starting feature N/total: <feature-name>`
2. Spawn a Task that runs the full scrum-team workflow:
   ```
   Spawn Task:
     subagent_type = "general-purpose"
     prompt        = "/scrum-team --auto [--size <SIZE>] <displayName>"
                     (omit --size if SIZE was not provided)
   ```
   Wait for the Task to complete before starting the next feature.
3. If the task finished successfully → log: `Feature <name> complete — PR: <url>`
4. If the task finished with error → log the failure, mark it as Failed, and continue to the next feature.

Because the list is topologically sorted, a feature only starts after all its dependencies have already completed (or been marked Failed — in which case proceed anyway and let the downstream feature fail naturally if the dependency was critical).

#### Parallel mode (`--parallel`)

Spawn a single `feature-manager` agent and wait for it to complete.

Build the spawn prompt containing:
- `FEATURES` — JSON array of `{ slug, displayName, dependencies }` objects (topologically sorted)
- `SIZE` — the value of the `--size` flag (omit the field if `--size` was not provided)
- `MAX_RETRIES=2`
- `STALL_TIMEOUT_MINUTES=120`

```
Spawn Task:
  subagent_type = "feature-manager"
  prompt        = """
    FEATURES=<json array>
    SIZE=<size>          # omit if not provided
    MAX_RETRIES=2
    STALL_TIMEOUT_MINUTES=120
  """
Wait for the feature-manager agent to complete.
```

The `feature-manager` agent owns all scheduling, retry logic, stall detection,
completeness verification, and the final report. No further parallel logic is
needed here — proceed directly to Phase 4 once the agent returns.

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
