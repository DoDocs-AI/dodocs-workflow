# Changelog

All notable changes to dodocs-workflow will be documented in this file.

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
