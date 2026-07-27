Merge all open `feature/*` pull requests into main in creation order, with CI gating,
auto-rebase on conflicts, and a final summary report.

**Arguments** (all optional):
- *(none)* — merge all open `feature/*` PRs
- `--dry-run` — assess and display status table, then exit without merging
- `--only <n,m,...>` — merge only the specified PR numbers (comma-separated)
- `--skip-ci` — bypass CI gate (merge even if checks are pending or failing)

---

## Phase 1 — Validate Environment

Run these checks before doing anything else:

```bash
gh auth status              # gh CLI authenticated?
git rev-parse --git-dir     # inside a git repo?
git remote get-url origin   # has origin remote?
```

If any check fails, stop immediately with a clear error message explaining what is missing.

---

## Phase 2 — Discover Open Feature PRs

```bash
gh pr list \
  --base main \
  --state open \
  --limit 100 \
  --json number,title,headRefName,url,createdAt,mergeable,mergeStateStatus,statusCheckRollup
```

**Filter**: keep only entries where `headRefName` starts with `feature/`.

**Sort**: by `createdAt` ascending (oldest first — least likely to conflict after rebases).

If `--only <n,m,...>` was passed, further filter to only those PR numbers.

**Per PR, derive:**

- **CI status**: scan `statusCheckRollup`
  - any `conclusion == FAILURE` → `FAIL`
  - any `status == IN_PROGRESS` → `PENDING`
  - else → `PASS`
- **Conflict state**: `mergeable == CONFLICTING` → needs rebase

If no matching PRs are found, print "No open feature/* PRs found." and exit.

---

## Phase 3 — Assessment Table

Display the status of every discovered PR:

```
Open Feature PRs
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
 #   Branch                      CI          Conflicts  Action
 35  feature/org-invitations     🔄 Pending  ✅ Clean   ⏭️  skip (CI pending)
 38  feature/dark-mode           ✅ Pass     ⚠️  Conflict  🔧 rebase then merge
 42  feature/billing-dashboard   ✅ Pass     ✅ Clean   ✅ ready to merge
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Plan: merge 2, skip 1 (CI pending)
```

**Action logic per PR:**

| CI       | Conflict  | --skip-ci | Action                              |
|----------|-----------|-----------|-------------------------------------|
| PASS     | Clean     | any       | ✅ ready to merge                   |
| PASS     | Conflict  | any       | 🔧 rebase then merge                |
| PENDING  | any       | false     | ⏭️ skip (CI pending)                |
| PENDING  | any       | true      | ✅ merge anyway (--skip-ci)         |
| FAIL     | any       | false     | ⏭️ skip (CI failed)                 |
| FAIL     | any       | true      | ✅ merge anyway (--skip-ci)         |

After displaying the table, ask:

```
Proceed? [y = merge, n = abort, d = dry-run view only]
```

If `--dry-run` was passed: display the table and exit without asking or merging.
If user enters `n` or anything other than `y`/`d`: abort with "Aborted. No PRs were merged."
If user enters `d`: display the table again and exit.

---

## Phase 4 — Auto-Rebase Conflicting PRs

For each PR marked "🔧 rebase then merge", spawn a tech-lead agent with
`mode: "bypassPermissions"` with this task:

```
Task: Rebase feature/<branch-name> onto latest main.

Steps:
1. git fetch origin main
2. git checkout feature/<branch-name>
3. git rebase origin/main
   - For each conflict that arises:
     - For files that are NEW in the feature branch (not in main): keep the feature version
     - For infrastructure / config files that exist in both branches: prefer main's version
       unless the feature explicitly requires the change
     - git add <resolved-file> && git rebase --continue
4. git push --force-with-lease origin feature/<branch-name>
5. Report back: "rebased successfully" or list files with unresolvable conflicts

If the rebase cannot be completed cleanly, do NOT force-push. Report failure instead.
```

**After the rebase agent reports back:**

- If "rebased successfully": wait up to 60 seconds, then re-check CI and mergeable state
  via `gh pr view <number> --json mergeable,statusCheckRollup`
- If rebase failed: mark PR as `❌ conflict — manual resolution needed`, skip it, continue

---

## Phase 5 — Merge Loop

Process each ready PR in oldest-first order (same order as the assessment table).

For each ready PR:

### Step 1: Final CI gate

```bash
gh pr checks <number> --watch --interval 10
```

Wait up to 5 minutes for pending checks to complete. If checks are still failing after the
wait (and `--skip-ci` is not set), skip the PR with a warning:
`⏭️ Skipped #<number>: CI still failing after 5-minute wait`

### Step 2: Squash merge

```bash
gh pr merge <number> \
  --squash \
  --delete-branch \
  --subject "feat(<feature-slug>): <PR title>"
```

Where `<feature-slug>` is the branch name with `feature/` prefix stripped.

Record the resulting commit SHA:
```bash
git pull origin main
git rev-parse HEAD
```

### Step 2b: Archive the OpenSpec change (post-merge, on main)

If the project has an `openspec/` directory and `openspec/changes/<feature-slug>/` exists
(the slug is the branch name with `feature/` stripped — for change-request branches this
is the full `<area>-<change>` slug):

```bash
git checkout main && git pull
# read the OpenSpec CLI line from .claude/scrum-team-config.md; default:
npx -y @fission-ai/openspec@1.6.0 archive <feature-slug> --yes
```

- Before archiving, verify every checkbox in `openspec/changes/<feature-slug>/tasks.md`
  is `[x]`; tick stragglers that correspond to shipped work (the CLI refuses to archive
  otherwise).
- If archive creates a new domain spec with a `TBD` Purpose, fill it in.
- Update `docs/features/<feature-slug>/PROGRESS.md` Related Docs to the archive path
  (`openspec/changes/archive/<DATE>-<feature-slug>/`) if that file exists.
- Commit and push: `git add openspec docs/features && git commit -m "openspec: archive <feature-slug>" && git push`
- If the archive fails, log a warning and continue the merge loop — do not block other
  PRs; report unarchived changes in the final summary.

Never archive a change whose PR has not merged — the living specs must only reflect
merged code.

### Step 3: Re-check remaining PRs

After each merge, main has advanced. Re-check the remaining unmerged PRs:

```bash
gh pr view <number> --json mergeable,mergeStateStatus
```

If a previously-clean PR now shows `CONFLICTING`, trigger the auto-rebase flow
(Phase 4) for that PR before its turn comes.

---

## Phase 6 — Final Report

Display a summary after all PRs have been processed:

```
Merge Summary
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
✅ Merged:   #42 billing-dashboard  →  abc1234  (change archived)
✅ Merged:   #38 dark-mode (auto-rebased)  →  def5678  (change archived)
⏭️ Skipped:  #35 org-invitations (CI pending at merge time)
❌ Failed:   #40 payments (unresolvable merge conflict)
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
main is now: def5678
2 features shipped. 2 PRs still open. 0 changes left unarchived.

To retry skipped/failed PRs, run /merge-features again after resolving the issues.
```

**Status legend:**
- `✅ Merged` — squash-merged successfully
- `✅ Merged (auto-rebased)` — rebased onto latest main before merging
- `⏭️ Skipped` — CI pending or failing (not merged)
- `❌ Failed` — unresolvable merge conflict, needs manual intervention
