# DoDocs Support Bot

Dockerized customer support bot powered by Claude Code. Receives messages from Telegram and Slack, investigates production issues via kubectl and psql, and responds to team members and clients.

## Architecture

```
Telegram Bot API ──poll──▶ ┌──────────────────────┐
                           │   Python Gateway      │
Slack Events API ──hook──▶ │   (asyncio service)   │
                           │                       │
                           │  • Telegram poller    │
                           │  • Slack webhook :8080│
                           │  • Message normalizer │
                           │  • Response dispatcher│
                           └──────────┬────────────┘
                                      │ writes messages to JSON
                                      ▼
                           ┌──────────────────────┐
                           │   Claude Code CLI     │
                           │   /support command    │
                           └──────────┬────────────┘
                                      │
                    ┌─────────────────┼─────────────────┐
                    ▼                 ▼                  ▼
                 kubectl           psql              git clone
               (prod logs)     (readonly DB)       (investigate)
```

## Quick Start

```bash
cp .env.example .env
# Edit .env with your tokens

make build
make up
make logs
```

## Requirements

- Docker & Docker Compose
- Claude Max subscription (auth via `~/.claude` mount)
- kubeconfig with prod cluster access (`~/.kube/config`)
- Telegram Bot Token
- Slack Bot Token + Signing Secret (optional)

## Configuration

| File | Purpose |
|------|---------|
| `.env` | Secrets (bot tokens, signing secrets) |
| `config/bot-config.yaml` | Polling intervals, rate limits, timeouts |
| `config/access-control.yaml` | Team members, permissions, escalation |
| `config/products/matchpoint.yaml` | Matchpoint k8s/DB/repo details |

## Adding a New Product

1. Create `config/products/<product>.yaml` with k8s, database, and GitHub details
2. The `/support` command reads product configs dynamically

## Available Commands

The bot inherits all dodocs-workflow commands:
- `/brainstorm` — Stress-test a feature idea
- `/fix-the-issue` — Fix a bug
- `/scrum-team` — Create an agent team
- And 10+ more

## Security

- Database: SELECT-only queries via readonly users
- kubectl: Read-only operations only (logs, describe, get, top)
- Client responses require team approval before sending
- All interactions logged to `state/audit/`
- Rate limiting: 5 messages per user per 5 minutes
