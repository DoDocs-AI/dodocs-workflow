Orchestrate the full GTM Agent Team — 16 agents across 6 phases producing a complete Go-To-Market strategy and execution plan.

## MANDATORY: Agent Execution Mode

**CRITICAL**: Every agent you spawn via the Agent tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution.

Spawn all agents automatically as their phase begins — do NOT ask the user for permission.

<boot>
BEFORE doing anything else:

**Step 1 — Parse $ARGUMENTS:**
- Extract flags first, then treat the remainder as the product name.
- If `--auto` is present: set AUTO_MODE=true; otherwise AUTO_MODE=false.
- Strip all parsed flags from $ARGUMENTS to obtain the clean product name.

**Step 2 — Derive slug:**
- Convert product name to kebab-case, max 40 characters.
- Example: "My Cool Product" → `my-cool-product`

**Step 3 — Create directory and progress tracker:**
```bash
mkdir -p docs/gtm/<slug>
```

Write `docs/gtm/<slug>/GTM-PROGRESS.md`:

```markdown
# GTM Progress: <Product Name>

## Current Phase
Phase 1 — Strategy

## Phase Status

| Phase | Status | Agent(s) | Outputs | Approval |
|-------|--------|----------|---------|----------|
| Phase 1: Strategy | In Progress | gtm-strategist | GTM-STRATEGY.md | Pending |
| Phase 2: Research | Pending | market-research, icp-discovery, trend-monitor | COMPETITIVE-ANALYSIS.md, BATTLE-CARDS.md, ICP-PROFILES.md, PROSPECT-LIST.md, TREND-DIGEST.md | Pending |
| Phase 3: Content | Pending | copywriter, seo-content, localization | content/*.md, SEO-KEYWORD-REPORT.md, CONTENT-CLUSTER-MAP.md | Pending |
| Phase 4: Demand Gen | Pending | outbound, paid-ads, community | OUTBOUND-*.md, PAID-ADS-PLAN.md, COMMUNITY-PLAN.md | Pending |
| Phase 5: Sales Enablement | Pending | lead-scoring, crm, proposal | LEAD-SCORING-MODEL.md, CRM-SETUP.md, PROPOSAL-TEMPLATE.md, ROI-CALCULATOR.md | Pending |
| Phase 6: Analytics | Pending | metrics, experiment, reporting | KPI-DASHBOARD.md, EXPERIMENT-*.md, *-TEMPLATE.md | Pending |

## Timeline
- Started: <timestamp>

## Approval Log
<!-- Approval decisions are logged here -->
```
</boot>

## Phase 1: Strategy (1 agent)

Spawn `gtm-strategist` with `mode: "bypassPermissions"`:
- Prompt: "Create a GTM strategy for '<product-name>'. Write all output to `docs/gtm/<slug>/`. You are part of the GTM Agent Team. Include a machine-readable `## Agent Task Assignments` section at the end of GTM-STRATEGY.md that maps each downstream agent to their specific focus areas from the strategy."
- If AUTO_MODE=true: append "AUTO_MODE=true — do NOT ask the user any questions. Make reasonable assumptions based on research and state all assumptions explicitly." to the prompt.

**Validate**: Read `docs/gtm/<slug>/GTM-STRATEGY.md` — must exist and contain sections: ICP, Positioning, Channel Strategy.
If missing or incomplete, re-spawn gtm-strategist with: "GTM-STRATEGY.md is incomplete. Regenerate with all required sections."

Update GTM-PROGRESS.md: Phase 1 → Done, Phase 2 → In Progress.

### Approval Gate — Phase 1

**If AUTO_MODE=true:** Update the Approval column for Phase 1 → "Auto-approved". Append to Approval Log: `- Phase 1: Auto-approved (<timestamp>)`. Proceed to Phase 2.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/gtm/<slug>/GTM-STRATEGY.md` (by gtm-strategist)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 2 (Research)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 1: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user what to fix in GTM-STRATEGY.md. Re-spawn `gtm-strategist` with the original prompt plus the user's revision feedback. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 1: Skipped (<timestamp>)`. Set PHASE_1_SKIPPED=true. Proceed.

