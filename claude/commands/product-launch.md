Orchestrate the Product Launch pipeline — 15+ agents across 10 phases taking a product idea from zero to first dollar and beyond (Idea → Build → Test → Prod → Iterate).

## MANDATORY: Agent Execution Mode

**CRITICAL**: Every agent you spawn via the Agent tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution.

Spawn all agents automatically as their phase begins — do NOT ask the user for permission.

<boot>
BEFORE doing anything else:

**Step 1 — Parse $ARGUMENTS:**
- Extract flags first, then treat the remainder as the product name.
- If `--auto` is present: set AUTO_MODE=true; otherwise AUTO_MODE=false.
- If `--skip-build` is present: set SKIP_BUILD=true; otherwise SKIP_BUILD=false.
- If `--skip-test` is present: set SKIP_TEST=true; otherwise SKIP_TEST=false.
- If `--skip-smoke` is present: set SKIP_SMOKE=true; otherwise SKIP_SMOKE=false.
- If `--skip-iterate` is present: set SKIP_ITERATE=true; otherwise SKIP_ITERATE=false.
- If `--prod-url <url>` is present: set PROD_URL=<url>; otherwise PROD_URL=unset.
- Strip all parsed flags from $ARGUMENTS to obtain the clean product name.

**Step 2 — Derive slug:**
- Convert product name to kebab-case, max 40 characters.
- Example: "My Cool Product" → `my-cool-product`

**Step 3 — Create directory structure and progress tracker:**
```bash
mkdir -p docs/launch/<slug>/presell docs/launch/<slug>/mvp docs/launch/<slug>/monetize docs/launch/<slug>/launch/content/blog docs/launch/<slug>/optimize docs/launch/<slug>/build docs/launch/<slug>/audit docs/launch/<slug>/iterate
```

Write `docs/launch/<slug>/LAUNCH-PROGRESS.md`:

```markdown
# Launch Progress: <Product Name>

## Current Phase
Phase 0 — Validate

## Phase Status

| Phase | Status | Agent(s) | Outputs | Approval |
|-------|--------|----------|---------|----------|
| Phase 0: Validate | In Progress | gtm-strategist, gtm-market-research, gtm-icp-discovery | GTM-STRATEGY.md, COMPETITIVE-ANALYSIS.md, ICP-PROFILES.md, PROSPECT-LIST.md | Pending |
| Phase 1: Pre-sell | Pending | gtm-copywriter, gtm-outbound | presell/LANDING-PAGE.md, presell/PAYMENT-SETUP.md, presell/OUTBOUND-TEMPLATES.md | Pending |
| Phase 2: Spec MVP | Pending | product-owner, architect | mvp/MVP-SPEC.md, mvp/ARCHITECTURE.md | Pending |
| Phase 3: Build MVP | Pending | /scrum-team (delegated) | build/BUILD-SUMMARY.md | Pending |
| Phase 4: Audit & Harden | Pending | /prepare-for-production (delegated) | audit/AUDIT-STATUS.md | Pending |
| Phase 5: Monetize | Pending | gtm-proposal, gtm-crm, gtm-copywriter | monetize/PRICING-STRATEGY.md, monetize/ROI-CALCULATOR.md, monetize/CRM-SETUP.md, monetize/EMAIL-TEMPLATES.md | Pending |
| Phase 6: Launch & Distribute | Pending | gtm-seo-content, gtm-community, gtm-outbound, gtm-paid-ads, gtm-copywriter | launch/ directory | Pending |
| Phase 7: Prod Smoke Test | Pending | manual-tester | build/SMOKE-TEST-RESULTS.md | Pending |
| Phase 8: Optimize & Scale | Pending | gtm-metrics, gtm-experiment, gtm-lead-scoring, gtm-reporting | optimize/ directory | Pending |
| Phase 9: Feature Invention | Pending | brainstorm-facilitator | iterate/NEXT-FEATURES.md | Pending |

## Timeline
- Started: <timestamp>

## Approval Log
<!-- Approval decisions are logged here -->
```
</boot>

## Phase 0: Validate (1 sequential + 2 parallel)

### Step 1: Strategy (sequential)

Spawn `gtm-strategist` with `mode: "bypassPermissions"`:
- Prompt: "Create a launch validation strategy for '<product-name>'. Focus on: willingness-to-pay signals, minimum viable audience (MVA), competitive moat, and go-to-market channel prioritization. Write GTM-STRATEGY.md to `docs/launch/<slug>/`. Include a machine-readable `## Agent Task Assignments` section at the end."
- If AUTO_MODE=true: append "AUTO_MODE=true — do NOT ask the user any questions. Make reasonable assumptions based on research and state all assumptions explicitly."

