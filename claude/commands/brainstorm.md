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

No team. No git branch. No PR. Purely a thinking artifact.

---

## No Project Config Required

This command does NOT require `.claude/scrum-team-config.md`. It works in any project directory.

If a scrum-team config exists, the agent will read it for app context. If not, it continues without it.

---

## Spawn the Agent

Spawn the `brainstorm-facilitator` agent with `mode: "bypassPermissions"`:

> Feature idea: `$ARGUMENTS`
>
> Run the full brainstorm workflow:
> 1. Read `.claude/scrum-team-config.md` if it exists (for app context) — continue if missing
> 2. Research the feature space with 5–6 WebSearch queries
> 3. Challenge the user across all 5+ areas using structured AskUserQuestion calls
> 4. Run a deep-dive follow-up round on gaps and contradictions
> 5. Write the FRD to `docs/brainstorm/<feature-name>/FRD.md`

---

The feature to brainstorm: $ARGUMENTS
