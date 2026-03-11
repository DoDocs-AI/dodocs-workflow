import { useState, useEffect } from 'react'
import { api } from '../../api'

function TreeNode({ node, depth = 1 }) {
  const [open, setOpen] = useState(depth <= 1)
  if (node.type === 'file') {
    return <div className="tree-file" style={{ paddingLeft: depth * 16 }}>📄 {node.name}</div>
  }
  const children = node.children || []
  const childCount = children.length || node.child_count || 0
  return (
    <div className="tree-dir-wrap">
      <div className="tree-dir" style={{ paddingLeft: depth * 16 }} onClick={() => setOpen(v => !v)}>
        <span className="tree-arrow">{open ? '▼' : '▶'}</span>
        📁 {node.name}
        <span className="tree-count">{childCount}</span>
      </div>
      {open && children.length > 0 && (
        <div className="tree-children">
          {children.map((child, i) => <TreeNode key={i} node={child} depth={depth + 1} />)}
        </div>
      )}
    </div>
  )
}

export default function SourcesTab({ project }) {
  const [tree, setTree] = useState(null)

  useEffect(() => {
    api.tree(project.id).then(setTree).catch(() => setTree([]))
  }, [project.id])

  if (!tree) return <div className="loading">Scanning directory…</div>
  if (tree.length === 0) return <div className="empty-state" style={{ padding: 40 }}><h3>Empty or not found</h3></div>

  return (
    <div className="tree-root">
      <div className="tree-root-label">📂 {project.path || 'project root'}</div>
      <div className="tree-root-children">
        {tree.map((node, i) => <TreeNode key={i} node={node} depth={1} />)}
      </div>
    </div>
  )
}