**Validate**: Read `docs/launch/<slug>/GTM-STRATEGY.md` — must exist and contain sections on ICP, Positioning, Channel Strategy.
If missing or incomplete, re-spawn gtm-strategist with: "GTM-STRATEGY.md is incomplete. Regenerate with all required sections."

### Step 2: Research (parallel)

Spawn both simultaneously with `mode: "bypassPermissions"`:

1. **gtm-market-research**: "Analyze the competitive landscape for the product described in `docs/launch/<slug>/GTM-STRATEGY.md`. Write COMPETITIVE-ANALYSIS.md and BATTLE-CARDS.md to `docs/launch/<slug>/`."

2. **gtm-icp-discovery**: "Build detailed ICP profiles and prospect list based on `docs/launch/<slug>/GTM-STRATEGY.md`. Write ICP-PROFILES.md and PROSPECT-LIST.md to `docs/launch/<slug>/`."

**Validate**: Check that COMPETITIVE-ANALYSIS.md and ICP-PROFILES.md exist in `docs/launch/<slug>/`.

Update LAUNCH-PROGRESS.md: Phase 0 → Done, Phase 1 → In Progress.

### Approval Gate — Phase 0

**If AUTO_MODE=true:** Update the Approval column for Phase 0 → "Auto-approved". Append to Approval Log: `- Phase 0: Auto-approved (<timestamp>)`. Proceed to Phase 1.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/GTM-STRATEGY.md` (by gtm-strategist)
   - `docs/launch/<slug>/COMPETITIVE-ANALYSIS.md` (by gtm-market-research)
   - `docs/launch/<slug>/BATTLE-CARDS.md` (by gtm-market-research)
   - `docs/launch/<slug>/ICP-PROFILES.md` (by gtm-icp-discovery)
   - `docs/launch/<slug>/PROSPECT-LIST.md` (by gtm-icp-discovery)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 1 (Pre-sell)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 0: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user what to fix. Re-spawn only the relevant agent(s) with the original prompt plus the user's revision feedback. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 0: Skipped (<timestamp>)`. Set PHASE_0_SKIPPED=true. Proceed.

---

## Phase 1: Pre-sell (2 parallel agents)

**Skip-awareness:** If PHASE_0_SKIPPED=true, append to each agent's prompt: "Note: Phase 0 (Validate) was skipped. GTM-STRATEGY.md, ICP-PROFILES.md, and research outputs may not exist. Use your best judgment to infer strategy from the product name."

Spawn both simultaneously with `mode: "bypassPermissions"`:

1. **gtm-copywriter**: "Create pre-sell assets for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md and ICP-PROFILES.md if they exist. Write to `docs/launch/<slug>/presell/`: LANDING-PAGE.md (conversion-focused landing page copy with headline variants, hero section, benefits, social proof placeholders, CTA), PAYMENT-SETUP.md (guide for setting up Stripe/payment collection for pre-orders or early access)."

2. **gtm-outbound**: "Create early validation outreach templates for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md, ICP-PROFILES.md, and PROSPECT-LIST.md if they exist. Write OUTBOUND-TEMPLATES.md to `docs/launch/<slug>/presell/` — include: cold email sequences for validation interviews, LinkedIn DM templates for early adopter outreach, founder-led sales templates."

**Validate**: Check that `docs/launch/<slug>/presell/LANDING-PAGE.md` exists.

Update LAUNCH-PROGRESS.md: Phase 1 → Done, Phase 2 → In Progress.

### Approval Gate — Phase 1

**If AUTO_MODE=true:** Update the Approval column for Phase 1 → "Auto-approved". Append to Approval Log: `- Phase 1: Auto-approved (<timestamp>)`. Proceed to Phase 2.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/presell/LANDING-PAGE.md` (by gtm-copywriter)
   - `docs/launch/<slug>/presell/PAYMENT-SETUP.md` (by gtm-copywriter)
   - `docs/launch/<slug>/presell/OUTBOUND-TEMPLATES.md` (by gtm-outbound)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 2 (Spec MVP)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 1: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Re-spawn only the named agent(s). Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 1: Skipped (<timestamp>)`. Set PHASE_1_SKIPPED=true. Proceed.

---

## Phase 2: Spec MVP (2 sequential agents — skippable)

**If SKIP_BUILD=true:** Update Phase 2 Status → "Skipped (--skip-build)". Append to Approval Log: `- Phase 2: Skipped via --skip-build (<timestamp>)`. Set PHASE_2_SKIPPED=true. Proceed directly to Phase 5.

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_0_SKIPPED: "Note: Phase 0 (Validate) was skipped. GTM-STRATEGY.md and research outputs may not exist."
- If PHASE_1_SKIPPED: "Note: Phase 1 (Pre-sell) was skipped. Pre-sell assets may not exist."

### Step 1: Product Owner (sequential)

