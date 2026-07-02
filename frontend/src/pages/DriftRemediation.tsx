import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { driftApi, type DriftPolicy } from '../api/client'
import { useToast } from '../contexts/ToastContext'
import Collapsible from '../components/Collapsible'

// Auto-eligible categories (IPAM-only safe actions). The rest are review-only.
const SAFE = ['orphan_dns', 'orphan_dhcp', 'mac_mismatch', 'active_but_available']
const REVIEW_ONLY = ['hostname_mismatch', 'multi_dhcp_scope', 'missing_dns']
const ALL = [...SAFE, ...REVIEW_ONLY]

const LABEL: Record<string, string> = {
  orphan_dns: 'Orphan DNS', orphan_dhcp: 'Orphan DHCP', mac_mismatch: 'MAC mismatch',
  active_but_available: 'Active but available', hostname_mismatch: 'Hostname mismatch',
  multi_dhcp_scope: 'Multi DHCP scope', missing_dns: 'Missing DNS',
}
const STATUSES = ['reserved', 'assigned', 'deprecated', 'available']

export default function DriftRemediation() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const { data: policies = [] } = useQuery({ queryKey: ['drift-policies'], queryFn: driftApi.listPolicies })
  const byCat = Object.fromEntries(policies.map((p: DriftPolicy) => [p.category, p]))

  const invalidate = () => qc.invalidateQueries({ queryKey: ['drift-policies'] })
  const upsert = useMutation({
    mutationFn: ({ category, body }: { category: string; body: any }) => driftApi.upsertPolicy(category, body),
    onSuccess: invalidate,
    onError: (e: any) => showToast(e?.response?.data?.detail ?? 'Save failed', 'error'),
  })
  const remove = useMutation({
    mutationFn: (category: string) => driftApi.deletePolicy(category),
    onSuccess: invalidate,
  })

  const setMode = (cat: string, mode: string) => {
    if (mode === 'off') { if (byCat[cat]) remove.mutate(cat); return }
    const cur = byCat[cat]
    upsert.mutate({ category: cat, body: {
      mode,
      dry_run: cur?.dry_run ?? true,
      params: cur?.params ?? (cat === 'active_but_available' ? { target_status: 'reserved' } : {}),
      enabled: true,
    }})
  }
  const setField = (cat: string, patch: any) => {
    const cur = byCat[cat]
    if (!cur) return
    upsert.mutate({ category: cat, body: { mode: cur.mode, dry_run: cur.dry_run, params: cur.params, enabled: cur.enabled, ...patch } })
  }

  return (
    <Collapsible title="Drift Auto-Remediation" storageKey="drift-remediation">
      <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginTop: 0 }}>
        Auto-fix open drift per category. Safe (IPAM-only) categories can run <strong>auto</strong>;
        the rest are <strong>review</strong>-only (flagged for a human). New auto policies default to
        <strong> dry-run</strong> — they log what they'd do until you turn it off. GitOps-managed resources are skipped.
      </p>
      <div className="table-wrap">
        <table>
          <thead><tr><th scope="col">Category</th><th scope="col">Mode</th><th scope="col">Dry-run</th><th scope="col">Status (active)</th></tr></thead>
          <tbody>
            {ALL.map(cat => {
              const p = byCat[cat]
              const safe = SAFE.includes(cat)
              return (
                <tr key={cat}>
                  <td>{LABEL[cat]}</td>
                  <td>
                    <select value={p?.mode ?? 'off'} onChange={e => setMode(cat, e.target.value)}>
                      <option value="off">off</option>
                      <option value="review">review</option>
                      {safe && <option value="auto">auto</option>}
                    </select>
                  </td>
                  <td>
                    {p?.mode === 'auto' ? (
                      <input type="checkbox" checked={p.dry_run} onChange={e => setField(cat, { dry_run: e.target.checked })} />
                    ) : <span className="text-muted">—</span>}
                  </td>
                  <td>
                    {cat === 'active_but_available' && p?.mode === 'auto' ? (
                      <select value={String(p.params?.target_status ?? 'reserved')}
                        onChange={e => setField(cat, { params: { target_status: e.target.value } })}>
                        {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                      </select>
                    ) : <span className="text-muted">—</span>}
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>
    </Collapsible>
  )
}
