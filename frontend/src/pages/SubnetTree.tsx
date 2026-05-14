import { useState, useMemo } from 'react'
import { ChevronRight, ChevronDown } from 'lucide-react'
import type { Subnet } from '../api/client'
import UtilBar from '../components/UtilBar'

interface TreeNode {
  subnet: Subnet
  children: TreeNode[]
}

function buildTree(subnets: Subnet[]): TreeNode[] {
  const map = new Map<number, TreeNode>()
  for (const s of subnets) {
    map.set(s.id, { subnet: s, children: [] })
  }
  const roots: TreeNode[] = []
  for (const s of subnets) {
    const node = map.get(s.id)!
    if (s.parent_id == null) {
      roots.push(node)
    } else {
      const parent = map.get(s.parent_id)
      if (parent) {
        parent.children.push(node)
      } else {
        roots.push(node)  // orphaned node, treat as root
      }
    }
  }
  return roots
}

function collectAllIds(nodes: TreeNode[]): Set<number> {
  const ids = new Set<number>()
  function walk(node: TreeNode) {
    ids.add(node.subnet.id)
    for (const c of node.children) walk(c)
  }
  for (const n of nodes) walk(n)
  return ids
}

interface TreeNodeRowProps {
  node: TreeNode
  depth: number
  selectedId: number | null
  onSelect: (subnet: Subnet) => void
  expandedIds: Set<number>
  toggleExpand: (id: number) => void
  warnAt: number
  criticalAt: number
}

function TreeNodeRow({ node, depth, selectedId, onSelect, expandedIds, toggleExpand, warnAt, criticalAt }: TreeNodeRowProps) {
  const { subnet, children } = node
  const isSelected = subnet.id === selectedId
  const isExpanded = expandedIds.has(subnet.id)
  const hasChildren = children.length > 0
  const pct = subnet.rollup_utilization_pct
  const utilColor = pct >= criticalAt
    ? 'var(--danger, #f87171)'
    : pct >= warnAt
    ? 'var(--warning, #facc15)'
    : 'var(--success, #4ade80)'

  return (
    <>
      <div
        onClick={() => onSelect(subnet)}
        style={{
          display: 'flex', alignItems: 'center', gap: '0.35rem',
          padding: `0.3rem 0.75rem 0.3rem ${0.5 + depth * 1.25}rem`,
          cursor: 'pointer',
          background: isSelected ? 'var(--surface-selected, #252545)' : undefined,
          borderLeft: isSelected ? '2px solid var(--primary, #3b82f6)' : '2px solid transparent',
        }}
      >
        <span
          style={{ width: 14, flexShrink: 0, color: 'var(--text-muted)', display: 'flex', alignItems: 'center' }}
          onClick={e => { e.stopPropagation(); if (hasChildren) toggleExpand(subnet.id) }}
        >
          {hasChildren
            ? (isExpanded ? <ChevronDown size={12} /> : <ChevronRight size={12} />)
            : null}
        </span>
        <span style={{ flex: 1, minWidth: 0, overflow: 'hidden' }}>
          <span style={{ fontSize: '0.8rem', display: 'block', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
            {subnet.name}
            {!isExpanded && hasChildren && (
              <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginLeft: '0.35rem' }}>
                ({children.length})
              </span>
            )}
          </span>
          <span className="font-mono" style={{ fontSize: '0.65rem', color: 'var(--text-muted)' }}>
            {subnet.cidr}
          </span>
        </span>
        <span style={{ fontSize: '0.68rem', color: utilColor, flexShrink: 0 }}>
          {pct.toFixed(1)}%
        </span>
      </div>
      {isExpanded && children.map(c => (
        <TreeNodeRow
          key={c.subnet.id}
          node={c}
          depth={depth + 1}
          selectedId={selectedId}
          onSelect={onSelect}
          expandedIds={expandedIds}
          toggleExpand={toggleExpand}
          warnAt={warnAt}
          criticalAt={criticalAt}
        />
      ))}
    </>
  )
}

interface Props {
  subnets: Subnet[]
  warnAt: number
  criticalAt: number
  onSelect: (subnet: Subnet) => void
  selectedId?: number | null
}