Spawn `product-owner` with `mode: "bypassPermissions"`:
- Prompt: "Create an MVP specification for the product described in `docs/launch/<slug>/`. Read GTM-STRATEGY.md, ICP-PROFILES.md, COMPETITIVE-ANALYSIS.md, and presell/LANDING-PAGE.md if they exist. If `.claude/scrum-team-config.md` does not exist, continue anyway — use the launch docs as your context. Write MVP-SPEC.md to `docs/launch/<slug>/mvp/`. Focus on: minimum feature set for first paying customers, core user stories (max 5-8), acceptance criteria, what is explicitly OUT of scope."
- If AUTO_MODE=true: append "AUTO_MODE=true — do NOT ask the user any questions. Make reasonable assumptions and state all assumptions explicitly."

**Validate**: Check that `docs/launch/<slug>/mvp/MVP-SPEC.md` exists.

### Step 2: Architect (sequential)

Spawn `architect` with `mode: "bypassPermissions"`:
- Prompt: "Design a minimal architecture for the MVP described in `docs/launch/<slug>/mvp/MVP-SPEC.md`. If `.claude/scrum-team-config.md` does not exist, continue anyway — use the launch docs as your context. Write ARCHITECTURE.md to `docs/launch/<slug>/mvp/`. Focus on: simplest viable tech stack, core entities and data model, key API endpoints, frontend page structure. Keep it minimal — this is an MVP, not a production system."

**Validate**: Check that `docs/launch/<slug>/mvp/ARCHITECTURE.md` exists.

Update LAUNCH-PROGRESS.md: Phase 2 → Done, Phase 3 → In Progress.

### Approval Gate — Phase 2

**If AUTO_MODE=true:** Update the Approval column for Phase 2 → "Auto-approved". Append to Approval Log: `- Phase 2: Auto-approved (<timestamp>)`. Proceed to Phase 3.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/mvp/MVP-SPEC.md` (by product-owner)
   - `docs/launch/<slug>/mvp/ARCHITECTURE.md` (by architect)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 3 (Build MVP)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 2: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Re-spawn only the named agent(s). Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 2: Skipped (<timestamp>)`. Set PHASE_2_SKIPPED=true. Proceed.

---

## Phase 3: Build MVP (delegates to /scrum-team — skippable)

**If SKIP_BUILD=true:** Update Phase 3 Status → "Skipped (--skip-build)". Append to Approval Log: `- Phase 3: Skipped via --skip-build (<timestamp>)`. Set PHASE_3_SKIPPED=true. Proceed directly to Phase 5.

**If PHASE_2_SKIPPED=true:** Update Phase 3 Status → "Skipped (no specs from Phase 2)". Append to Approval Log: `- Phase 3: Skipped — Phase 2 was skipped, no specs available (<timestamp>)`. Set PHASE_3_SKIPPED=true. Proceed directly to Phase 5.

**Precondition check:** Read `.claude/scrum-team-config.md`. If it does NOT exist:
- Print: "ERROR: `.claude/scrum-team-config.md` not found. Phase 3 (Build MVP) requires a scrum team config. Skipping build phase."
- Update Phase 3 Status → "Skipped (no scrum-team-config.md)". Set PHASE_3_SKIPPED=true. Proceed to Phase 5.

### Build execution

Spawn a general-purpose agent with `mode: "bypassPermissions"`:
```
Spawn Task:
  subagent_type = "general-purpose"
  mode          = "bypassPermissions"
  prompt        = """
    Read the file `~/.claude/commands/scrum-team.md` and execute the full workflow
    described in it. Set $ARGUMENTS to: `--auto --size medium <product-name>`

    Use `docs/launch/<slug>/mvp/MVP-SPEC.md` as the feature brief basis.
    Use `docs/launch/<slug>/mvp/ARCHITECTURE.md` as the architecture basis.

    When complete, write a summary to `docs/launch/<slug>/build/BUILD-SUMMARY.md` with:
    - PR URL (if created)
    - Branch name
    - Build status (success/failure)
    - Key files created/modified
  """
```

**Validate**: Check that `docs/launch/<slug>/build/BUILD-SUMMARY.md` exists.

Update LAUNCH-PROGRESS.md: Phase 3 → Done, Phase 4 → In Progress.

### Approval Gate — Phase 3

**If AUTO_MODE=true:** Update the Approval column for Phase 3 → "Auto-approved". Append to Approval Log: `- Phase 3: Auto-approved (<timestamp>)`. Proceed to Phase 4.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/build/BUILD-SUMMARY.md` (by /scrum-team delegation)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 4 (Audit & Harden)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 3: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user what to fix. Re-spawn the scrum-team delegation with revision instructions. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 3: Skipped (<timestamp>)`. Set PHASE_3_SKIPPED=true. Proceed.

