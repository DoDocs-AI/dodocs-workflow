# Code Reviewer

Reviews completed developer code for pattern adherence, security issues, logic errors, and edge cases. Approves or requests changes before code moves to testing.

## Spec

| Property | Value |
|----------|-------|
| **Agent file** | `agents/code-reviewer.md` |
| **Model** | opus |
| **Active in phases** | 5 (per-task review), 6 (full-diff review) |
| **Tools** | Read, Grep, Glob, Bash |
| **Inputs** | Completed developer tasks, Architecture doc |
| **Outputs** | Approve verdict OR rework task with issues |

## Behavior

1. Monitors TaskList for developer tasks marked `completed`.
2. For each completed task:
   - Reads task description to understand intent.
   - Reads the Architecture doc for the feature.
   - Reads ALL files created or modified by the developer.
3. Checks: pattern adherence, security (SQL injection, XSS, missing auth), logic errors, edge cases, API contract match, type safety, missing pieces.
4. Verdict:
   - **Approve** — notifies team lead that this task's review is complete. When all tasks in a user story are approved, notes that the story is review-complete.
   - **Request changes** — creates a rework task with file paths, line references, severity, suggested fix. Assigns to the original developer.

## Review Format (when requesting changes)

- Files reviewed: list of files checked
- Issues found: file path, line reference, description per issue
- Severity: Critical (blocks testing) / Minor (should fix)
- Suggested fix: brief description per issue

## Phase 6 Role

Does a full-diff review of the entire feature branch (all changes from branch point) before PR creation.

## Config Sections Used

- App Identity, Tech Stack — understands codebase conventions
- Source Paths — Backend, Frontend — locates code files
- Commands (Compile Backend, Compile Frontend) — aware of build verification

## Coordination

- Sends message to team lead after each review verdict.
- When all tasks in a user story are approved, notifies team lead that the story is review-complete. Manual-tester begins testing only after ALL tasks are reviewed and test cases are ready.
- Request changes sends developer back to fix, then re-review cycle.
- In retest mode: reviews bug fixes made by developers.
- After each review verdict, updates the Code Reviews section of `PROGRESS.md` and adds a timeline entry.

## When It Runs

- **Full workflow**: Phase 5 (per-task review) + Phase 6 (full diff)
- **Retest mode**: Reviews bug fixes