---

## Phase 2: Research (3 agents in parallel)

**Skip-awareness:** If PHASE_1_SKIPPED=true, append to each agent's prompt: "Note: Phase 1 (Strategy) was skipped. GTM-STRATEGY.md may not exist. Use your best judgment to infer strategy from the product name."

Spawn all 3 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-market-research**: "Analyze the competitive landscape for the product described in `docs/gtm/<slug>/GTM-STRATEGY.md`. Write COMPETITIVE-ANALYSIS.md and BATTLE-CARDS.md to `docs/gtm/<slug>/`."

2. **gtm-icp-discovery**: "Build detailed ICP profiles and prospect list based on `docs/gtm/<slug>/GTM-STRATEGY.md`. Write ICP-PROFILES.md and PROSPECT-LIST.md to `docs/gtm/<slug>/`."

3. **gtm-trend-monitor**: "Monitor market trends and signals relevant to the product in `docs/gtm/<slug>/GTM-STRATEGY.md`. Write TREND-DIGEST.md to `docs/gtm/<slug>/`."

**Validate**: Check that COMPETITIVE-ANALYSIS.md, ICP-PROFILES.md, and TREND-DIGEST.md exist.

Update GTM-PROGRESS.md: Phase 2 → Done, Phase 3 → In Progress.

### Approval Gate — Phase 2

**If AUTO_MODE=true:** Update the Approval column for Phase 2 → "Auto-approved". Append to Approval Log: `- Phase 2: Auto-approved (<timestamp>)`. Proceed to Phase 3.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/gtm/<slug>/COMPETITIVE-ANALYSIS.md` (by gtm-market-research)
   - `docs/gtm/<slug>/BATTLE-CARDS.md` (by gtm-market-research)
   - `docs/gtm/<slug>/ICP-PROFILES.md` (by gtm-icp-discovery)
   - `docs/gtm/<slug>/PROSPECT-LIST.md` (by gtm-icp-discovery)
   - `docs/gtm/<slug>/TREND-DIGEST.md` (by gtm-trend-monitor)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 3 (Content)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 2: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-market-research` → COMPETITIVE-ANALYSIS.md, BATTLE-CARDS.md
     - `gtm-icp-discovery` → ICP-PROFILES.md, PROSPECT-LIST.md
     - `gtm-trend-monitor` → TREND-DIGEST.md
     Re-spawn only the named agent(s) with the original prompt plus the user's revision feedback. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 2: Skipped (<timestamp>)`. Set PHASE_2_SKIPPED=true. Proceed.

---

## Phase 3: Content & Messaging (3 agents in parallel)

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_1_SKIPPED: "Note: Phase 1 (Strategy) was skipped. GTM-STRATEGY.md may not exist."
- If PHASE_2_SKIPPED: "Note: Phase 2 (Research) was skipped. COMPETITIVE-ANALYSIS.md, ICP-PROFILES.md, TREND-DIGEST.md, etc. may not exist."

Spawn all 3 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-copywriter**: "Create all marketing copy for the product in `docs/gtm/<slug>/`. Read GTM-STRATEGY.md and all Phase 2 outputs. Write to `docs/gtm/<slug>/content/`: LANDING-PAGE.md, EMAIL-SEQUENCES.md, AD-COPY.md, LINKEDIN-POSTS.md, SALES-ONEPAGER.md."

2. **gtm-seo-content**: "Build an SEO content strategy for the product in `docs/gtm/<slug>/`. Read GTM-STRATEGY.md and ICP-PROFILES.md. Write SEO-KEYWORD-REPORT.md, CONTENT-CLUSTER-MAP.md to `docs/gtm/<slug>/`, and blog posts to `docs/gtm/<slug>/content/blog/`."

3. **gtm-localization**: "Localize all content for the product in `docs/gtm/<slug>/`. Read content files from `docs/gtm/<slug>/content/`. Write localized versions to `docs/gtm/<slug>/content/localized/<lang>/`."