---

## Phase 4: Audit & Harden (delegates to /prepare-for-production — skippable)

**If SKIP_BUILD=true OR SKIP_TEST=true:** Update Phase 4 Status → "Skipped (--skip-build or --skip-test)". Append to Approval Log: `- Phase 4: Skipped via flag (<timestamp>)`. Set PHASE_4_SKIPPED=true. Proceed to Phase 5.

**If PHASE_3_SKIPPED=true:** Update Phase 4 Status → "Skipped (no build from Phase 3)". Append to Approval Log: `- Phase 4: Skipped — Phase 3 was skipped, nothing to audit (<timestamp>)`. Set PHASE_4_SKIPPED=true. Proceed to Phase 5.

### Audit execution

Spawn a general-purpose agent with `mode: "bypassPermissions"`:
```
Spawn Task:
  subagent_type = "general-purpose"
  mode          = "bypassPermissions"
  prompt        = """
    Read the file `~/.claude/commands/prepare-for-production.md` and execute the full workflow
    described in it.

    When complete, read `docs/production-audit/SUMMARY.md` and extract the overall status.
    Write `docs/launch/<slug>/audit/AUDIT-STATUS.md` with:
    - Overall verdict: PASS / WARN / FAIL
    - Summary of each audit category (security, performance, dependencies, etc.)
    - Critical issues that must be fixed before launch
    - Recommended fixes with priority
  """
```

**Validate**: Check that `docs/launch/<slug>/audit/AUDIT-STATUS.md` exists. Read it and extract the verdict (PASS/WARN/FAIL).

Update LAUNCH-PROGRESS.md: Phase 4 → Done, Phase 5 → In Progress.

### Approval Gate — Phase 4

**If AUTO_MODE=true:** Update the Approval column for Phase 4 → "Auto-approved". Append to Approval Log: `- Phase 4: Auto-approved (<timestamp>) — Verdict: <PASS/WARN/FAIL>`. If verdict is FAIL, print: "WARNING: Audit verdict is FAIL. Proceeding due to --auto mode, but production deployment is NOT recommended until critical issues are resolved." Proceed to Phase 5.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/audit/AUDIT-STATUS.md` (by /prepare-for-production delegation)
   - Display the verdict prominently: **PASS** / **WARN** / **FAIL**
   - If FAIL: "⚠ AUDIT FAILED — Critical issues found. Review audit/AUDIT-STATUS.md before proceeding."

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 5 (Monetize)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 4: Approved (<timestamp>) — Verdict: <verdict>`. Proceed.
   - **Request changes**: Ask the user what to fix. Re-spawn the audit delegation with revision instructions. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 4: Skipped (<timestamp>)`. Set PHASE_4_SKIPPED=true. Proceed.

---

## Phase 5: Monetize (3 parallel agents)

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_0_SKIPPED: "Note: Phase 0 (Validate) was skipped. GTM-STRATEGY.md and research outputs may not exist."
- If PHASE_1_SKIPPED: "Note: Phase 1 (Pre-sell) was skipped. Pre-sell assets may not exist."
- If PHASE_2_SKIPPED: "Note: Phase 2 (Spec MVP) was skipped. MVP-SPEC.md and ARCHITECTURE.md may not exist."
- If PHASE_3_SKIPPED: "Note: Phase 3 (Build MVP) was skipped. No build artifacts exist."
- If PHASE_4_SKIPPED: "Note: Phase 4 (Audit & Harden) was skipped. No audit results exist."

Spawn all 3 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-proposal**: "Create a pricing strategy and ROI calculator for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md, ICP-PROFILES.md, COMPETITIVE-ANALYSIS.md, and mvp/MVP-SPEC.md if they exist. Write PRICING-STRATEGY.md (pricing tiers, willingness-to-pay analysis, competitive pricing comparison, recommended launch price) and ROI-CALCULATOR.md (customer ROI framework, payback period model, value metrics) to `docs/launch/<slug>/monetize/`."

2. **gtm-crm**: "Design a lightweight CRM and billing pipeline for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md and ICP-PROFILES.md if they exist. Write CRM-SETUP.md to `docs/launch/<slug>/monetize/` — include: recommended CRM tool for early stage, deal stages, billing/invoicing workflow, customer onboarding pipeline."

3. **gtm-copywriter**: "Create transactional email templates for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md, presell/LANDING-PAGE.md, and monetize/PRICING-STRATEGY.md if they exist. Write EMAIL-TEMPLATES.md to `docs/launch/<slug>/monetize/` — include: welcome/onboarding sequence, trial-to-paid conversion emails, payment confirmation, dunning/failed payment emails, upsell templates."

**Validate**: Check that `docs/launch/<slug>/monetize/PRICING-STRATEGY.md` and `docs/launch/<slug>/monetize/CRM-SETUP.md` exist.

Update LAUNCH-PROGRESS.md: Phase 5 → Done, Phase 6 → In Progress.

### Approval Gate — Phase 5

**If AUTO_MODE=true:** Update the Approval column for Phase 5 → "Auto-approved". Append to Approval Log: `- Phase 5: Auto-approved (<timestamp>)`. Proceed to Phase 6.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/monetize/PRICING-STRATEGY.md` (by gtm-proposal)
   - `docs/launch/<slug>/monetize/ROI-CALCULATOR.md` (by gtm-proposal)
   - `docs/launch/<slug>/monetize/CRM-SETUP.md` (by gtm-crm)
   - `docs/launch/<slug>/monetize/EMAIL-TEMPLATES.md` (by gtm-copywriter)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 6 (Launch & Distribute)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 5: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-proposal` → monetize/PRICING-STRATEGY.md, monetize/ROI-CALCULATOR.md
     - `gtm-crm` → monetize/CRM-SETUP.md
     - `gtm-copywriter` → monetize/EMAIL-TEMPLATES.md
     Re-spawn only the named agent(s). Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 5: Skipped (<timestamp>)`. Set PHASE_5_SKIPPED=true. Proceed.

