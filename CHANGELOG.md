# Changelog

All notable changes to dodocs-workflow will be documented in this file.

## [v1.3.1] - 2026-02-16

- Product-owner agent now uses AskUserQuestion for structured questions with selectable answer variants instead of plain text lists

## [v1.3.0] - 2026-02-15

- Parallelized UX Design and Architecture phases (formerly sequential Phase 2 + Phase 3, now single parallel Phase 2)
- Architect now reads Feature Brief as primary input, no longer waits for UX Design
- User checkpoint covers both UX and architecture approval together
- Reduced workflow from 7 phases to 6 phases

## [v1.2.2] - 2026-02-14

- Added autonomous execution block to manual-tester agent for approval-free command execution
- Switched planning/review roles (code-reviewer, product-owner, scrum-master, ux-designer, db-analyst, performance-engineer) from opus to sonnet model

## [v1.2.1] - 2026-02-14

- Fixed agents prompting for permissions despite bypassPermissions flag
- Moved bypassPermissions instruction to top-level mandatory section in scrum-team command
- Added explicit Mode column to all agent tables (scrum-team and retest)
- Added missing bypassPermissions to prepare-for-production auditor agents
- Reinforced mode at every phase spawn point for reliability

## [v1.2.0] - 2025-02-13

- manual-tester switched to haiku model for cost optimization
- Screenshots only captured on test failure (reduced token usage)
- Fixed VERSION file path in install.sh

## [v1.1.0] - 2025-02-12

- Added OpenCode workflow distribution (install-opencode.sh, opencode/ directory)
- OpenCode agents and commands mirror Claude Code workflow

## [v1.0.0] - 2025-02-11

- Initial release of dodocs-workflow
- 13-agent scrum team workflow for Claude Code
- 10-agent production readiness audit
- /scrum-team and /prepare-for-production slash commands
- Project config template system
