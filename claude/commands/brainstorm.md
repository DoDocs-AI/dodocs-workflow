Stress-test a feature idea through structured research and adversarial questioning, then produce a Feature Requirements Document (FRD).

## Usage

```
/brainstorm <feature idea>
```

**Examples:**
```
/brainstorm add user authentication
/brainstorm real-time collaboration on documents
/brainstorm AI-powered search with semantic matching
```

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: The agent you spawn via the Task tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

---

## What This Command Does

This is a **discovery-only** command. It does NOT build anything.

It runs the `brainstorm-facilitator` agent which will:

1. **Research the space** — run 5–6 WebSearch queries on best practices, existing solutions, common pitfalls, user needs, and technical approaches
2. **Challenge you across 5+ areas** — Problem Clarity, User & Market Fit, Competitive Landscape, Technical Feasibility, Edge Cases, Success Metrics, Scope & MVP
3. **Dig into gaps** — follow-up round targeting contradictions and unaddressed risks
4. **Produce a FRD** — written to `docs/brainstorm/<feature-name>/FRD.md`

Then this command runs a **requirements quality loop** over the FRD: two critics (UX + business)
score it, an enricher auto-resolves gaps, and you approve the hardened result at a final gate.

No team. No git branch. No PR. Purely a thinking artifact.

---

## No Project Config Required

This command does NOT require `.claude/scrum-team-config.md`. It works in any project directory.

If a scrum-team config exists, the agent will read it for app context. If not, it continues without it.

---

## Step 1 — Spawn the Facilitator

Spawn the `brainstorm-facilitator` agent with `mode: "bypassPermissions"`:

> Feature idea: `$ARGUMENTS`
>
> Run the full brainstorm workflow:
> 1. Read `.claude/scrum-team-config.md` if it exists (for app context) — continue if missing
> 2. Research the feature space with 5–6 WebSearch queries
> 3. Challenge the user across all 5+ areas using structured AskUserQuestion calls
> 4. Run a deep-dive follow-up round on gaps and contradictions
> 5. Write the FRD to `docs/brainstorm/<feature-name>/FRD.md`
> 6. Report back the exact `<feature-name>` you used and the FRD path.

Capture the `<feature-name>` from the facilitator's report. Set:
`REQ_DOC=docs/brainstorm/<feature-name>/FRD.md`, `OUTPUT_DIR=docs/brainstorm/<feature-name>/`, `DOC_TYPE=frd`.

---

## Step 2 — Requirements Quality Loop

Auto-refine the FRD against UX and business quality bars, then a human gate. Run up to
**3 iterations** of score → gate → enrich.

**Score (parallel)** — spawn BOTH critics in a single message (two Task calls), each with
`mode: "bypassPermissions"`:
```
ux-requirements-critic:
  Read ~/.claude/agents/ux-requirements-critic.md and execute it.
  REQ_DOC=docs/brainstorm/<feature-name>/FRD.md
  OUTPUT_DIR=docs/brainstorm/<feature-name>/
  DOC_TYPE=frd

business-requirements-critic:
  Read ~/.claude/agents/business-requirements-critic.md and execute it.
  REQ_DOC=docs/brainstorm/<feature-name>/FRD.md
  OUTPUT_DIR=docs/brainstorm/<feature-name>/
  DOC_TYPE=frd
```
Wait for both. Read `REQ-UX-REVIEW.md` and `REQ-BUSINESS-REVIEW.md`. Remember the first-round
weighted averages for the before→after summary.

**Gate:** PASS only if **both** reports show `PASS`.

**If FAIL:** spawn `requirements-enricher` (`mode: "bypassPermissions"`) with the same
`REQ_DOC` / `OUTPUT_DIR` / `DOC_TYPE=frd`, wait, then re-score. After 3 iterations without a
double-PASS, stop and proceed to the gate anyway, logging unresolved Critical/High findings.

Write `docs/brainstorm/<feature-name>/REQUIREMENTS-VALIDATION.md` (same format as in
`/prepare-feature`: before→after score table, iterations run, assumptions made, unresolved findings).

---

## Step 3 — Human Gate

Print the consolidated table and the enricher's `## Assumptions` list from the FRD, then:
```
AskUserQuestion:
  "FRD hardened (UX <Y.Y>/5, Business <Y.Y>/5). The enricher made the assumptions listed above.
   How would you like to proceed?"
  Options:
    - "Approve — the FRD is ready"
    - "Edit assumptions" — I'll edit the FRD, then we're done
    - "Re-run the quality loop"
```
- **Approve:** print the FRD path and a one-line summary of the score lift. Done.
- **Edit assumptions:** print the FRD path, wait for "continue", then finish.
- **Re-run the quality loop:** restart Step 2 from the score round (resets the iteration counter).

---

The feature to brainstorm: $ARGUMENTS
