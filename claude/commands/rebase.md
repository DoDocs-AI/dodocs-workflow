Rebase the current feature/fix branch on top of `main` and verify all migrations are properly ordered and named.

## Usage

```
/rebase
```

---

## What This Command Does

1. Fetches latest `main` from origin
2. Rebases the current branch on top of `main`
3. Locates all migration files in the project
4. Checks every migration for correct naming convention and sequential order
5. Renames and fixes any migrations that are out of order or incorrectly named
6. Reports a full summary of what was checked and what was fixed

---

## Steps

### Step 1: Identify Current Branch

```bash
git branch --show-current
```

If you are already on `main`, stop and tell the user: "You are on `main` — nothing to rebase. Switch to your feature or fix branch first."

### Step 2: Fetch and Rebase

```bash
git fetch origin main
git rebase origin/main
```

- If there are **no conflicts**: rebase completes automatically — continue.
- If there are **conflicts**:
  - Show the conflicting files to the user.
  - Resolve each conflict file by keeping the correct code (prefer the incoming changes from main for infrastructure/config; prefer branch changes for feature code).
  - After resolving: `git add <resolved-files> && git rebase --continue`
  - Repeat until rebase completes.
  - If the rebase cannot be completed automatically, run `git rebase --abort` and report the exact conflict details to the user — do NOT force-push or skip.

### Step 3: Locate Migration Files

Check the project config at `.claude/scrum-team-config.md` for a migrations path if defined.

Also scan these common locations:
- `src/main/resources/db/migration/` (Flyway / Java)
- `migrations/` (Django, general)
- `db/migrations/` (general)
- `alembic/versions/` (Python/Alembic)
- `database/migrations/` (Laravel)
- Any directory with files matching `*.sql`, `*migration*.py`, `*_migration.py`

List all migration files found. If no migrations exist in the project, skip to Step 5 and note "No migrations found."

### Step 4: Check and Fix Migrations

#### 4a. Determine the naming convention

Look at existing migration files already on `main`:
```bash
git show origin/main:<migrations-path>
```
Identify the pattern in use:
- **Flyway**: `V<N>__<snake_case_description>.sql` — e.g., `V5__add_user_roles.sql`
- **Django**: `<NNNN>_<snake_case_description>.py` — e.g., `0005_add_user_roles.py`
- **Alembic**: `<hex_revision>_<snake_case_description>.py`
- **Sequential SQL**: `<NNN>_<snake_case_description>.sql` — e.g., `005_add_user_roles.sql`
- Any other pattern: document what is in use

#### 4b. Find the last migration number on main

```bash
git show origin/main:<migrations-path> 2>/dev/null
```

Parse the highest version/sequence number from the migration files on `main`.

#### 4c. Find new migrations on this branch

Compare with main to find migration files added on this branch:
```bash
git diff origin/main --name-only --diff-filter=A | grep -i migrat
```

For each new migration file:
1. **Check the version number** — it must be exactly `last_on_main + 1` (or sequential if multiple new migrations exist)
2. **Check the file name** — it must match the naming convention exactly:
   - Snake_case description
   - Correct prefix/version format
   - Correct file extension
3. **Check the description** — it should be meaningful and describe what the migration does

#### 4d. Fix any issues found

For each migration with a wrong name or wrong version number:

```bash
git mv <old-migration-filename> <new-migration-filename>
```

If the migration content references its own version number (e.g., in Alembic `revision = "..."` or Flyway comments), update that too using the Edit tool.

Commit all renames:
```bash
git add -A
git commit -m "fix: rename migrations to correct naming convention and order"
```

### Step 5: Report Summary

Print a clear summary:

```
## Rebase + Migration Check Report

### Rebase
- Branch: <current-branch>
- Rebased on: origin/main (<short-sha>)
- Conflicts resolved: <yes/no — list files if yes>

### Migrations
- Migrations path: <path>
- Last migration on main: <V5__something.sql or "none">
- New migrations on this branch:
  - <filename> — version <N> — OK / RENAMED from <old-name>
- Issues fixed: <list renames, or "none">
- Status: ✅ All migrations are correctly named and sequentially ordered
```

If any issue could not be auto-fixed, describe it clearly so the developer can resolve it manually.
