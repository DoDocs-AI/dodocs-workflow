/* AI Workspace OS Dashboard — app.js */
const API = '';
let registry = { version: '1.0', workspaces: [], projects: [] };
let activeWorkspace = 'all';
let currentView = 'list';   // 'list' | 'detail'
let currentProjectId = null;
let currentTab = 'overview';
let sessionRefreshTimer = null;
let detailDocs = [];

// ── Fetch helpers ──────────────────────────────────────────────────────────
async function fetchJSON(url) {
  const r = await fetch(url);
  if (!r.ok) throw new Error(`HTTP ${r.status}`);
  return r.json();
}

async function fetchRegistry() { return fetchJSON(`${API}/api/registry`); }

async function postJSON(url, body) {
  const r = await fetch(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });
  if (!r.ok) throw new Error(await r.text());
  return r.json();
}

// ── Toast ──────────────────────────────────────────────────────────────────
function toast(msg, type = 'success') {
  const el = document.getElementById('toast');
  el.textContent = msg;
  el.className = `toast ${type} show`;
  setTimeout(() => el.classList.remove('show'), 3000);
}

// ── Helpers ────────────────────────────────────────────────────────────────
const TYPE_ICONS   = { software:'⚙️', research:'🔬', content:'✍️', brainstorm:'💡', devops:'🚀', design:'🎨' };
const PHASE_LABELS = { ideation:'ideation', planning:'planning', ready:'ready', in_progress:'in progress', development:'development', review:'review', done:'done', paused:'paused' };
const STATUS_ICONS = { pending:'○', in_progress:'⏳', done:'✓', blocked:'🚫', cancelled:'✗' };

function esc(s) {
  if (!s) return '';
  return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;');
}

function fmtSize(bytes) {
  if (bytes < 1024) return bytes + 'B';
  if (bytes < 1024*1024) return (bytes/1024).toFixed(1) + 'KB';
  return (bytes/1024/1024).toFixed(1) + 'MB';
}

function fmtDate(iso) {
  if (!iso) return '';
  return new Date(iso).toLocaleDateString('en-US', { month:'short', day:'numeric', year:'numeric' });
}

function fmtTs(ts) {
  if (!ts) return '';
  const d = typeof ts === 'number' ? new Date(ts * 1000) : new Date(ts);
  return d.toLocaleString('en-US', { month:'short', day:'numeric', hour:'2-digit', minute:'2-digit' });
}