---

## Phase 6: Launch & Distribute (5 parallel agents)

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_0_SKIPPED: "Note: Phase 0 (Validate) was skipped. GTM-STRATEGY.md and research outputs may not exist."
- If PHASE_1_SKIPPED: "Note: Phase 1 (Pre-sell) was skipped. Pre-sell assets may not exist."
- If PHASE_2_SKIPPED: "Note: Phase 2 (Spec MVP) was skipped. MVP specs may not exist."
- If PHASE_3_SKIPPED: "Note: Phase 3 (Build MVP) was skipped. No build artifacts exist."
- If PHASE_4_SKIPPED: "Note: Phase 4 (Audit & Harden) was skipped. No audit results exist."
- If PHASE_5_SKIPPED: "Note: Phase 5 (Monetize) was skipped. Pricing and monetization outputs may not exist."

Spawn all 5 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-seo-content**: "Build an SEO content strategy for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md and ICP-PROFILES.md if they exist. Write SEO-KEYWORD-REPORT.md and CONTENT-CLUSTER-MAP.md to `docs/launch/<slug>/launch/`, and 3-5 SEO-optimized blog post drafts to `docs/launch/<slug>/launch/content/blog/`."

2. **gtm-community**: "Plan a Product Hunt launch and community engagement strategy for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md and ICP-PROFILES.md if they exist. Write COMMUNITY-LAUNCH-PLAN.md to `docs/launch/<slug>/launch/` — include: Product Hunt launch checklist and timeline, Reddit/HackerNews submission strategy, community seeding plan, early adopter community building."

3. **gtm-outbound**: "Create a full outbound sales playbook for the product in `docs/launch/<slug>/`. Read all upstream docs. Write OUTBOUND-PLAYBOOK.md to `docs/launch/<slug>/launch/` — include: cold email sequences (awareness → demo → close), LinkedIn outreach cadence, follow-up sequences, objection handling scripts."

4. **gtm-paid-ads**: "Design a paid advertising launch plan for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md, ICP-PROFILES.md, and presell/LANDING-PAGE.md if they exist. Write PAID-ADS-PLAN.md to `docs/launch/<slug>/launch/` — include: Google Ads campaign structure, LinkedIn Ads targeting, Meta/social retargeting, budget allocation for $500-5000/mo launch budgets, A/B test plan."

5. **gtm-copywriter**: "Create social media content and launch announcement copy for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md, presell/LANDING-PAGE.md, and ICP-PROFILES.md if they exist. Write to `docs/launch/<slug>/launch/content/`: SOCIAL-MEDIA-CALENDAR.md (30-day launch content calendar for Twitter/LinkedIn/other), LAUNCH-ANNOUNCEMENT.md (press release style announcement, email blast copy, partner outreach templates)."

**Validate**: Check that `docs/launch/<slug>/launch/` directory contains at least COMMUNITY-LAUNCH-PLAN.md and OUTBOUND-PLAYBOOK.md.

Update LAUNCH-PROGRESS.md: Phase 6 → Done, Phase 7 → In Progress.

### Approval Gate — Phase 6

