# Workspace OS Dashboard

The Workspace OS Dashboard is a web-based project management UI for dodocs-workflow. It provides a visual interface to manage projects, track tasks, browse documentation, inspect source trees, and monitor agent activity — all backed by the same `~/.claude/workspace/registry.json` that the `/workspace` CLI commands use.

---

## Quick Start

```bash
cd dashboard
bash start.sh
```

This launches both services:

| Service | Port | Description |
|---------|------|-------------|
| Backend (Python) | 7474 | REST API + static file server |
| Frontend (Vite + React) | 7475 | SPA with hot reload |

Open **http://localhost:7475** in your browser.

No pip packages or global installs required — the backend uses Python stdlib only. The frontend needs Node.js for Vite.

### Prerequisites

- Python 3.8+
- Node.js 18+
- `~/.claude/workspace/` directory (created automatically on first project)

---

## Architecture

```
Browser (port 7475)
  |
  |  /api/*  (proxied by Vite)
  v
Python backend (port 7474)
  |
  |  reads/writes
  v
~/.claude/workspace/
  ├── registry.json          # All projects + tasks
  └── projects/
      ├── proj-001/
      │   ├── context.md     # Project context notes
      │   └── log.jsonl      # Agent activity log
      ├── proj-002/
      │   ├── context.md
      │   └── log.jsonl
      └── ...
```

The backend never touches your project source code for writes — it only reads files (docs, source tree) from the project path registered in `registry.json`. All state lives in `~/.claude/workspace/`.

---

## Data Model

### Registry (`registry.json`)

```json
{
  "version": "1.0",
  "workspaces": ["personal", "corporate"],
  "projects": [
    {
      "id": "proj-001",
      "name": "My App",
      "workspace": "personal",
      "type": "software",
      "phase": "development",
      "path": "/Users/me/projects/my-app",
      "description": "SaaS invoice platform",
      "status": "active",
      "created_at": "2026-03-01T10:00:00Z",
      "updated_at": "2026-03-04T14:30:00Z",
      "tasks": [
        {
          "id": "task-001",
          "title": "Add billing dashboard",
          "type": "coding",
          "status": "pending",
          "priority": "high",
          "agent_spawned": null,
          "result": null,
          "blocked_reason": null,
          "created_at": "2026-03-01T10:05:00Z"
        }
      ]
    }
  ]
}
```

### Project Types

| Type | Icon | Description |
|------|------|-------------|
| `software` | ⚙️ | Software development projects |
| `research` | 🔬 | Research and analysis |
| `content` | ✍️ | Content creation |
| `brainstorm` | 💡 | Idea exploration |
| `devops` | 🚀 | Infrastructure and deployment |
| `design` | 🎨 | Design projects |

### Project Phases

`ideation` → `planning` → `ready` → `in_progress` / `development` → `review` → `done` / `paused`

### Task Statuses

| Status | Icon | Description |
|--------|------|-------------|
| `pending` | ○ | Not started |
| `in_progress` | ⏳ | Being worked on |
| `done` | ✓ | Completed |
| `blocked` | 🚫 | Waiting on something |
| `cancelled` | ✗ | Cancelled |

### Task Priorities

`high` · `medium` · `low`

---

## UI Structure

### List View (Home)

The home screen has two areas:

**Sidebar** (left):
- Workspace filter chips — click to filter projects by workspace (`all`, `personal`, `corporate`, or custom)
- "Run Supervisor" button — triggers the `workspace-supervisor` agent to process all pending tasks
- Stats panel — total projects, active count, pending tasks, blocked tasks

**Main area** (right):
- Top bar with "New Project" button
- Blocked tasks banner — appears when any task across all projects has `status: blocked`
- Project cards grid — one card per project showing:
  - Name, workspace, type badge, phase badge
  - Description
  - Task list (first 4 tasks with overflow count)
  - Inline "Add task" form

### Detail View

Click any project card to enter the detail view. It has 5 tabs:

#### Overview Tab
- Project metadata: path, description, created/updated dates
- Task summary badges (done, in progress, pending, blocked counts)
- Features Implemented list (done tasks)
- In Progress and Blocked sections
- Context Notes panel — reads `context.md` from `~/.claude/workspace/projects/<id>/`

#### Tasks Tab
- Full task list with status icons, type badges, priority indicators, agent info, and timestamps
- Result and blocked reason display for each task
- "Add Task" form at the bottom with title, type selector, and priority selector

#### Documentation Tab
- Split-pane layout: file list (left) + document viewer (right)
- Scans the project path for `.md`, `.txt`, `.rst` files in:
  - Project root
  - `docs/` directory (recursive)
  - One level of subdirectories
- Built-in markdown renderer for `.md` files
- Raw text viewer for `.jsonl` files (shows last 80 lines for large files)

#### Sources Tab
- Interactive directory tree of the project (depth 2)
- Collapsible folders with file counts
- Excludes noise directories: `.git`, `node_modules`, `__pycache__`, `target`, `dist`, `build`, etc.

#### Session Tab
- Auto-refreshes every 5 seconds
- Agent Activity Log — reads `log.jsonl` from `~/.claude/workspace/projects/<id>/`, shows timestamp, task ID, agent name, status, and summary
- Session Files list — finds `.txt`, `.md` (in `tasks/`), and `.jsonl` files in the project directory
- File viewer panel for inspecting session file contents

