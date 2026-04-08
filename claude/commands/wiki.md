Maintain a compiled knowledge layer at `docs/wiki/` — init the wiki, ingest any docs from the `docs/` folder, check coverage, or lint entries. Non-destructive: never modifies source doc directories.

## Usage

```
/wiki init                        # bootstrap docs/wiki/ structure
/wiki ingest <doc-path>           # compile any docs/  into a wiki entry
/wiki coverage                    # report which doc directories are missing wiki entries
/wiki lint                        # validate all wiki entries for consistency
```

`<doc-path>` is a path relative to `docs/` — examples:
- `features/my-feature`  → reads `docs/features/my-feature/`
- `plc/my-project/build` → reads `docs/plc/my-project/build/`
- `api`                  → reads `docs/api/`
- `my-feature`           → backward-compat: falls back to `docs/features/my-feature/`

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Agent tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

When calling the Agent tool, ALWAYS include `mode: "bypassPermissions"` in the parameters.

---

## Step 0: Parse Arguments & Boot

**Parse `$ARGUMENTS`:**
- First token → `WIKI_CMD` (one of: `init`, `ingest`, `coverage`, `lint`)
- Remaining tokens joined → `INPUT_PATH`

If `WIKI_CMD` is empty or not one of the four valid values, STOP and print:
```
Usage: /wiki <init|ingest|coverage|lint> [doc-path]
  init                 — bootstrap docs/wiki/ directory structure
  ingest <doc-path>    — compile docs/<doc-path>/ into docs/wiki/<entry-slug>.md
  coverage             — list doc directories missing wiki entries
  lint                 — validate all existing wiki entries

<doc-path> examples: features/my-feature, plc/my-project, api
Bare slug (no /) falls back to docs/features/<slug>/ for backward compat.
```

**Read config:**
Read `.claude/scrum-team-config.md`. If it does not exist, STOP:
> "No scrum-team config found. Run `dodocs-workflow init` or copy the template to `.claude/scrum-team-config.md`."

Extract `APP_NAME` from the config.

---

## Sub-command: `init`

**Trigger**: `WIKI_CMD == "init"`

Spawn the `wiki-maintainer` agent (`mode: "bypassPermissions"`) with this prompt:

```
WIKI_TASK=init
APP_NAME=<APP_NAME from config>
WIKI_DIR=docs/wiki

Initialize the project wiki. Follow the TASK: INIT instructions in your system prompt.
```

After the agent completes, print:
```
Wiki initialized at docs/wiki/
  docs/wiki/README.md       — index
  docs/wiki/COVERAGE.md     — coverage tracker
  docs/wiki/_template.md    — entry template

Run `/wiki ingest <doc-path>` to add your first entry.
Examples:
  /wiki ingest features/my-feature
  /wiki ingest plc/my-project
  /wiki ingest api
```

---

## Sub-command: `ingest`

**Trigger**: `WIKI_CMD == "ingest"`

If `INPUT_PATH` is empty, STOP:
> "Usage: `/wiki ingest <doc-path>` — provide a path relative to `docs/` (e.g. `features/my-feature`, `plc/my-project`, `api`)."

**Resolve source directory and entry slug:**

1. If `docs/$INPUT_PATH/` exists as a directory:
   - `SOURCE_DIR = docs/$INPUT_PATH`
   - `ENTRY_SLUG` = `$INPUT_PATH` with all `/` replaced by `-`

2. Else if `$INPUT_PATH` contains no `/` and `docs/features/$INPUT_PATH/` exists (backward compat):
   - `SOURCE_DIR = docs/features/$INPUT_PATH`
   - `ENTRY_SLUG = $INPUT_PATH`

3. Otherwise STOP:
   > "Directory not found: `docs/$INPUT_PATH/`. Check the path and try again."

Check that `docs/wiki/` exists (wiki must be initialized). If it does not exist, STOP:
> "Wiki not initialized. Run `/wiki init` first."