export default function SubnetTree({ subnets, warnAt, criticalAt, onSelect, selectedId }: Props) {
  const roots = useMemo(() => buildTree(subnets), [subnets])
  const [expandedIds, setExpandedIds] = useState<Set<number>>(() => collectAllIds(roots))

  const toggleExpand = (id: number) => {
    setExpandedIds(prev => {
      const next = new Set(prev)
      if (next.has(id)) next.delete(id); else next.add(id)
      return next
    })
  }

  const selected = selectedId != null ? subnets.find(s => s.id === selectedId) ?? null : null
  const parentSubnet = selected?.parent_id != null
    ? subnets.find(s => s.id === selected.parent_id) ?? null
    : null
  const directChildren = selected
    ? subnets.filter(s => s.parent_id === selected.id)
    : []

  return (
    <div style={{ display: 'flex', height: '100%', border: '1px solid var(--border)', borderRadius: '6px', overflow: 'hidden' }}>
      {/* Left: tree panel */}
      <div style={{ width: 260, flexShrink: 0, borderRight: '1px solid var(--border)', overflowY: 'auto' }}>
        {roots.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', padding: '1rem' }}>No subnets.</p>
        ) : roots.map(node => (
          <TreeNodeRow
            key={node.subnet.id}
            node={node}
            depth={0}
            selectedId={selectedId ?? null}
            onSelect={onSelect}
            expandedIds={expandedIds}
            toggleExpand={toggleExpand}
            warnAt={warnAt}
            criticalAt={criticalAt}
          />
        ))}
      </div>

      {/* Right: detail panel */}
      <div style={{ flex: 1, padding: '1rem', overflowY: 'auto' }}>
        {!selected ? (
          <p style={{ color: 'var(--text-muted)', fontSize: '0.85rem', marginTop: '2rem', textAlign: 'center' }}>
            Select a subnet
          </p>
        ) : (
          <>
            <div style={{ marginBottom: '1rem' }}>
              <h3 style={{ margin: 0, fontSize: '1rem' }}>{selected.name}</h3>
              <span className="font-mono" style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>{selected.cidr}</span>
            </div>

            <div className="detail-fields">
              <div className="detail-field">
                <span className="detail-field-label">IP Version</span>
                <span className="detail-field-value">
                  <span className="badge badge-blue">IPv{selected.ip_version}</span>
                </span>
              </div>
              <div className="detail-field">
                <span className="detail-field-label">VLAN</span>
                <span className="detail-field-value">{selected.vlan_id ?? <span className="text-muted">—</span>}</span>
              </div>
              {selected.description && (
                <div className="detail-field">
                  <span className="detail-field-label">Description</span>
                  <span className="detail-field-value">{selected.description}</span>
                </div>
              )}
              <div className="detail-field">
                <span className="detail-field-label">Utilization (rollup)</span>
                <span className="detail-field-value" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <UtilBar pct={selected.rollup_utilization_pct} warn={warnAt} critical={criticalAt} />
                  <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                    {selected.rollup_used_count} / {selected.rollup_total_count}
                  </span>
                </span>
              </div>
            </div>

            <div style={{ marginTop: '1rem' }}>
              <div className="detail-section-title">Parent</div>
              {parentSubnet ? (
                <div
                  style={{ fontSize: '0.8rem', cursor: 'pointer', color: 'var(--primary, #3b82f6)', marginTop: '0.25rem' }}
                  onClick={() => onSelect(parentSubnet)}
                >
                  {parentSubnet.name}
                  <span className="font-mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                    {parentSubnet.cidr}
                  </span>
                </div>
              ) : (
                <span style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>None (root subnet)</span>
              )}
            </div>

            {directChildren.length > 0 && (
              <div style={{ marginTop: '1rem' }}>
                <div className="detail-section-title">Direct Children ({directChildren.length})</div>
                {directChildren.map(c => (
                  <div
                    key={c.id}
                    style={{ fontSize: '0.8rem', cursor: 'pointer', color: 'var(--primary, #3b82f6)', padding: '0.15rem 0' }}
                    onClick={() => onSelect(c)}
                  >
                    {c.name}
                    <span className="font-mono" style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                      {c.cidr}
                    </span>
                  </div>
                ))}
              </div>
            )}
          </>
        )}
      </div>
    </div>
  )
}