**Validate**: Check that `docs/gtm/<slug>/content/` directory exists with at least LANDING-PAGE.md.

Update GTM-PROGRESS.md: Phase 3 → Done, Phase 4 → In Progress.

### Approval Gate — Phase 3

**If AUTO_MODE=true:** Update the Approval column for Phase 3 → "Auto-approved". Append to Approval Log: `- Phase 3: Auto-approved (<timestamp>)`. Proceed to Phase 4.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/gtm/<slug>/content/LANDING-PAGE.md` (by gtm-copywriter)
   - `docs/gtm/<slug>/content/EMAIL-SEQUENCES.md` (by gtm-copywriter)
   - `docs/gtm/<slug>/content/AD-COPY.md` (by gtm-copywriter)
   - `docs/gtm/<slug>/content/LINKEDIN-POSTS.md` (by gtm-copywriter)
   - `docs/gtm/<slug>/content/SALES-ONEPAGER.md` (by gtm-copywriter)
   - `docs/gtm/<slug>/SEO-KEYWORD-REPORT.md` (by gtm-seo-content)
   - `docs/gtm/<slug>/CONTENT-CLUSTER-MAP.md` (by gtm-seo-content)
   - `docs/gtm/<slug>/content/blog/` (by gtm-seo-content)
   - `docs/gtm/<slug>/content/localized/` (by gtm-localization)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 4 (Demand Gen)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 3: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-copywriter` → content/LANDING-PAGE.md, EMAIL-SEQUENCES.md, AD-COPY.md, LINKEDIN-POSTS.md, SALES-ONEPAGER.md
     - `gtm-seo-content` → SEO-KEYWORD-REPORT.md, CONTENT-CLUSTER-MAP.md, content/blog/
     - `gtm-localization` → content/localized/
     Re-spawn only the named agent(s) with the original prompt plus the user's revision feedback. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 3: Skipped (<timestamp>)`. Set PHASE_3_SKIPPED=true. Proceed.

---

## Phase 4: Demand Generation (3 agents in parallel)

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_1_SKIPPED: "Note: Phase 1 (Strategy) was skipped. GTM-STRATEGY.md may not exist."
- If PHASE_2_SKIPPED: "Note: Phase 2 (Research) was skipped. ICP-PROFILES.md and other research outputs may not exist."
- If PHASE_3_SKIPPED: "Note: Phase 3 (Content) was skipped. Content files in content/ may not exist."

Spawn all 3 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-outbound**: "Create outbound sales playbook for the product in `docs/gtm/<slug>/`. Read all upstream docs. Write OUTBOUND-SEQUENCES.md, OUTBOUND-PLAYBOOK.md, LINKEDIN-DM-TEMPLATES.md to `docs/gtm/<slug>/`."

2. **gtm-paid-ads**: "Design paid advertising plan for the product in `docs/gtm/<slug>/`. Read GTM-STRATEGY.md and AD-COPY.md. Write PAID-ADS-PLAN.md to `docs/gtm/<slug>/`."

3. **gtm-community**: "Plan community engagement strategy for the product in `docs/gtm/<slug>/`. Read ICP-PROFILES.md. Write COMMUNITY-PLAN.md to `docs/gtm/<slug>/`."

Update GTM-PROGRESS.md: Phase 4 → Done, Phase 5 → In Progress.

### Approval Gate — Phase 4