**If AUTO_MODE=true:** Update the Approval column for Phase 6 → "Auto-approved". Append to Approval Log: `- Phase 6: Auto-approved (<timestamp>)`. Proceed to Phase 7.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/launch/SEO-KEYWORD-REPORT.md` (by gtm-seo-content)
   - `docs/launch/<slug>/launch/CONTENT-CLUSTER-MAP.md` (by gtm-seo-content)
   - `docs/launch/<slug>/launch/content/blog/` (by gtm-seo-content)
   - `docs/launch/<slug>/launch/COMMUNITY-LAUNCH-PLAN.md` (by gtm-community)
   - `docs/launch/<slug>/launch/OUTBOUND-PLAYBOOK.md` (by gtm-outbound)
   - `docs/launch/<slug>/launch/PAID-ADS-PLAN.md` (by gtm-paid-ads)
   - `docs/launch/<slug>/launch/content/SOCIAL-MEDIA-CALENDAR.md` (by gtm-copywriter)
   - `docs/launch/<slug>/launch/content/LAUNCH-ANNOUNCEMENT.md` (by gtm-copywriter)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 7 (Prod Smoke Test)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 6: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-seo-content` → launch/SEO-KEYWORD-REPORT.md, launch/CONTENT-CLUSTER-MAP.md, launch/content/blog/
     - `gtm-community` → launch/COMMUNITY-LAUNCH-PLAN.md
     - `gtm-outbound` → launch/OUTBOUND-PLAYBOOK.md
     - `gtm-paid-ads` → launch/PAID-ADS-PLAN.md
     - `gtm-copywriter` → launch/content/SOCIAL-MEDIA-CALENDAR.md, launch/content/LAUNCH-ANNOUNCEMENT.md
     Re-spawn only the named agent(s). Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 6: Skipped (<timestamp>)`. Set PHASE_6_SKIPPED=true. Proceed.

---

## Phase 7: Prod Smoke Test (manual-tester — skippable)

**If SKIP_BUILD=true OR SKIP_SMOKE=true:** Update Phase 7 Status → "Skipped (--skip-build or --skip-smoke)". Append to Approval Log: `- Phase 7: Skipped via flag (<timestamp>)`. Set PHASE_7_SKIPPED=true. Proceed to Phase 8.

**If PHASE_3_SKIPPED=true:** Update Phase 7 Status → "Skipped (no build from Phase 3)". Append to Approval Log: `- Phase 7: Skipped — no build to smoke test (<timestamp>)`. Set PHASE_7_SKIPPED=true. Proceed to Phase 8.

### Resolve PROD_URL

If PROD_URL is not set:
- If AUTO_MODE=false: Use AskUserQuestion: "Phase 7 needs a production URL for smoke testing. Enter the production URL, or type 'skip' to skip this phase."
  - If user provides URL: set PROD_URL to that URL.
  - If user types 'skip': Update Phase 7 Status → "Skipped (no prod URL)". Set PHASE_7_SKIPPED=true. Proceed to Phase 8.
- If AUTO_MODE=true: Update Phase 7 Status → "Skipped (no --prod-url provided)". Set PHASE_7_SKIPPED=true. Proceed to Phase 8.

### Smoke test execution

1. Write `docs/launch/<slug>/build/SMOKE-TEST-ENV.md`:
```markdown
# Smoke Test Environment
- Production URL: <PROD_URL>
- Test Date: <timestamp>
- Test Type: Production Smoke Test
- Safety: READ-ONLY — do NOT create test data that cannot be cleaned up
```

2. Spawn `manual-tester` with `mode: "bypassPermissions"`:
- Prompt: "Run a production smoke test against <PROD_URL>. Read `docs/launch/<slug>/build/SMOKE-TEST-ENV.md` for context. IMPORTANT: This is PRODUCTION — do NOT create test data that cannot be cleaned up. Do NOT perform destructive actions. Run only CRITICAL/HIGH test scenarios. If no test cases exist, run these basic smoke checks: homepage loads successfully, login page works (if applicable), core navigation is functional, primary user flow works end-to-end, no console errors on key pages. Write results to `docs/launch/<slug>/build/SMOKE-TEST-RESULTS.md` with: test name, status (PASS/FAIL), details, screenshots if available. Include a summary with total pass/fail counts."

**Validate**: Check that `docs/launch/<slug>/build/SMOKE-TEST-RESULTS.md` exists.

Update LAUNCH-PROGRESS.md: Phase 7 → Done, Phase 8 → In Progress.

### Approval Gate — Phase 7

**If AUTO_MODE=true:** Update the Approval column for Phase 7 → "Auto-approved". Append to Approval Log: `- Phase 7: Auto-approved (<timestamp>)`. Proceed to Phase 8.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/build/SMOKE-TEST-ENV.md`
   - `docs/launch/<slug>/build/SMOKE-TEST-RESULTS.md` (by manual-tester)
   - Display pass/fail counts prominently

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 8 (Optimize & Scale)"
   - "Request changes — re-run smoke tests"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 7: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user what to re-test. Re-spawn manual-tester. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 7: Skipped (<timestamp>)`. Set PHASE_7_SKIPPED=true. Proceed.

---

## Phase 8: Optimize & Scale (4 parallel agents)

**Skip-awareness:** Check for skipped upstream phases. For each skipped phase, append to every agent's prompt:
- If PHASE_0_SKIPPED: "Note: Phase 0 (Validate) was skipped. GTM-STRATEGY.md and research outputs may not exist."
- If PHASE_1_SKIPPED: "Note: Phase 1 (Pre-sell) was skipped. Pre-sell assets may not exist."
- If PHASE_2_SKIPPED: "Note: Phase 2 (Spec MVP) was skipped. MVP specs may not exist."
- If PHASE_3_SKIPPED: "Note: Phase 3 (Build MVP) was skipped. No build artifacts exist."
- If PHASE_4_SKIPPED: "Note: Phase 4 (Audit & Harden) was skipped. No audit results exist."
- If PHASE_5_SKIPPED: "Note: Phase 5 (Monetize) was skipped. Pricing and monetization outputs may not exist."
- If PHASE_6_SKIPPED: "Note: Phase 6 (Launch & Distribute) was skipped. Launch and distribution outputs may not exist."
- If PHASE_7_SKIPPED: "Note: Phase 7 (Prod Smoke Test) was skipped. No smoke test results exist."

Spawn all 4 simultaneously with `mode: "bypassPermissions"`:

1. **gtm-metrics**: "Design an early-stage KPI dashboard for the product in `docs/launch/<slug>/`. Read all upstream docs. Write KPI-DASHBOARD.md to `docs/launch/<slug>/optimize/` — focus on: pre-revenue metrics (signups, activation, engagement), revenue metrics (MRR, churn, LTV), channel-specific metrics (CAC by channel, conversion rates), recommended dashboard tool for early stage."

2. **gtm-experiment**: "Design an experiment backlog for the product in `docs/launch/<slug>/`. Read all upstream docs. Write EXPERIMENT-BACKLOG.md to `docs/launch/<slug>/optimize/` — include: ICE-scored experiment backlog (pricing, messaging, channel, product), A/B test frameworks for landing page and email, experiment tracking template."

3. **gtm-lead-scoring**: "Design a lead scoring model for the product in `docs/launch/<slug>/`. Read GTM-STRATEGY.md, ICP-PROFILES.md, and PROSPECT-LIST.md if they exist. Write LEAD-SCORING-MODEL.md to `docs/launch/<slug>/optimize/` — include: firmographic fit scoring, behavioral intent signals, lead routing rules, MQL/SQL definitions for early stage."

4. **gtm-reporting**: "Create reporting templates for the product in `docs/launch/<slug>/`. Read all upstream docs. Write REPORTING-TEMPLATES.md to `docs/launch/<slug>/optimize/` — include: weekly founder digest template, monthly investor/board update template, quarterly business review structure."

**Validate**: Check that `docs/launch/<slug>/optimize/KPI-DASHBOARD.md` exists.

Update LAUNCH-PROGRESS.md: Phase 8 → Done, Phase 9 → In Progress.

### Approval Gate — Phase 8

**If AUTO_MODE=true:** Update the Approval column for Phase 8 → "Auto-approved". Append to Approval Log: `- Phase 8: Auto-approved (<timestamp>)`. Proceed to Phase 9.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/optimize/KPI-DASHBOARD.md` (by gtm-metrics)
   - `docs/launch/<slug>/optimize/EXPERIMENT-BACKLOG.md` (by gtm-experiment)
   - `docs/launch/<slug>/optimize/LEAD-SCORING-MODEL.md` (by gtm-lead-scoring)
   - `docs/launch/<slug>/optimize/REPORTING-TEMPLATES.md` (by gtm-reporting)