### New Project Modal

Fields:
- **Name** (required)
- **Workspace** — dropdown with existing workspaces + defaults (`personal`, `corporate`)
- **Type** — software, research, content, brainstorm, devops, design
- **Phase** — ideation through done
- **Path** — absolute filesystem path to the project
- **Description** — free text

---

## REST API

All endpoints are served by `server.py` on port 7474. The Vite dev server proxies `/api/*` to the backend.

### Projects

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/registry` | Full registry (all workspaces + projects + tasks) |
| `GET` | `/api/projects/{id}` | Single project by ID |
| `POST` | `/api/projects` | Create a new project |
| `POST` | `/api/projects/{id}` | Update project fields (`phase`, `status`, `description`) |
| `POST` | `/api/projects/{id}/tasks` | Add a task to a project |

### Project Detail Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `GET` | `/api/projects/{id}/docs` | List documentation files found in project path |
| `GET` | `/api/projects/{id}/doc?file=<rel_path>` | Read a specific file from within the project |
| `GET` | `/api/projects/{id}/tree` | Directory tree (depth 2) of the project path |
| `GET` | `/api/projects/{id}/session` | Agent activity log + session files |
| `GET` | `/api/projects/{id}/log` | Raw activity log (last 100 entries) |
| `GET` | `/api/projects/{id}/context` | Read `context.md` for the project |

### Supervisor

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/api/supervisor/run` | Spawn the `workspace-supervisor` agent via `claude` CLI |

### Example: Create a Project

```bash
curl -X POST http://localhost:7474/api/projects \
  -H "Content-Type: application/json" \
  -d '{
    "name": "My New App",
    "workspace": "personal",
    "type": "software",
    "phase": "ideation",
    "path": "/Users/me/projects/my-new-app",
    "description": "A new SaaS application"
  }'
```

### Example: Add a Task

```bash
curl -X POST http://localhost:7474/api/projects/proj-001/tasks \
  -H "Content-Type: application/json" \
  -d '{
    "title": "Implement user authentication",
    "type": "coding",
    "priority": "high"
  }'
```

### Security

- File reads are sandboxed: `doc?file=` resolves paths relative to the project root and rejects any path that escapes it (path traversal protection)
- Large files are truncated at 400KB
- `.jsonl` files show only the last 80 lines
- CORS is open (`*`) for local development

---

## Frontend Architecture

The frontend is a React 18 SPA built with Vite.

### File Structure

```
dashboard/ui/
├── index.html              # Vite entry point
├── package.json            # React 18, Vite 6
├── vite.config.js          # Port 7475, proxies /api to :7474
└── src/
    ├── main.jsx            # React root mount
    ├── App.jsx             # Top-level: routing between list/detail views
    ├── api.js              # API client (fetch wrappers for all endpoints)
    ├── index.css            # Global styles (dark theme)
    ├── utils.js            # Icons, formatters, markdown renderer
    └── components/
        ├── Sidebar.jsx          # Workspace filter, stats, supervisor button
        ├── ProjectCard.jsx      # Project card with inline task add
        ├── NewProjectModal.jsx  # Create project form
        └── detail/
            ├── DetailView.jsx   # Tab container + phase selector
            ├── OverviewTab.jsx  # Project info + context notes
            ├── TasksTab.jsx     # Task list + add task form
            ├── DocsTab.jsx      # Split-pane doc browser
            ├── SourcesTab.jsx   # Directory tree viewer
            └── SessionTab.jsx   # Agent log + session file viewer
```

### Key Behaviors

- **Auto-refresh**: Registry re-fetched every 10 seconds; Session tab refreshes every 5 seconds
- **Markdown rendering**: Custom regex-based renderer handles headings, bold, italic, code blocks, lists, blockquotes, and horizontal rules
- **Toast notifications**: Success/error messages auto-dismiss after 3 seconds
- **State management**: React `useState` + `useEffect` — no external state library

---

## Legacy Static Version

The `dashboard/` root also contains a standalone HTML+JS+CSS version (`index.html`, `app.js`, `style.css`) that works without Node.js. It served the same purpose before the React rewrite and can still be accessed directly via the Python backend at `http://localhost:7474`.

---

## Integration with CLI

The dashboard shares the same data store (`~/.claude/workspace/registry.json`) as the `/workspace` slash commands:

| CLI Command | Dashboard Equivalent |
|-------------|----------------------|
| `/workspace add <name>` | "New Project" button |
| `/workspace task <project> <title>` | "Add task" on any project card |
| `/workspace run` | "Run Supervisor" button |
| `/workspace status` | The entire dashboard |

Changes made via CLI appear in the dashboard on the next auto-refresh cycle (up to 10 seconds). Changes made in the dashboard are immediately written to `registry.json` and visible to CLI commands.

---

## Configuration

### Ports

Default ports are defined in:
- `server.py` line 19: `PORT = 7474` (backend)
- `ui/vite.config.js`: `port: 7475` (frontend)

To change them, edit these files and update the proxy target in `vite.config.js` accordingly.

### Data Directory

The backend stores all data at `~/.claude/workspace/`. This path is defined in `server.py`:
```python
REGISTRY_PATH = Path.home() / ".claude" / "workspace" / "registry.json"
PROJECTS_DIR = Path.home() / ".claude" / "workspace" / "projects"
```