**If AUTO_MODE=true:** Update the Approval column for Phase 4 → "Auto-approved". Append to Approval Log: `- Phase 4: Auto-approved (<timestamp>)`. Proceed to Phase 5.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/gtm/<slug>/OUTBOUND-SEQUENCES.md` (by gtm-outbound)
   - `docs/gtm/<slug>/OUTBOUND-PLAYBOOK.md` (by gtm-outbound)
   - `docs/gtm/<slug>/LINKEDIN-DM-TEMPLATES.md` (by gtm-outbound)
   - `docs/gtm/<slug>/PAID-ADS-PLAN.md` (by gtm-paid-ads)
   - `docs/gtm/<slug>/COMMUNITY-PLAN.md` (by gtm-community)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 5 (Sales Enablement)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 4: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-outbound` → OUTBOUND-SEQUENCES.md, OUTBOUND-PLAYBOOK.md, LINKEDIN-DM-TEMPLATES.md
     - `gtm-paid-ads` → PAID-ADS-PLAN.md
     - `gtm-community` → COMMUNITY-PLAN.md
     Re-spawn only the named agent(s) with the original prompt plus the user's revision feedback. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 4: Skipped (<timestamp>)`. Set PHASE_4_SKIPPED=true. Proceed.

---

## Phase 5: Sales Enablement (3 agents in parallel)

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_1_SKIPPED: "Note: Phase 1 (Strategy) was skipped. GTM-STRATEGY.md may not exist."
- If PHASE_2_SKIPPED: "Note: Phase 2 (Research) was skipped. ICP-PROFILES.md and other research outputs may not exist."
- If PHASE_3_SKIPPED: "Note: Phase 3 (Content) was skipped. Content files may not exist."
- If PHASE_4_SKIPPED: "Note: Phase 4 (Demand Gen) was skipped. Outbound and ads outputs may not exist."

Spawn all 3 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-lead-scoring**: "Design lead scoring model for the product in `docs/gtm/<slug>/`. Read GTM-STRATEGY.md and ICP-PROFILES.md. Write LEAD-SCORING-MODEL.md to `docs/gtm/<slug>/`."

2. **gtm-crm**: "Design CRM setup for the product in `docs/gtm/<slug>/`. Read GTM-STRATEGY.md. Write CRM-SETUP.md to `docs/gtm/<slug>/`."

3. **gtm-proposal**: "Create sales proposal templates for the product in `docs/gtm/<slug>/`. Read all upstream docs. Write PROPOSAL-TEMPLATE.md, ROI-CALCULATOR.md, EXECUTIVE-SUMMARY-TEMPLATE.md to `docs/gtm/<slug>/`."

Update GTM-PROGRESS.md: Phase 5 → Done, Phase 6 → In Progress.

### Approval Gate — Phase 5

**If AUTO_MODE=true:** Update the Approval column for Phase 5 → "Auto-approved". Append to Approval Log: `- Phase 5: Auto-approved (<timestamp>)`. Proceed to Phase 6.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/gtm/<slug>/LEAD-SCORING-MODEL.md` (by gtm-lead-scoring)
   - `docs/gtm/<slug>/CRM-SETUP.md` (by gtm-crm)
   - `docs/gtm/<slug>/PROPOSAL-TEMPLATE.md` (by gtm-proposal)
   - `docs/gtm/<slug>/ROI-CALCULATOR.md` (by gtm-proposal)
   - `docs/gtm/<slug>/EXECUTIVE-SUMMARY-TEMPLATE.md` (by gtm-proposal)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 6 (Analytics)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 5: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-lead-scoring` → LEAD-SCORING-MODEL.md
     - `gtm-crm` → CRM-SETUP.md
     - `gtm-proposal` → PROPOSAL-TEMPLATE.md, ROI-CALCULATOR.md, EXECUTIVE-SUMMARY-TEMPLATE.md
     Re-spawn only the named agent(s) with the original prompt plus the user's revision feedback. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 5: Skipped (<timestamp>)`. Set PHASE_5_SKIPPED=true. Proceed.

---

## Phase 6: Analytics Setup (3 agents in parallel)

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_1_SKIPPED: "Note: Phase 1 (Strategy) was skipped. GTM-STRATEGY.md may not exist."
- If PHASE_2_SKIPPED: "Note: Phase 2 (Research) was skipped. Research outputs may not exist."
- If PHASE_3_SKIPPED: "Note: Phase 3 (Content) was skipped. Content files may not exist."
- If PHASE_4_SKIPPED: "Note: Phase 4 (Demand Gen) was skipped. Demand gen outputs may not exist."
- If PHASE_5_SKIPPED: "Note: Phase 5 (Sales Enablement) was skipped. Sales enablement outputs may not exist."