2. Use AskUserQuestion with these options:
   - "Approve — proceed to Phase 9 (Feature Invention)"
   - "Request changes — I'll describe what to fix"
   - "Skip — move on without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 8: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Ask the user which agent(s) to re-run and what to fix. Available agents and their outputs:
     - `gtm-metrics` → optimize/KPI-DASHBOARD.md
     - `gtm-experiment` → optimize/EXPERIMENT-BACKLOG.md
     - `gtm-lead-scoring` → optimize/LEAD-SCORING-MODEL.md
     - `gtm-reporting` → optimize/REPORTING-TEMPLATES.md
     Re-spawn only the named agent(s). Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 8: Skipped (<timestamp>)`. Set PHASE_8_SKIPPED=true. Proceed.

---

## Phase 9: Feature Invention (brainstorm-facilitator — skippable)

**If SKIP_ITERATE=true:** Update Phase 9 Status → "Skipped (--skip-iterate)". Append to Approval Log: `- Phase 9: Skipped via --skip-iterate (<timestamp>)`. Proceed to Completion.

### Feature invention execution

Spawn `brainstorm-facilitator` with `mode: "bypassPermissions"`:
- Prompt: "AUTO_MODE=true — do NOT ask the user any questions. You are generating the next wave of feature ideas for the product launched in `docs/launch/<slug>/`. Read ALL available launch artifacts in `docs/launch/<slug>/` — including GTM-STRATEGY.md, COMPETITIVE-ANALYSIS.md, ICP-PROFILES.md, mvp/MVP-SPEC.md, monetize/PRICING-STRATEGY.md, optimize/KPI-DASHBOARD.md, optimize/EXPERIMENT-BACKLOG.md, build/SMOKE-TEST-RESULTS.md, and audit/AUDIT-STATUS.md (read whichever exist). Run 3-4 WebSearch queries for feature trends in the product's space and recent competitor moves. Write `docs/launch/<slug>/iterate/NEXT-FEATURES.md` with: (1) 5-8 feature ideas, each with source (data-driven from artifacts or market research), expected impact, estimated effort, and ICE score; (2) Top 3 features expanded into mini-FRD briefs with problem statement, target user stories, and acceptance criteria; (3) Recommended next sprint — pick 1-2 features with exact commands to start building them (e.g. `/scrum-team --auto <feature-name>`); (4) Innovation radar — 3-6 month horizon ideas that are worth tracking but not building yet."

**Validate**: Check that `docs/launch/<slug>/iterate/NEXT-FEATURES.md` exists.

Update LAUNCH-PROGRESS.md: Phase 9 → Done.

### Approval Gate — Phase 9

**If AUTO_MODE=true:** Update the Approval column for Phase 9 → "Auto-approved". Append to Approval Log: `- Phase 9: Auto-approved (<timestamp>)`. Proceed to Completion.

**If AUTO_MODE=false:**

1. List the artifacts produced:
   - `docs/launch/<slug>/iterate/NEXT-FEATURES.md` (by brainstorm-facilitator)

2. Use AskUserQuestion with these options:
   - "Approve — finalize launch package"
   - "Request changes — I'll describe what to fix"
   - "Skip — finalize without these outputs"

3. Handle response:
   - **Approve**: Update Approval → "Approved". Append to Approval Log: `- Phase 9: Approved (<timestamp>)`. Proceed.
   - **Request changes**: Re-spawn brainstorm-facilitator with revision instructions. Re-validate, then loop back to this approval gate.
   - **Skip**: Update Approval → "Skipped". Append to Approval Log: `- Phase 9: Skipped (<timestamp>)`. Proceed.

---

## Completion

After all phases complete:

1. List all files produced in `docs/launch/<slug>/` using `ls -R`.
2. Update LAUNCH-PROGRESS.md with completion timestamp.
3. Print a summary (include approval status for each phase):

```
Product Launch Complete for <Product Name>

