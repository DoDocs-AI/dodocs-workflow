Creative website design generator — spawns a web-designer agent to create an award-caliber Next.js site with Tailwind CSS, then a design-validator agent to screenshot and score visual quality. Iterates until the design meets quality threshold or max iterations reached.

## Usage

```
/web-design <site-name>                          # generate 3-page site
/web-design <site-name> --pages 5                # more pages
/web-design <site-name> --port 3200              # custom port (default 3200)
/web-design <site-name> --theme "brutalist dark"  # creative direction
/web-design <site-name> --max-iterations 5       # more iteration cycles (default 3)
```

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Agent tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

When calling the Agent tool, ALWAYS include `mode: "bypassPermissions"` in the parameters.

## Workflow

You are the **orchestrator** for the `/web-design` pipeline. Follow these phases exactly.

---

### Phase W1: Creative Brief

**Goal:** Parse arguments and establish creative direction.

**Step 1 — Parse $ARGUMENTS:**
- Extract `<site-name>` — the first positional argument (required). Convert to kebab-case for `$SLUG`.
- Extract `--pages N` — number of pages (default: 3, minimum: 3)
- Extract `--port N` — dev server port (default: 3200)
- Extract `--theme "..."` — creative direction hint (optional)
- Extract `--max-iterations N` — max design/validate cycles (default: 3)

If no site-name provided, STOP: "Usage: `/web-design <site-name>` — provide a name for the site."

**Step 2 — Create output directory:**
```bash
mkdir -p docs/designs/$SLUG
```

**Step 3 — Write creative brief:**
Write `docs/designs/$SLUG/CREATIVE-BRIEF.md`:

```markdown
# Creative Brief — $SLUG

**Generated**: <timestamp>
**Pages**: $PAGES
**Port**: $PORT
**Theme Direction**: $THEME (or "Open — designer's choice")
**Max Iterations**: $MAX_ITERATIONS

## Direction

<If theme provided, expand on the creative direction — suggest mood, color families, layout approaches that fit the theme. 2-3 paragraphs of creative guidance.>

<If no theme, write an inspiring brief encouraging the designer to choose a bold, unexpected concept. Suggest 2-3 possible directions they could take.>
```

**Step 4 — Initialize STATUS:**
Write `docs/designs/$SLUG/STATUS` with content: `in-progress`

---

### Phase W2: Design

**Goal:** Create the Next.js site.

Spawn the `web-designer` agent with these variables in the prompt:

```
SLUG=$SLUG
PORT=$PORT
PAGES=$PAGES
THEME=$THEME (or empty)
ITERATION=1
FEEDBACK=(empty)

Create a stunning, award-caliber Next.js website at docs/designs/$SLUG/app/.
Read the creative brief at docs/designs/$SLUG/CREATIVE-BRIEF.md for direction.
```

Wait for the designer to complete. If it reports build errors it couldn't fix, note this for the validator.

---

### Phase W3: Visual Validation

**Goal:** Screenshot and score the design.

**Step 1 — Start dev server** (if not already running):
```bash
cd docs/designs/$SLUG/app && npm install && npx next dev --port $PORT &
```
Wait up to 15 seconds for the server to be ready (check with curl).

**Step 2 — Spawn validator:**
Spawn the `design-validator` agent:

```
SLUG=$SLUG
PORT=$PORT
ITERATION=1

Validate the website running at http://localhost:$PORT.
Take screenshots and score the design quality.
Write your report to docs/designs/$SLUG/DESIGN-VALIDATION.md.
```

**Step 3 — Read the report:**
Read `docs/designs/$SLUG/DESIGN-VALIDATION.md`.
- If **PASS** → go to Phase W4
- If **FAIL** → go to Phase W3.5

---

### Phase W3.5: Iteration Loop

**Goal:** Improve the design based on validator feedback.

**Maximum iterations**: `$MAX_ITERATIONS` (default 3). If already at max, go to Phase W4 regardless.

For each iteration (starting at 2):

**Step 1 — Extract feedback:**
Read the validation report. Extract:
- Specific scores that are low
- Issues to fix (quoted from the report)
- Strengths to preserve

**Step 2 — Re-spawn designer with feedback:**
Spawn the `web-designer` agent:

```
SLUG=$SLUG
PORT=$PORT
PAGES=$PAGES
THEME=$THEME
ITERATION=$CURRENT_ITERATION
FEEDBACK=<paste the specific issues and low scores from the validation report>

Improve the existing design at docs/designs/$SLUG/app/ based on the validator feedback.
Do NOT start from scratch — make targeted improvements to address the issues.
```

**Step 3 — Kill and restart dev server:**
```bash
# Kill existing server on $PORT
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
cd docs/designs/$SLUG/app && npx next dev --port $PORT &
```
Wait for server to be ready.

**Step 4 — Re-spawn validator:**
Spawn the `design-validator` agent:

```
SLUG=$SLUG
PORT=$PORT
ITERATION=$CURRENT_ITERATION

Validate the website running at http://localhost:$PORT.
Take screenshots and score the design quality.
Write your report to docs/designs/$SLUG/DESIGN-VALIDATION.md.
```

**Step 5 — Check result:**
- If **PASS** → go to Phase W4
- If **FAIL** and iterations remaining → loop back to Step 1
- If **FAIL** and no iterations remaining → go to Phase W4

---

### Phase W4: Final Output

**Goal:** Clean up and present results.

**Step 1 — Kill dev server:**
```bash
lsof -ti:$PORT | xargs kill -9 2>/dev/null || true
```

**Step 2 — Update STATUS:**
Read the final validation report. Write `docs/designs/$SLUG/STATUS`:
- `completed` if PASS
- `completed-below-threshold` if FAIL after max iterations

**Step 3 — Write summary:**
Write `docs/designs/$SLUG/SUMMARY.md`:

```markdown
# Web Design Summary — $SLUG

**Status**: PASS / FAIL (after N iterations)
**Final Score**: X.X / 10.0
**Pages Created**: N
**Screenshots**: docs/designs/$SLUG/screenshots/

## Design Concept
<Brief description of the concept/metaphor the designer chose>

## Pages
| Page | Route | Description |
|------|-------|-------------|
| Home | / | ... |
| About | /about | ... |
| ... | ... | ... |

## Score Progression
| Iteration | Score | Result |
|-----------|-------|--------|
| 1 | X.X | FAIL |
| 2 | X.X | FAIL |
| 3 | X.X | PASS |

## Preview Instructions

To view the site locally:
\`\`\`bash
cd docs/designs/$SLUG/app
npm install
npx next dev --port $PORT
\`\`\`

Then open http://localhost:$PORT in your browser.
```

**Step 4 — Print completion message:**
Print to the user:
```
Design complete: docs/designs/$SLUG/
  Score: X.X / 10.0 (PASS/FAIL after N iterations)
  Preview: cd docs/designs/$SLUG/app && npm install && npx next dev --port $PORT
  Screenshots: docs/designs/$SLUG/screenshots/
  Report: docs/designs/$SLUG/DESIGN-VALIDATION.md
```