// ── Markdown renderer ──────────────────────────────────────────────────────
function renderMarkdown(raw) {
  if (!raw) return '<em class="text2">Empty</em>';
  const segments = raw.split(/(```(?:[a-z]*\n)?[\s\S]*?```)/g);
  let html = '';
  for (let i = 0; i < segments.length; i++) {
    const seg = segments[i];
    if (i % 2 === 1) {
      const inner = seg.replace(/^```[a-z]*\n?/, '').replace(/```$/, '');
      html += `<pre class="md-pre">${esc(inner)}</pre>`;
    } else {
      let t = esc(seg);
      t = t.replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>');
      t = t.replace(/^#{3} (.+)$/gm, '<h3 class="md-h3">$1</h3>');
      t = t.replace(/^#{2} (.+)$/gm, '<h2 class="md-h2">$1</h2>');
      t = t.replace(/^# (.+)$/gm, '<h1 class="md-h1">$1</h1>');
      t = t.replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>');
      t = t.replace(/\*([^*\n]+)\*/g, '<em>$1</em>');
      t = t.replace(/^&gt; (.+)$/gm, '<blockquote class="md-quote">$1</blockquote>');
      t = t.replace(/^[-*] (.+)$/gm, '<li class="md-li">$1</li>');
      t = t.replace(/^(\d+)\. (.+)$/gm, '<li class="md-li">$2</li>');
      t = t.replace(/(<li[^>]*>[\s\S]*?<\/li>\n?)+/g, m => `<ul class="md-ul">${m}</ul>`);
      t = t.replace(/^---+$/gm, '<hr class="md-hr">');
      t = t.replace(/\n{2,}/g, '</p><p class="md-p">');
      t = t.replace(/\n/g, '<br>');
      html += `<p class="md-p">${t}</p>`;
    }
  }
  return `<div class="md-body">${html}</div>`;
}

// ── Tree renderer ──────────────────────────────────────────────────────────
function renderTree(nodes, depth) {
  if (!nodes || nodes.length === 0) return '';
  return nodes.map(n => {
    if (n.type === 'file') {
      return `<div class="tree-file" style="padding-left:${depth*16}px">📄 ${esc(n.name)}</div>`;
    }
    const childCount = n.children ? n.children.length : (n.child_count || 0);
    const childHTML  = n.children && n.children.length > 0 ? renderTree(n.children, depth + 1) : '';
    const hasChildren = childHTML.length > 0;
    const id = 'tree-' + Math.random().toString(36).slice(2);
    return `<div class="tree-dir-wrap">
      <div class="tree-dir" style="padding-left:${depth*16}px" onclick="toggleTreeDir('${id}')">
        <span class="tree-arrow" id="arr-${id}">▶</span> 📁 ${esc(n.name)}
        <span class="tree-count">${childCount}</span>
      </div>
      <div id="${id}" class="tree-children" style="display:none">${childHTML}</div>
    </div>`;
  }).join('');
}

function toggleTreeDir(id) {
  const el = document.getElementById(id);
  const arr = document.getElementById('arr-' + id);
  if (!el) return;
  const open = el.style.display !== 'none';
  el.style.display = open ? 'none' : 'block';
  if (arr) arr.textContent = open ? '▶' : '▼';
}

// ── List view render ───────────────────────────────────────────────────────
function render() {
  if (currentView === 'detail') return;
  renderSidebar();
  renderBlocked();
  renderProjects();
}

function renderSidebar() {
  const { workspaces, projects } = registry;
  const wsContainer = document.getElementById('workspace-chips');
  const chips = ['all', ...workspaces].map(ws => {
    const count = ws === 'all' ? projects.length : projects.filter(p => p.workspace === ws).length;
    return `<button class="chip ${ws==='all'?'all':''} ${activeWorkspace===ws?'active':''}" onclick="setWorkspace('${ws}')">${ws} <small>(${count})</small></button>`;
  }).join('');
  wsContainer.innerHTML = chips;

  const total   = projects.length;
  const active  = projects.filter(p => p.status === 'active').length;
  const pending = projects.reduce((s,p) => s + p.tasks.filter(t=>t.status==='pending').length, 0);
  const blocked = projects.reduce((s,p) => s + p.tasks.filter(t=>t.status==='blocked').length, 0);
  document.getElementById('stat-total').textContent   = total;
  document.getElementById('stat-active').textContent  = active;
  document.getElementById('stat-pending').textContent = pending;
  document.getElementById('stat-blocked').textContent = blocked;
}

function renderBlocked() {
  const blocked = [];
  registry.projects.forEach(p => {
    p.tasks.filter(t=>t.status==='blocked').forEach(t => {
      blocked.push({ project: p.name, task: t.title, reason: t.blocked_reason });
    });
  });
  const banner = document.getElementById('blocked-banner');
  if (blocked.length === 0) { banner.classList.remove('visible'); return; }
  banner.classList.add('visible');
  document.getElementById('blocked-items').innerHTML = blocked.map(b =>
    `<div class="blocked-item">🚫 <strong>${esc(b.project)}</strong> → ${esc(b.task)}${b.reason ? ': ' + esc(b.reason) : ''}</div>`
  ).join('');
}

function renderProjects() {
  const container = document.getElementById('projects-grid');
  let projects = registry.projects;
  if (activeWorkspace !== 'all') projects = projects.filter(p => p.workspace === activeWorkspace);
  if (projects.length === 0) {
    container.innerHTML = `<div class="empty-state"><h3>No projects</h3><p>Click "New Project" or use <code>/workspace add</code> in any Claude session.</p></div>`;
    return;
  }
  container.innerHTML = projects.map(p => renderCard(p)).join('');
}

function renderCard(p) {
  const tasks   = p.tasks || [];
  const shown   = tasks.slice(0, 4);
  const overflow = tasks.length - shown.length;
  const taskHTML = tasks.length === 0
    ? '<div class="no-tasks">No tasks — click to add</div>'
    : shown.map(t => `
      <div class="task-item status-${t.status}">
        <span class="task-icon">${STATUS_ICONS[t.status]||'○'}</span>
        <div style="flex:1">
          <div class="task-title">${esc(t.title)}</div>
          ${t.blocked_reason ? `<div class="task-blocked-reason">${esc(t.blocked_reason)}</div>` : ''}
        </div>
        <span class="task-priority priority-${t.priority}">${t.priority}</span>
      </div>`).join('') + (overflow > 0 ? `<div class="tasks-overflow">+${overflow} more</div>` : '');

  return `<div class="card" onclick="openDetail('${p.id}')" title="Click for details" id="card-${p.id}">
    <div class="card-header">
      <div>
        <div class="card-title">${TYPE_ICONS[p.type]||''} ${esc(p.name)}</div>
        <div class="card-workspace">${p.workspace}</div>
      </div>
      <div class="card-badges">
        <span class="badge badge-${p.type}">${p.type}</span>
        <span class="badge badge-phase">${PHASE_LABELS[p.phase]||p.phase}</span>
      </div>
    </div>
    ${p.description ? `<div class="card-desc">${esc(p.description)}</div>` : ''}
    <div class="tasks-header">
      <span class="tasks-label">Tasks (${tasks.length})</span>
      <button class="add-task-btn" onclick="event.stopPropagation();toggleAddTask('${p.id}')">+ Add task</button>
    </div>
    <div class="task-list">${taskHTML}</div>
    <div class="add-task-form" id="form-${p.id}" onclick="event.stopPropagation()">
      <input class="form-input" id="task-title-${p.id}" placeholder="Task title…" />
      <div class="form-row">
        <select class="form-select" id="task-type-${p.id}">
          <option value="coding">coding</option><option value="research">research</option>
          <option value="review">review</option><option value="design">design</option>
          <option value="devops">devops</option><option value="content">content</option>
          <option value="other" selected>other</option>
        </select>
        <select class="form-select" id="task-priority-${p.id}">
          <option value="high">high</option><option value="medium" selected>medium</option><option value="low">low</option>
        </select>
        <button class="form-btn form-btn-submit" onclick="submitTask('${p.id}')">Add</button>
        <button class="form-btn form-btn-cancel" onclick="toggleAddTask('${p.id}')">Cancel</button>
      </div>
    </div>
  </div>`;
}

// ── List interactions ──────────────────────────────────────────────────────
function setWorkspace(ws) { activeWorkspace = ws; render(); }

function toggleAddTask(projectId) {
  document.getElementById(`form-${projectId}`).classList.toggle('visible');
}

async function submitTask(projectId) {
  const title = document.getElementById(`task-title-${projectId}`).value.trim();
  if (!title) { toast('Task title required', 'error'); return; }
  const type     = document.getElementById(`task-type-${projectId}`).value;
  const priority = document.getElementById(`task-priority-${projectId}`).value;
  try {
    await postJSON(`/api/projects/${projectId}/tasks`, { title, type, priority });
    toast(`Task "${title}" added`);
    await refresh();
  } catch(e) { toast('Failed: ' + e.message, 'error'); }
}

// ── New Project Modal ──────────────────────────────────────────────────────
function openNewProjectModal() { document.getElementById('modal').classList.add('visible'); }
function closeModal() { document.getElementById('modal').classList.remove('visible'); }

async function submitNewProject() {
  const name = document.getElementById('p-name').value.trim();
  if (!name) { toast('Name required', 'error'); return; }
  const body = {
    name,
    workspace:   document.getElementById('p-workspace').value,
    type:        document.getElementById('p-type').value,
    phase:       document.getElementById('p-phase').value,
    path:        document.getElementById('p-path').value.trim(),
    description: document.getElementById('p-desc').value.trim(),
  };
  try {
    await postJSON('/api/projects', body);
    toast(`Project "${name}" created`);
    closeModal();
    ['p-name','p-path','p-desc'].forEach(id => document.getElementById(id).value = '');
    await refresh();
  } catch(e) { toast('Failed: ' + e.message, 'error'); }
}

// ── Supervisor ─────────────────────────────────────────────────────────────
async function runSupervisor() {
  const btn = document.getElementById('run-btn');
  btn.disabled = true; btn.classList.add('running');
  btn.querySelector('.btn-label').textContent = 'Running…';
  try {
    const res = await postJSON('/api/supervisor/run', {});
    toast(`Supervisor started (PID ${res.pid})`);
    setTimeout(refresh, 3000); setTimeout(refresh, 8000); setTimeout(refresh, 15000);
  } catch(e) { toast('Failed: ' + e.message, 'error'); }
  finally {
    btn.disabled = false; btn.classList.remove('running');
    btn.querySelector('.btn-label').textContent = 'Run Supervisor';
  }
}

// ── Detail view ────────────────────────────────────────────────────────────
function openDetail(projectId) {
  currentView = 'detail';
  currentProjectId = projectId;
  currentTab = 'overview';
  document.getElementById('list-view').style.display  = 'none';
  document.getElementById('detail-view').style.display = 'block';
  const project = registry.projects.find(p => p.id === projectId);
  if (project) renderDetailPage(project);
}

function closeDetail() {
  currentView = 'list';
  currentProjectId = null;
  if (sessionRefreshTimer) { clearInterval(sessionRefreshTimer); sessionRefreshTimer = null; }
  document.getElementById('detail-view').style.display = 'none';
  document.getElementById('list-view').style.display   = 'block';
  render();
}

function updateDetailHeader(project) {
  document.getElementById('detail-name').textContent = project.name;
  document.getElementById('detail-meta').innerHTML = `
    <span class="badge badge-${project.type}">${project.type}</span>
    <span class="badge badge-phase">${PHASE_LABELS[project.phase]||project.phase}</span>
    <span class="badge" style="background:var(--surface2);color:var(--text2)">${project.workspace}</span>
    ${project.status !== 'active' ? `<span class="badge" style="background:rgba(248,81,73,.15);color:var(--red)">${project.status}</span>` : ''}
  `;
  const phaseSelect = document.getElementById('detail-phase-select');
  if (phaseSelect) phaseSelect.value = project.phase;
  const el = document.getElementById('tab-count-tasks');
  if (el) el.textContent = (project.tasks||[]).length > 0 ? (project.tasks||[]).length : '';
}

function renderDetailPage(project) {
  updateDetailHeader(project);
  switchTab('overview');
}

function switchTab(tab) {
  currentTab = tab;
  // Update tab buttons
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  const activeBtn = document.querySelector(`.tab-btn[data-tab="${tab}"]`);
  if (activeBtn) activeBtn.classList.add('active');
  // Show/hide tab content
  document.querySelectorAll('.tab-content').forEach(c => c.style.display = 'none');
  const el = document.getElementById(`tab-${tab}`);
  if (el) el.style.display = 'block';
  // Cancel session refresh if switching away from session tab
  if (tab !== 'session' && sessionRefreshTimer) {
    clearInterval(sessionRefreshTimer); sessionRefreshTimer = null;
  }
  // Load content
  loadTabContent(tab);
}

function loadTabContent(tab) {
  const project = registry.projects.find(p => p.id === currentProjectId);
  if (!project) return;
  if (tab === 'overview')  renderOverviewTab(project);
  if (tab === 'tasks')     renderTasksTab(project);
  if (tab === 'docs')      loadDocsTab(project.id);
  if (tab === 'sources')   loadSourcesTab(project.id);
  if (tab === 'session')   loadSessionTab(project.id);
}

// ── Overview tab ───────────────────────────────────────────────────────────
function renderOverviewTab(project) {
  const tasks   = project.tasks || [];
  const done    = tasks.filter(t=>t.status==='done');
  const pending = tasks.filter(t=>t.status==='pending');
  const inprog  = tasks.filter(t=>t.status==='in_progress');
  const blocked = tasks.filter(t=>t.status==='blocked');

  const featuresHTML = done.length > 0
    ? `<div class="overview-section">
        <div class="overview-section-title">Features Implemented (${done.length})</div>
        ${done.map(t => `<div class="feature-item">✓ ${esc(t.title)}</div>`).join('')}
      </div>`
    : '';

  const inProgHTML = inprog.length > 0
    ? `<div class="overview-section">
        <div class="overview-section-title">In Progress (${inprog.length})</div>
        ${inprog.map(t => `<div class="feature-item inprog">⏳ ${esc(t.title)}</div>`).join('')}
      </div>`
    : '';

  const blockedHTML = blocked.length > 0
    ? `<div class="overview-section blocked-section">
        <div class="overview-section-title">Blocked (${blocked.length})</div>
        ${blocked.map(t => `<div class="feature-item blocked">🚫 ${esc(t.title)} ${t.blocked_reason ? `<span class="text2">— ${esc(t.blocked_reason)}</span>` : ''}</div>`).join('')}
      </div>`
    : '';

  document.getElementById('tab-overview').innerHTML = `
    <div class="overview-layout">
      <div class="overview-main">
        <div class="detail-info-grid">
          <div class="info-row"><span class="info-label">Path</span><code class="info-path">${esc(project.path||'—')}</code></div>
          <div class="info-row"><span class="info-label">Description</span><span>${esc(project.description||'—')}</span></div>
          <div class="info-row"><span class="info-label">Created</span><span>${fmtDate(project.created_at)}</span></div>
          <div class="info-row"><span class="info-label">Updated</span><span>${fmtDate(project.updated_at)}</span></div>
          <div class="info-row">
            <span class="info-label">Tasks</span>
            <span>
              <span class="mini-badge green">${done.length} done</span>
              <span class="mini-badge blue">${inprog.length} in progress</span>
              <span class="mini-badge yellow">${pending.length} pending</span>
              ${blocked.length > 0 ? `<span class="mini-badge red">${blocked.length} blocked</span>` : ''}
            </span>
          </div>
        </div>
        ${featuresHTML}${inProgHTML}${blockedHTML}
      </div>
      <div class="overview-context" id="overview-context">
        <div class="overview-section-title">Context Notes</div>
        <div class="text2" style="font-size:12px">Loading…</div>
      </div>
    </div>`;

  // Load context.md async
  fetchJSON(`/api/projects/${project.id}/context`)
    .then(d => {
      const el = document.getElementById('overview-context');
      if (el) el.innerHTML = `<div class="overview-section-title">Context Notes</div>${renderMarkdown(d.content)}`;
    })
    .catch(() => {});
}

// ── Tasks tab ──────────────────────────────────────────────────────────────
function renderTasksTab(project) {
  const tasks = project.tasks || [];
  const el = document.getElementById('tab-tasks');

  const taskRows = tasks.length === 0
    ? '<div class="no-tasks" style="padding:24px">No tasks yet</div>'
    : tasks.map(t => `
      <div class="detail-task-row status-${t.status}">
        <div class="detail-task-main">
          <span class="detail-task-icon">${STATUS_ICONS[t.status]||'○'}</span>
          <div class="detail-task-info">
            <div class="detail-task-title">${esc(t.title)}</div>
            <div class="detail-task-meta">
              <span class="mini-badge">${t.type||'other'}</span>
              <span class="task-priority priority-${t.priority}">${t.priority}</span>
              ${t.agent_spawned ? `<span class="mini-badge blue">agent: ${esc(t.agent_spawned)}</span>` : ''}
              <span class="text2" style="font-size:11px">${fmtDate(t.created_at)}</span>
            </div>
            ${t.result ? `<div class="task-result">Result: ${esc(t.result)}</div>` : ''}
            ${t.blocked_reason ? `<div class="task-blocked-reason">Blocked: ${esc(t.blocked_reason)}</div>` : ''}
          </div>
        </div>
      </div>`).join('');

  el.innerHTML = `
    <div class="tasks-list-detail">${taskRows}</div>
    <div class="detail-add-task-section">
      <div class="overview-section-title">Add Task</div>
      <div class="detail-add-task-form">
        <input class="form-input" id="dt-title" placeholder="Task title…" style="flex:1" />
        <select class="form-select" id="dt-type">
          <option value="coding">coding</option><option value="research">research</option>
          <option value="review">review</option><option value="design">design</option>
          <option value="devops">devops</option><option value="content">content</option>
          <option value="other" selected>other</option>
        </select>
        <select class="form-select" id="dt-priority">
          <option value="high">high</option><option value="medium" selected>medium</option><option value="low">low</option>
        </select>
        <button class="form-btn form-btn-submit" onclick="submitDetailTask('${project.id}')">Add Task</button>
      </div>
    </div>`;
}

async function submitDetailTask(projectId) {
  const title    = document.getElementById('dt-title').value.trim();
  if (!title) { toast('Title required', 'error'); return; }
  const type     = document.getElementById('dt-type').value;
  const priority = document.getElementById('dt-priority').value;
  try {
    await postJSON(`/api/projects/${projectId}/tasks`, { title, type, priority });
    toast(`Task added`);
    registry = await fetchRegistry();
    const project = registry.projects.find(p => p.id === projectId);
    if (project) { renderDetailPage(project); switchTab('tasks'); }
  } catch(e) { toast('Failed: ' + e.message, 'error'); }
}

// ── Docs tab ───────────────────────────────────────────────────────────────
async function loadDocsTab(projectId) {
  const el = document.getElementById('tab-docs');
  el.innerHTML = '<div class="loading">Loading documentation…</div>';
  try {
    const docs = await fetchJSON(`/api/projects/${projectId}/docs`);
    detailDocs = docs;
    if (docs.length === 0) {
      el.innerHTML = '<div class="empty-state" style="padding:40px"><h3>No docs found</h3><p>No .md or .txt files found in project directory</p></div>';
      return;
    }
    el.innerHTML = `
      <div class="docs-layout">
        <div class="docs-filelist" id="docs-filelist">
          ${docs.map((d,i) => `
            <div class="docs-fileitem" id="dfi-${i}" onclick="loadDoc('${projectId}','${esc(d.rel_path)}','${esc(d.name)}',${i})">
              <div class="docs-fname">${esc(d.name)}</div>
              <div class="docs-fmeta">${esc(d.rel_path)} · ${fmtSize(d.size)}</div>
            </div>`).join('')}
        </div>
        <div class="docs-viewer" id="docs-viewer">
          <div class="text2" style="padding:24px;text-align:center">Select a file to read</div>
        </div>
      </div>`;
    // Auto-load first file
    if (docs.length > 0) loadDoc(projectId, docs[0].rel_path, docs[0].name, 0);
  } catch(e) {
    el.innerHTML = `<div class="error-msg">Failed to load docs: ${esc(e.message)}</div>`;
  }
}

async function loadDoc(projectId, relPath, name, idx) {
  // Highlight selected
  document.querySelectorAll('.docs-fileitem').forEach(el => el.classList.remove('active'));
  const item = document.getElementById(`dfi-${idx}`);
  if (item) item.classList.add('active');

  const viewer = document.getElementById('docs-viewer');
  if (!viewer) return;
  viewer.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const d = await fetchJSON(`/api/projects/${projectId}/doc?file=${encodeURIComponent(relPath)}`);
    if (d.error) {
      viewer.innerHTML = `<div class="error-msg">${esc(d.error)}</div>`;
      return;
    }
    const isCode = relPath.endsWith('.jsonl');
    viewer.innerHTML = `
      <div class="docs-viewer-header">
        <strong>${esc(name)}</strong>
        <span class="text2" style="font-size:11px">${esc(relPath)} · ${fmtSize(d.size||0)}</span>
      </div>
      ${isCode
        ? `<pre class="md-pre" style="margin-top:12px">${esc(d.content)}</pre>`
        : renderMarkdown(d.content)}`;
  } catch(e) {
    viewer.innerHTML = `<div class="error-msg">Error: ${esc(e.message)}</div>`;
  }
}

// ── Sources tab ────────────────────────────────────────────────────────────
async function loadSourcesTab(projectId) {
  const el = document.getElementById('tab-sources');
  el.innerHTML = '<div class="loading">Scanning directory…</div>';
  try {
    const tree = await fetchJSON(`/api/projects/${projectId}/tree`);
    if (!tree || tree.length === 0) {
      el.innerHTML = '<div class="empty-state" style="padding:40px"><h3>Empty or not found</h3></div>';
      return;
    }
    const project = registry.projects.find(p => p.id === projectId);
    el.innerHTML = `
      <div class="tree-root">
        <div class="tree-root-label">📂 ${esc(project?.path || 'project root')}</div>
        <div class="tree-root-children">${renderTree(tree, 1)}</div>
      </div>`;
    // Auto-expand all root-level dirs
    document.querySelectorAll('.tree-dir').forEach(d => {
      const id = d.getAttribute('onclick')?.match(/'([^']+)'/)?.[1];
      if (id) { const ch = document.getElementById(id); const arr = document.getElementById('arr-'+id); if(ch){ch.style.display='block'; if(arr)arr.textContent='▼';} }
    });
  } catch(e) {
    el.innerHTML = `<div class="error-msg">Error: ${esc(e.message)}</div>`;
  }
}

// ── Session tab ────────────────────────────────────────────────────────────
async function loadSessionTab(projectId) {
  const el = document.getElementById('tab-session');
  el.innerHTML = '<div class="loading">Loading session data…</div>';
  try {
    await renderSessionContent(projectId);
  } catch(e) {
    el.innerHTML = `<div class="error-msg">Error: ${esc(e.message)}</div>`;
  }
  // Auto-refresh every 5s
  if (sessionRefreshTimer) clearInterval(sessionRefreshTimer);
  sessionRefreshTimer = setInterval(() => {
    if (currentTab === 'session' && currentProjectId === projectId) renderSessionContent(projectId);
  }, 5000);
}

async function renderSessionContent(projectId) {
  const el = document.getElementById('tab-session');
  if (!el) return;
  const data = await fetchJSON(`/api/projects/${projectId}/session`);

  const logHTML = data.log.length === 0
    ? '<div class="no-tasks">No agent activity logged yet</div>'
    : [...data.log].reverse().map(e => `
      <div class="session-entry status-${e.status||'info'}">
        <span class="session-ts">${fmtTs(e.ts)}</span>
        <span class="session-task">${esc(e.task_id||'')}</span>
        <span class="session-agent">${esc(e.agent||'')}</span>
        <span class="session-status ${e.status==='blocked'?'red':e.status==='done'?'green':''}">${esc(e.status||'')}</span>
        <span class="session-summary">${esc(e.summary||'')}</span>
      </div>`).join('');

  const TYPE_ICONS_S = { 'session-txt':'📝', 'task-md':'✅', 'jsonl':'🗂️' };
  const filesHTML = data.sessions.length === 0
    ? '<div class="no-tasks">No session files found in project directory</div>'
    : data.sessions.map((f,i) => `
      <div class="session-file-item" onclick="loadSessionFile('${projectId}','${esc(f.rel_path)}','${esc(f.name)}')">
        <span>${TYPE_ICONS_S[f.type]||'📄'} ${esc(f.name)}</span>
        <span class="text2" style="font-size:11px">${fmtSize(f.size)} · ${fmtTs(f.modified)}</span>
      </div>`).join('');

  el.innerHTML = `
    <div class="session-layout">
      <div class="session-left">
        <div class="session-section-title">Agent Activity Log <span class="refresh-dot"></span></div>
        <div class="session-log">${logHTML}</div>
        <div class="session-section-title" style="margin-top:20px">Session Files in Project</div>
        <div class="session-files">${filesHTML}</div>
      </div>
      <div class="session-right" id="session-file-viewer">
        <div class="text2" style="padding:24px;text-align:center">Select a file to view</div>
      </div>
    </div>`;
}

async function loadSessionFile(projectId, relPath, name) {
  const viewer = document.getElementById('session-file-viewer');
  if (!viewer) return;
  viewer.innerHTML = '<div class="loading">Loading…</div>';
  try {
    const d = await fetchJSON(`/api/projects/${projectId}/doc?file=${encodeURIComponent(relPath)}`);
    if (d.error) { viewer.innerHTML = `<div class="error-msg">${esc(d.error)}</div>`; return; }
    viewer.innerHTML = `
      <div class="docs-viewer-header"><strong>${esc(name)}</strong><span class="text2" style="font-size:11px">${fmtSize(d.size||0)}</span></div>
      <pre class="md-pre" style="margin-top:12px;max-height:600px;overflow-y:auto">${esc(d.content)}</pre>`;
  } catch(e) {
    viewer.innerHTML = `<div class="error-msg">Error: ${esc(e.message)}</div>`;
  }
}

// ── Phase update ───────────────────────────────────────────────────────────
async function updatePhase() {
  const phase = document.getElementById('detail-phase-select').value;
  if (!currentProjectId) return;
  try {
    await postJSON(`/api/projects/${currentProjectId}`, { phase });
    registry = await fetchRegistry();
    const project = registry.projects.find(p => p.id === currentProjectId);
    if (project) {
      document.getElementById('detail-meta').innerHTML = `
        <span class="badge badge-${project.type}">${project.type}</span>
        <span class="badge badge-phase">${PHASE_LABELS[project.phase]||project.phase}</span>
        <span class="badge" style="background:var(--surface2);color:var(--text2)">${project.workspace}</span>`;
      toast(`Phase updated to ${phase}`);
    }
  } catch(e) { toast('Failed: ' + e.message, 'error'); }
}

// ── Refresh ────────────────────────────────────────────────────────────────
async function refresh() {
  try {
    registry = await fetchRegistry();
    if (currentView === 'list') {
      render();
    } else if (currentView === 'detail' && currentProjectId) {
      renderSidebar();
      const project = registry.projects.find(p => p.id === currentProjectId);
      if (project) updateDetailHeader(project);
    }
  } catch(e) { console.error('Refresh failed:', e); }
}

function startAutoRefresh() {
  refresh();
  setInterval(refresh, 10000);
}

// ── Init ───────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
  startAutoRefresh();
  document.getElementById('modal').addEventListener('click', e => {
    if (e.target === document.getElementById('modal')) closeModal();
  });
});