Output directory: docs/launch/<slug>/

Phase 0 (Validate):         GTM-STRATEGY.md, COMPETITIVE-ANALYSIS.md, ICP-PROFILES.md, PROSPECT-LIST.md [<Status>]
Phase 1 (Pre-sell):         presell/LANDING-PAGE.md, presell/PAYMENT-SETUP.md, presell/OUTBOUND-TEMPLATES.md [<Status>]
Phase 2 (Spec MVP):         mvp/MVP-SPEC.md, mvp/ARCHITECTURE.md [<Status>]
Phase 3 (Build MVP):        build/BUILD-SUMMARY.md — PR: <url or N/A> [<Status>]
Phase 4 (Audit & Harden):   audit/AUDIT-STATUS.md — Verdict: <PASS/WARN/FAIL or N/A> [<Status>]
Phase 5 (Monetize):         monetize/PRICING-STRATEGY.md, monetize/ROI-CALCULATOR.md, monetize/CRM-SETUP.md, monetize/EMAIL-TEMPLATES.md [<Status>]
Phase 6 (Launch):           launch/ — SEO, community, outbound, paid ads, social content [<Status>]
Phase 7 (Smoke Test):       build/SMOKE-TEST-RESULTS.md — <pass>/<total> passed [<Status>]
Phase 8 (Optimize):         optimize/ — KPI dashboard, experiments, lead scoring, reporting [<Status>]
Phase 9 (Feature Invention): iterate/NEXT-FEATURES.md — <N> features generated [<Status>]

Total agents used: 15+ unique (20+ spawns)
Total documents produced: 25+

Next steps:
- Review and customize all outputs in docs/launch/<slug>/
- To build the MVP: /scrum-team --auto <product-name>
- To build recommended features: /scrum-team --auto <top-recommended-feature>
- To batch-build features: /batch-features --features '<recommended features from NEXT-FEATURES.md>'
- To run the full GTM team: /gtm-team --auto <product-name>
```

The product launch plan for $ARGUMENTS