Spawn the `wiki-maintainer` agent (`mode: "bypassPermissions"`) with this prompt:

```
WIKI_TASK=ingest
APP_NAME=<APP_NAME from config>
INPUT_PATH=<INPUT_PATH>
SOURCE_DIR=<SOURCE_DIR>
ENTRY_SLUG=<ENTRY_SLUG>
WIKI_DIR=docs/wiki
WIKI_ENTRY=docs/wiki/<ENTRY_SLUG>.md

Ingest the documentation into the wiki. Follow the TASK: INGEST instructions in your system prompt.
```

After the agent completes, print:
```
Wiki entry created: docs/wiki/<ENTRY_SLUG>.md
Coverage updated:  docs/wiki/COVERAGE.md
Index updated:     docs/wiki/README.md

Run `/wiki lint` to validate all entries.
```

---

## Sub-command: `coverage`

**Trigger**: `WIKI_CMD == "coverage"`

Check that `docs/wiki/` exists. If it does not exist, STOP:
> "Wiki not initialized. Run `/wiki init` first."

Run this directly (no agent needed):

```bash
# Collect all doc directories (any dir under docs/ that contains .md files, excluding docs/wiki/)
DOC_DIRS=$(find docs/ -mindepth 1 -type d ! -path 'docs/wiki' ! -path 'docs/wiki/*' 2>/dev/null | while read d; do
  if ls "$d"/*.md >/dev/null 2>&1; then
    # Produce path relative to docs/
    echo "${d#docs/}"
  fi
done | sort)

# Build wiki slug list (exclude special files)
WIKI=$(ls docs/wiki/*.md 2>/dev/null | xargs -I{} basename {} .md | grep -v '^README$' | grep -v '^COVERAGE$' | grep -v '^LINT-REPORT$' | grep -v '^_template$' | sort)

echo "=== Wiki Coverage Report ==="
echo ""
echo "Doc directories with wiki entries:"
for rel_path in $DOC_DIRS; do
  slug=$(echo "$rel_path" | tr '/' '-')
  if echo "$WIKI" | grep -q "^${slug}$"; then
    echo "  [x] $rel_path  →  docs/wiki/${slug}.md"
  fi
done

echo ""
echo "Doc directories MISSING wiki entries:"
MISSING=0
for rel_path in $DOC_DIRS; do
  slug=$(echo "$rel_path" | tr '/' '-')
  if ! echo "$WIKI" | grep -q "^${slug}$"; then
    echo "  [ ] $rel_path"
    MISSING=$((MISSING + 1))
  fi
done

echo ""
TOTAL=$(echo "$DOC_DIRS" | grep -c . || echo 0)
COVERED=$((TOTAL - MISSING))
echo "Coverage: $COVERED / $TOTAL doc directories"

if [ "$MISSING" -gt 0 ]; then
  echo ""
  echo "Run: /wiki ingest <doc-path>  for each missing directory."
  echo "Example slugs missing:"
  for rel_path in $DOC_DIRS; do
    slug=$(echo "$rel_path" | tr '/' '-')
    if ! echo "$WIKI" | grep -q "^${slug}$"; then
      echo "  /wiki ingest $rel_path"
    fi
  done | head -5
fi
```

Print the output directly to the user. Do not spawn an agent.

---

## Sub-command: `lint`

**Trigger**: `WIKI_CMD == "lint"`

Check that `docs/wiki/` exists. If it does not exist, STOP:
> "Wiki not initialized. Run `/wiki init` first."

Spawn the `wiki-maintainer` agent (`mode: "bypassPermissions"`) with this prompt:

```
WIKI_TASK=lint
APP_NAME=<APP_NAME from config>
WIKI_DIR=docs/wiki

Lint all wiki entries for consistency. Follow the TASK: LINT instructions in your system prompt.
```

After the agent completes, print the lint report summary returned by the agent. If there were issues, remind the user:
```
Fix issues by re-running: /wiki ingest <doc-path>
```
