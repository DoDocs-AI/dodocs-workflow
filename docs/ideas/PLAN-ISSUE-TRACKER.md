# Plan: GitHub Issues Integration

> Priority: HIGH | Effort: MODERATE
> Inspired by: Symphony's Linear integration

## Goal

Auto-dispatch dodocs-workflow agents when GitHub issues are labeled, and post results back as comments. Closes the loop between project management and autonomous agent execution.

---

## Architecture Overview

```
GitHub Issues                     dodocs-workflow
┌──────────────┐                 ┌─────────────────────┐
│ Issue created │                 │  Dashboard Server   │
│ + label added │──webhook POST──│  POST /api/webhook/ │
│   "ai-ready" │                 │       github        │
└──────────────┘                 └─────────┬───────────┘
                                           │
                                           ▼
                                 ┌─────────────────────┐
                                 │  Issue Dispatcher    │
                                 │  (new module in      │
                                 │   server.py)         │
                                 │                      │
                                 │  1. Parse issue      │
                                 │  2. Create registry  │
                                 │     task             │
                                 │  3. Spawn agent      │
                                 │  4. Post result back │
                                 └─────────────────────┘
                                           │
                                           ▼
                                 ┌─────────────────────┐
                                 │  workspace-supervisor│
                                 │  OR                  │
                                 │  /fix-the-issue      │
                                 │  /scrum-team --auto  │
                                 └──────────┬──────────┘
                                            │
                                            ▼
                                 ┌─────────────────────┐
                                 │  GitHub API          │
                                 │  (via gh CLI)        │
                                 │  - Comment on issue  │
                                 │  - Link PR           │
                                 │  - Update labels     │
                                 └─────────────────────┘
```

## Implementation Steps

### Step 1: GitHub Webhook Receiver

**File**: `dashboard/server.py` — new endpoint

```
POST /api/webhook/github
```

- Receives GitHub webhook payloads (issue events)
- Validates `X-Hub-Signature-256` header (optional, configurable secret)
- Filters for relevant events:
  - `issues.labeled` where label = `ai-ready`, `ai-fix`, or `ai-feature`
  - `issues.opened` with matching label (pre-labeled issues)
- Extracts: repo, issue number, title, body, labels, assignee

**Label → Workflow mapping**:
| Label | Workflow | Command |
|-------|----------|---------|
| `ai-fix` | Bug fix | `/fix-the-issue` |
| `ai-feature` | Full feature | `/scrum-team --auto` |
| `ai-ready` | Auto-detect | Analyze issue title/body to decide |
| `ai-task` | Simple task | `workspace-supervisor` |

### Step 2: Issue-to-Task Bridge

**File**: `dashboard/github_bridge.py` — new module

Responsibilities:
1. **Map GitHub issue → registry task**
   - Find or create project in `registry.json` by repo path
   - Create task with `source: "github"`, `github_issue: { repo, number, url }`
   - Set priority from issue labels (`priority:high`, `priority:critical`, etc.)

2. **Dispatch the right agent**
   - For `ai-fix`: spawn `claude --agent fix-the-issue` in project directory
   - For `ai-feature`: spawn `claude --agent scrum-team --auto` in project directory
   - For `ai-task`: create registry task, let supervisor pick it up (or daemon mode)

3. **Track run status**
   - Store `run_id` on the task
   - Monitor subprocess for completion
   - On completion: update task status, post GitHub comment

### Step 3: GitHub Result Reporter

**File**: `dashboard/github_bridge.py` — result posting

When an agent completes:
1. Read task result from registry
2. Format as GitHub comment:
   ```markdown
   ## AI Agent Result

   **Status**: Completed / Blocked
   **Agent**: workspace-supervisor / scrum-team
   **Duration**: 12m 34s

   ### Summary
   <task result text>

   ### Pull Request
   - #42 (if PR was created)

   ---
   _Processed by [dodocs-workflow](https://github.com/user/dodocs-workflow)_
   ```
3. Post via `gh issue comment <number> --repo <repo> --body <text>`
4. Update labels: remove `ai-ready`, add `ai-done` or `ai-blocked`
5. If PR created: add `Closes #<number>` to PR body

### Step 4: Polling Mode (Alternative to Webhooks)

For users who can't set up webhooks (local dev, no public URL):

**File**: `dashboard/github_poller.py` — new module

- Poll `gh issue list --label ai-ready --json number,title,body,labels` every 60s
- Track processed issues in `~/.claude/workspace/github-processed.json`
- Same dispatch logic as webhook mode
- Configurable via `~/.claude/workspace/github-config.json`:
  ```json
  {
    "mode": "poll",
    "poll_interval_ms": 60000,
    "repos": [
      {
        "path": "/Users/me/projects/my-app",
        "repo": "owner/my-app",
        "labels": {
          "ai-fix": "fix-the-issue",
          "ai-feature": "scrum-team",
          "ai-task": "supervisor"
        }
      }
    ]
  }
  ```

### Step 5: Dashboard UI

**File**: `dashboard/ui/src/components/GitHubPanel.jsx` — new component

- Show connected repos and their sync status
- List recent GitHub-triggered runs with issue links
- Config form for adding repos and label mappings
- Button to manually sync/poll

### Step 6: CLI Command

**File**: `claude/commands/github-sync.md` — new slash command

```
/github-sync setup   — Configure GitHub integration for current project
/github-sync status  — Show sync status and recent activity
/github-sync poll    — Run one poll cycle manually
```

---

## Configuration

### `~/.claude/workspace/github-config.json`

```json
{
  "enabled": true,
  "mode": "poll",
  "poll_interval_ms": 60000,
  "webhook_secret": "$GITHUB_WEBHOOK_SECRET",
  "repos": [
    {
      "path": "/Users/me/projects/my-app",
      "repo": "owner/my-app",
      "default_workflow": "fix-the-issue",
      "label_map": {
        "ai-fix": "fix-the-issue",
        "ai-feature": "scrum-team --auto",
        "ai-task": "supervisor"
      },
      "auto_comment": true,
      "auto_label": true
    }
  ]
}
```

---

## Dependencies

- `gh` CLI (already commonly available, used throughout dodocs-workflow)
- GitHub repo access (authenticated via `gh auth`)
- No additional pip packages (stdlib HTTP for webhooks)

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Webhook delivery failures | Polling mode as fallback |
| Duplicate dispatches | Track processed issue IDs in `github-processed.json` |
| Agent crashes mid-issue | Retry with exponential backoff (see daemon mode plan) |
| Rate limits on `gh` CLI | Batch API calls, respect rate limit headers |
| Repo access permissions | Validate on setup, clear error messages |

## Estimated Scope

- `github_bridge.py`: ~300 lines (dispatch + result posting)
- `github_poller.py`: ~150 lines (polling loop)
- `server.py` changes: ~50 lines (webhook endpoint)
- Dashboard UI: ~200 lines (GitHubPanel component)
- Slash command: ~50 lines
- **Total: ~750 lines new code**
