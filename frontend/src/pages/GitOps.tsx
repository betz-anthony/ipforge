import { useState } from 'react'
import { useMutation } from '@tanstack/react-query'
import { GitBranch } from 'lucide-react'
import { gitopsApi, type GitopsPlan, type GitopsApplyResult } from '../api/client'
import { useToast } from '../contexts/ToastContext'

const SAMPLE = `source: prod-net
vlans:
  - { vlan_id: 10, name: servers }
subnets:
  - cidr: 10.0.0.0/24
    name: servers
    vlan_id: 10
    reserved_ranges:
      - { start: 10.0.0.1, kind: gateway, label: gw }
allocations:
  - { subnet: 10.0.0.0/24, hostname: web-01 }
`

function DiffBlock({ title, diff }: { title: string; diff?: { create: string[]; update: string[]; prune: string[] } }) {
  if (!diff) return null
  const n = diff.create.length + diff.update.length + diff.prune.length
  if (n === 0) return null
  return (
    <div style={{ marginBottom: '0.6rem' }}>
      <div className="detail-section-title">{title}</div>
      {diff.create.map(x => <div key={'c' + x} style={{ fontSize: '0.8rem' }}><span className="badge badge-green">create</span> <span className="font-mono">{x}</span></div>)}
      {diff.update.map(x => <div key={'u' + x} style={{ fontSize: '0.8rem' }}><span className="badge badge-yellow">update</span> <span className="font-mono">{x}</span></div>)}
      {diff.prune.map(x => <div key={'p' + x} style={{ fontSize: '0.8rem' }}><span className="badge badge-red">prune</span> <span className="font-mono">{x}</span></div>)}
    </div>
  )
}

export default function GitOpsPage() {
  const { showToast } = useToast()
  const [text, setText] = useState(SAMPLE)
  const [planResult, setPlanResult] = useState<GitopsPlan | null>(null)
  const [applyResult, setApplyResult] = useState<GitopsApplyResult | null>(null)

  const errMsg = (e: any) => e?.response?.data?.detail ?? 'Request failed'

  const planMut = useMutation({
    mutationFn: () => gitopsApi.plan(text),
    onSuccess: (r) => { setApplyResult(null); setPlanResult(r.plan) },
    onError: (e: any) => showToast(errMsg(e), 'error'),
  })

  const applyMut = useMutation({
    mutationFn: () => gitopsApi.apply(text),
    onSuccess: (r) => { setApplyResult(r); setPlanResult(r.plan); showToast('Applied', 'success') },
    onError: (e: any) => showToast(errMsg(e), 'error'),
  })

  return (
    <div style={{ maxWidth: 960 }}>
      <div className="page-header"><h1><GitBranch size={20} style={{ verticalAlign: '-3px' }} /> GitOps</h1></div>
      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)' }}>
        Declare VLANs, subnets, reserved ranges, and allocations as YAML. <strong>Plan</strong> shows the diff;
        <strong> Apply</strong> reconciles IPForge to match. Resources are namespaced by <code>source</code>;
        prune only affects rows this source created. Providers (DNS/DHCP) are never pruned.
      </p>

      <textarea
        value={text}
        onChange={e => setText(e.target.value)}
        rows={16}
        spellCheck={false}
        style={{ width: '100%', fontFamily: 'var(--font-mono)', fontSize: '0.8rem', resize: 'vertical' }}
      />

      <div className="form-actions" style={{ marginTop: '0.6rem' }}>
        <button className="btn-ghost" onClick={() => planMut.mutate()} disabled={planMut.isPending}>
          {planMut.isPending ? 'Planning…' : 'Plan'}
        </button>
        <button className="btn-primary" onClick={() => applyMut.mutate()} disabled={applyMut.isPending}>
          {applyMut.isPending ? 'Applying…' : 'Apply'}
        </button>
      </div>

      {planResult && (
        <div className="stat-card" style={{ padding: '0.75rem 1rem', marginTop: '1rem' }}>
          <div style={{ fontWeight: 600, marginBottom: '0.4rem' }}>{applyResult ? 'Applied plan' : 'Plan'}</div>
          <DiffBlock title="VLANs" diff={planResult.vlans} />
          <DiffBlock title="Subnets" diff={planResult.subnets} />
          <DiffBlock title="Reserved ranges" diff={planResult.reserved_ranges} />
          <DiffBlock title="Allocations" diff={planResult.allocations} />
          {Object.values(planResult).every(d => d.create.length + d.update.length + d.prune.length === 0) && (
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No changes — in sync.</p>
          )}
        </div>
      )}

      {applyResult && applyResult.errors.length > 0 && (
        <div className="stat-card" style={{ padding: '0.75rem 1rem', marginTop: '0.6rem' }}>
          <div className="detail-section-title">Errors</div>
          {applyResult.errors.map((e, i) => <div key={i} className="feedback-error" style={{ fontSize: '0.78rem' }}>{e}</div>)}
        </div>
      )}
    </div>
  )
}
