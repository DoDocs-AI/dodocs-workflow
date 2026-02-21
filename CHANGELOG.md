# Changelog

All notable changes to dodocs-workflow will be documented in this file.

## [v1.5.4] - 2026-02-21

- Add /fix-the-issue command: lightweight bug-fix workflow with tech-lead investigation, parallel frontend/backend implementation, code review, compile gate, QA automation test updates, and PR creation with squash-merge

## [v1.5.3] - 2026-02-21

- Support modifying existing test cases and E2E tests: qa-engineer now scans for stale .md test case files and updates them in-place before creating new ones; qa-automation now scans for existing Playwright spec files covering changed functionality and updates them before writing new tests

## [v1.5.1] - 2026-02-18

- Remove --headed flag from manual-tester: playwright-cli now runs headless by default, no Playwright Flags config field needed
- Remove Playwright Flags field from scrum-team-config template (both claude and opencode)

## [v1.5.0] - 2026-02-18

- Switch Docker isolation to no-host-port architecture: only the frontend gets one host port (for manual-tester playwright-cli), all other services (backend, postgres, redis, minio) stay fully internal to the Docker network
- Startup health poll now runs inside Docker via curlimages/curl container (no host-side curl needed)
- qa-automation gets a new docker_test_runner section: runs Playwright inside a container on the same Docker network using internal URLs (BASE_URL, API_URL env vars), with fallback to host Playwright when Playwright Service is blank
- TEST-ENV.md now includes both external Test Frontend URL (for manual-tester) and internal Docker network URLs (for qa-automation)
- Replace App Services field in scrum-team-config template with explicit fields: Frontend Service Name, Frontend Internal Port, Backend Service Name, Backend Internal Port, Playwright Service
- Add Test Environment (Docker Isolation) section to opencode template (was missing)

## [v1.4.0] - 2026-02-18

- Add remote dev environment testing support: manual-tester and qa-automation now register a fresh tenant before testing, use it throughout, and delete it after all tests complete
- Add Remote Testing section to scrum-team-config template (Remote Dev URL, Tenant Registration URL, Tenant Admin URL)

## [v1.3.9] - 2026-02-18

- Enforce headless mode for all Playwright E2E tests in qa-automation agent (never use --headed flag)

## [v1.3.8] - 2026-02-18

- Track PROGRESS.md in git: tech-lead now commits and pushes PROGRESS.md to the feature branch after PR creation
- Add Session Cost section to PROGRESS.md template to record total spend per feature session

## [v1.3.7] - 2026-02-18

- feat: add /dw-upgrade command for one-step upgrade
- feat: show installed version in statusline (dw v1.3.x) with ⬆️ indicator when update available

## [v1.3.3] - 2026-02-16

- Product-owner agent upgraded from sonnet to opus model for better reasoning
- Added comprehensive environment-specific questions (environments, config, dependencies, behaviors, test data, security)
- Enhanced Feature Brief format with Environment Configuration section
- Added AskUserQuestion tool to OpenCode product-owner

## [v1.3.2] - 2026-02-16

- Add WebSearch tool to architect agent for documentation lookup

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
