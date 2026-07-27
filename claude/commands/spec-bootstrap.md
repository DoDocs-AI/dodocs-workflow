Bootstrap OpenSpec living specs for a project — derives `openspec/specs/<domain>/spec.md` from existing feature docs and the codebase, and seeds change proposals for in-flight features. One-time migration step for projects created before the OpenSpec pipeline (or new projects that want an initial spec baseline).

## Usage

```
/spec-bootstrap            # full bootstrap (interactive domain approval)
/spec-bootstrap --dry-run  # only propose the domain list and per-feature mapping, write nothing
```

---

## MANDATORY: Agent Execution Mode

**CRITICAL — READ THIS FIRST**: Every agent you spawn via the Agent tool MUST use `mode: "bypassPermissions"` to ensure fully autonomous execution with no permission prompts.

---

## Step 0: Preflight

1. Read `.claude/scrum-team-config.md`. If it does not exist, STOP:
   > "No scrum-team config found. Run `dodocs-workflow init` first."
   Extract `APP_NAME`, the `## OpenSpec` section (CLI invocation, Spec Domains), and the Feature Docs path (default `docs/features/`).
   If the `## OpenSpec` section is missing, use the pinned default CLI `npx -y @fission-ai/openspec@1.6.0` and note that the config should be updated from the current template.
2. Doctor: `node --version` must be >= 20 and `<openspec-cli> --version` must succeed. Otherwise STOP with install instructions.
3. If `openspec/` does not exist, scaffold it: `<openspec-cli> init --tools none`
4. If `openspec/specs/` already contains spec files, STOP:
   > "openspec/specs/ already has specs — this project is already bootstrapped. Use /prepare-feature or /change-request for new work."

## Step 1: Spawn the bootstrapper

Spawn the `spec-bootstrapper` agent (`mode: "bypassPermissions"`) with this prompt:

```
APP_NAME=<APP_NAME from config>
OPENSPEC_CLI=<CLI invocation from config or default>
FEATURE_DOCS=<Feature Docs path from config>
CONFIG_DOMAINS=<Spec Domains line from config, may be empty>
DRY_RUN=<true|false>

Bootstrap the OpenSpec living specs. Follow the instructions in your system prompt.
```

The agent pauses once to get the domain list approved (AskUserQuestion) before writing specs.

## Step 2: Report

After the agent completes, print its summary:
- Domains created and requirement counts per domain
- `<openspec-cli> validate --specs --strict` result
- In-flight features seeded as `openspec/changes/<slug>/`
- Reminder that legacy `docs/features/*/FEATURE-BRIEF.md` files remain as read-only history

If the agent updated the Spec Domains line, confirm `.claude/scrum-team-config.md` reflects it.
$ARGUMENTS