Spawn all 3 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-metrics**: "Design KPI dashboard for the product in `docs/gtm/<slug>/`. Read all upstream docs. Write KPI-DASHBOARD.md to `docs/gtm/<slug>/`."

2. **gtm-experiment**: "Design experiment framework for the product in `docs/gtm/<slug>/`. Read KPI-DASHBOARD.md and all outputs. Write EXPERIMENT-BACKLOG.md and EXPERIMENT-FRAMEWORK.md to `docs/gtm/<slug>/`."

3. **gtm-reporting**: "Create reporting templates for the product in `docs/gtm/<slug>/`. Read all docs. Write WEEKLY-DIGEST-TEMPLATE.md and MONTHLY-REPORT-TEMPLATE.md to `docs/gtm/<slug>/`."

Update GTM-PROGRESS.md: Phase 6 → Done.

### Approval Gate — Phase 6

**If AUTO_MODE=true:** Update the Approval column for Phase 6 → "Auto-approved". Append to Approval Log: `- Phase 6: Auto-approved (<timestamp>)`. Proceed to Completion.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/gtm/<slug>/KPI-DASHBOARD.md` (by gtm-metrics)
   - `docs/gtm/<slug>/EXPERIMENT-BACKLOG.md` (by gtm-experiment)
   - `docs/gtm/<slug>/EXPERIMENT-FRAMEWORK.md` (by gtm-experiment)
   - `docs/gtm/<slug>/WEEKLY-DIGEST-TEMPLATE.md` (by gtm-reporting)
   - `docs/gtm/<slug>/MONTHLY-REPORT-TEMPLATE.md` (by gtm-reporting)

2. Use AskUserQuestion with these options:
   - "Approve — finalize GTM package"
   - "Request changes — I'll describe what to fix"
   - "Skip — finalize without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 6: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-metrics` → KPI-DASHBOARD.md
     - `gtm-experiment` → EXPERIMENT-BACKLOG.md, EXPERIMENT-FRAMEWORK.md
     - `gtm-reporting` → WEEKLY-DIGEST-TEMPLATE.md, MONTHLY-REPORT-TEMPLATE.md
     Re-spawn only the named agent(s) with the original prompt plus the user's revision feedback. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 6: Skipped (<timestamp>)`. Proceed.

---

## Completion

After all phases complete:

1. List all files produced in `docs/gtm/<slug>/` using `ls -R`.
2. Update GTM-PROGRESS.md with completion timestamp.
3. Print a summary (include approval status for each phase):

```
GTM Team Complete for <Product Name>

Output directory: docs/gtm/<slug>/

Phase 1 (Strategy):        GTM-STRATEGY.md [<Approval Status>]
Phase 2 (Research):        COMPETITIVE-ANALYSIS.md, BATTLE-CARDS.md, ICP-PROFILES.md, PROSPECT-LIST.md, TREND-DIGEST.md [<Approval Status>]
Phase 3 (Content):         content/ directory with landing page, emails, ads, LinkedIn posts, SEO content [<Approval Status>]
Phase 4 (Demand Gen):      OUTBOUND-SEQUENCES.md, OUTBOUND-PLAYBOOK.md, LINKEDIN-DM-TEMPLATES.md, PAID-ADS-PLAN.md, COMMUNITY-PLAN.md [<Approval Status>]
Phase 5 (Sales):           LEAD-SCORING-MODEL.md, CRM-SETUP.md, PROPOSAL-TEMPLATE.md, ROI-CALCULATOR.md [<Approval Status>]
Phase 6 (Analytics):       KPI-DASHBOARD.md, EXPERIMENT-BACKLOG.md, EXPERIMENT-FRAMEWORK.md, reporting templates [<Approval Status>]

Total agents used: 16
Total documents produced: 24+
```

The GTM strategy and execution plan for $ARGUMENTS
