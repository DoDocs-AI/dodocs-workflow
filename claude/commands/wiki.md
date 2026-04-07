Maintain a compiled knowledge layer at `docs/wiki/` — init the wiki, ingest feature docs, check coverage, or lint entries. Non-destructive: never modifies `docs/features/` or `docs/e2e-testcases/`.

## Usage

```
/wiki init                        # bootstrap docs/wiki/ structure
/wiki ingest <feature-slug>       # compile one feature's docs into a wiki entry
/wiki coverage                    # report which features are missing wiki entries
/wiki lint                        # validate all wiki entries for consistency
```

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Agent tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

When calling the Agent tool, ALWAYS include `mode: "bypassPermissions"` in the parameters.

---

## Step 0: Parse Arguments & Boot

**Parse `$ARGUMENTS`:**
- First token → `WIKI_CMD` (one of: `init`, `ingest`, `coverage`, `lint`)
- Second token (if present) → `FEATURE_SLUG`

If `WIKI_CMD` is empty or not one of the four valid values, STOP and print:
```
Usage: /wiki <init|ingest|coverage|lint> [feature-slug]
  init                 — bootstrap docs/wiki/ directory structure
  ingest <slug>        — compile docs/features/<slug>/ into docs/wiki/<slug>.md
  coverage             — list features missing wiki entries
  lint                 — validate all existing wiki entries
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

Run `/wiki ingest <feature-slug>` to add your first entry.
```

---

## Sub-command: `ingest`

**Trigger**: `WIKI_CMD == "ingest"`

If `FEATURE_SLUG` is empty, STOP:
> "Usage: `/wiki ingest <feature-slug>` — provide the slug of the feature to ingest."

Check that `docs/features/$FEATURE_SLUG/` exists. If it does not exist, STOP:
> "Feature directory not found: `docs/features/$FEATURE_SLUG/`. Check the slug and try again."

Check that `docs/wiki/` exists (wiki must be initialized). If it does not exist, STOP:
> "Wiki not initialized. Run `/wiki init` first."

Spawn the `wiki-maintainer` agent (`mode: "bypassPermissions"`) with this prompt:

```
WIKI_TASK=ingest
APP_NAME=<APP_NAME from config>
FEATURE_SLUG=<FEATURE_SLUG>
FEATURE_DIR=docs/features/<FEATURE_SLUG>
WIKI_DIR=docs/wiki
WIKI_ENTRY=docs/wiki/<FEATURE_SLUG>.md

Ingest the feature docs into the wiki. Follow the TASK: INGEST instructions in your system prompt.
```

After the agent completes, print:
```
Wiki entry created: docs/wiki/<FEATURE_SLUG>.md
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
# List all feature slugs
FEATURES=$(ls docs/features/ 2>/dev/null | sort)
# List all wiki entry slugs (exclude special files)
WIKI=$(ls docs/wiki/*.md 2>/dev/null | xargs -I{} basename {} .md | grep -v '^README$' | grep -v '^COVERAGE$' | grep -v '^_template$' | sort)

echo "=== Wiki Coverage Report ==="
echo ""
echo "Features with wiki entries:"
for slug in $FEATURES; do
  if echo "$WIKI" | grep -q "^${slug}$"; then
    echo "  [x] $slug"
  fi
done

echo ""
echo "Features MISSING wiki entries:"
MISSING=0
for slug in $FEATURES; do
  if ! echo "$WIKI" | grep -q "^${slug}$"; then
    echo "  [ ] $slug"
    MISSING=$((MISSING + 1))
  fi
done

echo ""
TOTAL=$(echo "$FEATURES" | wc -l | tr -d ' ')
COVERED=$((TOTAL - MISSING))
echo "Coverage: $COVERED / $TOTAL features"

if [ "$MISSING" -gt 0 ]; then
  echo ""
  echo "Run: /wiki ingest <slug>  for each missing feature."
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
Fix issues by re-running: /wiki ingest <feature-slug>
```
