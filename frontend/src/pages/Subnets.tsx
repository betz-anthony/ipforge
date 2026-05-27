import { useState, useMemo, useEffect, useRef } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Scan, AlertTriangle, GitBranch, Download, Upload } from 'lucide-react'
import { subnetsApi, dhcpApi, addressesApi, scanApi, settingsApi, importExportApi, grantsApi, groupsApi, usersApi, type Subnet, type DHCPScope, type Collision, type ImportResult } from '../api/client'
import { ipInCidr, ipCompare } from '../utils/ip'
import DetailDrawer from '../components/DetailDrawer'
import UtilBar from '../components/UtilBar'
import CollisionResolveDialog from './CollisionResolveDialog'
import SubnetTree from './SubnetTree'
import ConfirmModal from '../components/ConfirmModal'
import SearchInput from '../components/SearchInput'
import { useTableSort } from '../hooks/useTableSort'
import { useToast } from '../contexts/ToastContext'
import { useAuth } from '../contexts/AuthContext'
import { rowActivation } from '../utils/a11y'

function SubnetGrants({ subnetId }: { subnetId: number }) {
  const qc = useQueryClient()
  const [principal, setPrincipal] = useState('')   // "user:ID" | "group:ID"
  const [permission, setPermission] = useState<'view' | 'manage'>('view')

  const { data: grants } = useQuery({
    queryKey: ['grants', subnetId],
    queryFn: () => grantsApi.list({ subnet_id: subnetId }),
  })
  const { data: users }  = useQuery({ queryKey: ['users'], queryFn: usersApi.list })
  const { data: groups } = useQuery({ queryKey: ['groups'], queryFn: groupsApi.list })

  const createMut = useMutation({
    mutationFn: () => {
      const [kind, id] = principal.split(':')
      return grantsApi.create({
        subnet_id: subnetId,
        permission,
        ...(kind === 'user' ? { user_id: Number(id) } : { group_id: Number(id) }),
      })
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['grants', subnetId] }); setPrincipal('') },
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => grantsApi.remove(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['grants', subnetId] }),
  })

  const labelFor = (g: { user_id: number | null; group_id: number | null }) => {
    if (g.user_id != null) {
      return 'user: ' + ((users ?? []).find(u => u.id === g.user_id)?.username ?? g.user_id)
    }
    return 'group: ' + ((groups ?? []).find(x => x.id === g.group_id)?.name ?? g.group_id)
  }

  return (
    <div>
      {(grants ?? []).map(g => (
        <div key={g.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <span style={{ flex: 1 }}>{labelFor(g)} <span className="text-muted">({g.permission})</span></span>
          <button className="btn-ghost btn-sm" aria-label="Remove grant"
                  onClick={() => deleteMut.mutate(g.id)}>
            <X size={12} />
          </button>
        </div>
      ))}
      {(grants ?? []).length === 0 && <div className="text-muted">No grants.</div>}
      <div className="form-actions">
        <select value={principal} onChange={e => setPrincipal(e.target.value)}>
          <option value="">Select principal…</option>
          {(users ?? []).map(u => <option key={'u' + u.id} value={`user:${u.id}`}>user: {u.username}</option>)}
          {(groups ?? []).map(x => <option key={'g' + x.id} value={`group:${x.id}`}>group: {x.name}</option>)}
        </select>
        <select value={permission} onChange={e => setPermission(e.target.value as 'view' | 'manage')}>
          <option value="view">view</option>
          <option value="manage">manage</option>
        </select>
        <button className="btn-primary btn-sm" disabled={!principal}
                onClick={() => createMut.mutate()}>Add grant</button>
      </div>
    </div>
  )
}

const emptyForm = { name: '', cidr: '', vlan_id: '', description: '', scan_interval_minutes: '', dns_provider_name: '', dhcp_provider_name: '' }

const emptyEditForm = { name: '', vlan_id: '', description: '', notes: '', scan_interval_minutes: '', dns_provider_name: '', dhcp_provider_name: '', request_eligible: false }

export default function Subnets() {
  const [showForm, setShowForm]             = useState(false)
  const [form, setForm]                     = useState(emptyForm)
  const [selectedSubnet, setSelectedSubnet] = useState<Subnet | null>(null)
  const [editForm, setEditForm]             = useState(emptyEditForm)
  const qc = useQueryClient()
  const [showRangePicker, setShowRangePicker] = useState(false)
  const [rangeForm, setRangeForm]             = useState({ start_ip: '', end_ip: '' })

  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)

  const [formParentId, setFormParentId]                 = useState<number | null>(null)
  const [parentCandidates, setParentCandidates]         = useState<Subnet[]>([])
  const [editParentId, setEditParentId]                 = useState<number | null | undefined>(undefined)
  const [editParentCandidates, setEditParentCandidates] = useState<Subnet[]>([])
  const suggestTimerRef     = useRef<ReturnType<typeof setTimeout> | null>(null)
  const editSuggestTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  const { data: allScopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
  })

  // Debounced suggest-parent for create form
  useEffect(() => {
    if (suggestTimerRef.current) clearTimeout(suggestTimerRef.current)
    if (!form.cidr) { setParentCandidates([]); return }
    let cancelled = false
    suggestTimerRef.current = setTimeout(async () => {
      try {
        const results = await subnetsApi.suggestParent(form.cidr)
        if (!cancelled) setParentCandidates(results)
      } catch {
        if (!cancelled) setParentCandidates([])
      }
    }, 300)
    return () => {
      cancelled = true
      if (suggestTimerRef.current) clearTimeout(suggestTimerRef.current)
    }
  }, [form.cidr])

  // Debounced suggest-parent for edit form (uses selectedSubnet.cidr — CIDR is immutable in edit)
  useEffect(() => {
    if (!selectedSubnet) return
    if (editSuggestTimerRef.current) clearTimeout(editSuggestTimerRef.current)
    let cancelled = false
    editSuggestTimerRef.current = setTimeout(async () => {
      try {
        const results = await subnetsApi.suggestParent(selectedSubnet.cidr)
        if (!cancelled) setEditParentCandidates(results)
      } catch {
        if (!cancelled) setEditParentCandidates([])
      }
    }, 300)
    return () => {
      cancelled = true
      if (editSuggestTimerRef.current) clearTimeout(editSuggestTimerRef.current)
    }
  }, [selectedSubnet?.cidr])

  const { data: subnetAddresses } = useQuery({
    queryKey: ['addresses', selectedSubnet?.id],
    queryFn: () => addressesApi.list({ subnet_id: selectedSubnet!.id }),
    enabled: !!selectedSubnet,
  })

  const matchedScopes = useMemo((): DHCPScope[] => {
    if (!selectedSubnet || !allScopes) return []
    return allScopes.filter(s =>
      s.ip_version === selectedSubnet.ip_version &&
      s.start_range &&
      ipInCidr(s.start_range, selectedSubnet.cidr)
    )
  }, [selectedSubnet, allScopes])

  const { data: scanStatus, refetch: refetchScan } = useQuery({
    queryKey: ['scan-status', selectedSubnet?.id],
    queryFn: () => scanApi.status(selectedSubnet!.id),
    enabled: !!selectedSubnet,
    refetchInterval: (query) => query.state.data?.status === 'running' ? 3000 : false,
  })

  const { data: subnetCollisions } = useQuery({
    queryKey: ['collisions', selectedSubnet?.id],
    queryFn: () => scanApi.collisions({ resolved: false, subnet_id: selectedSubnet!.id }),
    enabled: !!selectedSubnet,
  })

  const { data: allUnresolvedCollisions } = useQuery({
    queryKey: ['collisions-all'],
    queryFn: () => scanApi.collisions({ resolved: false }),
  })

  const triggerScanMutation = useMutation({
    mutationFn: (range?: { start_ip: string; end_ip: string }) => {
      if (!selectedSubnet) return Promise.reject(new Error('No subnet selected'))
      return scanApi.trigger(selectedSubnet.id, range)
    },
    onSuccess: () => {
      setShowRangePicker(false)
      refetchScan()
      qc.invalidateQueries({ queryKey: ['addresses', selectedSubnet?.id] })
    },
  })

  const [resolveTarget, setResolveTarget] = useState<Collision | null>(null)
  const [confirmSubnet, setConfirmSubnet] = useState<Subnet | null>(null)
  const { showToast } = useToast()
  const { user } = useAuth()
  const isAdmin = user?.role === 'admin'

  const [treeView, setTreeView]           = useState(false)
  const [treeSelectedId, setTreeSelectedId] = useState<number | null>(null)

  const { data: settingsData } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })
  const warnAt     = settingsData?.util_warn_threshold     ?? 80
  const criticalAt = settingsData?.util_critical_threshold ?? 95

  const { data, isLoading, error } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  const [searchTerm, setSearchTerm] = useState('')
  const { sortKey, toggleSort, sortIcon, dir } = useTableSort<
    'name' | 'cidr' | 'ip_version' | 'vlan' | 'description' | 'utilization'
  >('cidr')

  const visibleSubnets = useMemo(() => {
    if (!data) return []
    const q = searchTerm.trim().toLowerCase()
    const filtered = q
      ? data.filter((s: Subnet) =>
          s.name.toLowerCase().includes(q) ||
          s.cidr.toLowerCase().includes(q) ||
          (s.description ?? '').toLowerCase().includes(q) ||
          (s.vlan_id != null && String(s.vlan_id).includes(q))
        )
      : data.slice()
    const cmp = (a: Subnet, b: Subnet) => {
      switch (sortKey) {
        case 'name':        return a.name.localeCompare(b.name) * dir
        case 'cidr':        return ipCompare(a.cidr.split('/')[0], b.cidr.split('/')[0]) * dir
        case 'ip_version':  return (a.ip_version - b.ip_version) * dir
        case 'vlan':        return ((a.vlan_id ?? Number.MAX_SAFE_INTEGER) - (b.vlan_id ?? Number.MAX_SAFE_INTEGER)) * dir
        case 'description': return (a.description ?? '').localeCompare(b.description ?? '') * dir
        case 'utilization': return (a.utilization_pct - b.utilization_pct) * dir
      }
    }
    return filtered.sort(cmp)
  }, [data, searchTerm, sortKey, dir])

  const createMutation = useMutation({
    mutationFn: () => subnetsApi.create({
      name:                  form.name,
      cidr:                  form.cidr,
      vlan_id:               form.vlan_id ? Number(form.vlan_id) : null,
      description:           form.description || null,
      ip_version:            4,
      notes:                 null,
      parent_id:             formParentId,
      scan_interval_minutes: form.scan_interval_minutes ? Number(form.scan_interval_minutes) : null,
      dns_provider_name:  form.dns_provider_name || null,
      dhcp_provider_name: form.dhcp_provider_name || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnets'] })
      setForm(emptyForm)
      setShowForm(false)
      setFormParentId(null)
      setParentCandidates([])
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => subnetsApi.update(selectedSubnet!.id, {
      name:                  editForm.name        || undefined,
      vlan_id:               editForm.vlan_id ? Number(editForm.vlan_id) : null,
      description:           editForm.description || null,
      notes:                 editForm.notes       || null,
      scan_interval_minutes: editForm.scan_interval_minutes ? Number(editForm.scan_interval_minutes) : null,
      dns_provider_name:  editForm.dns_provider_name || null,
      dhcp_provider_name: editForm.dhcp_provider_name || null,
      request_eligible:   editForm.request_eligible,
      ...(editParentId !== undefined ? { parent_id: editParentId } : {}),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subnets'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => subnetsApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnets'] })
      showToast('Subnet deleted', 'success')
      setConfirmSubnet(null)
    },
    onError: (err: any) => {
      showToast(err?.response?.data?.detail ?? 'Delete failed', 'error')
      setConfirmSubnet(null)
    },
  })

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(f => ({ ...f, [key]: e.target.value }))

  const setEdit = (key: keyof typeof emptyEditForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setEditForm(f => ({ ...f, [key]: e.target.value }))

  const openDrawer = (s: Subnet) => {
    setSelectedSubnet(s)
    setEditForm({
      name:                  s.name,
      vlan_id:               s.vlan_id != null ? String(s.vlan_id) : '',
      description:           s.description ?? '',
      notes:                 s.notes       ?? '',
      scan_interval_minutes: s.scan_interval_minutes ? String(s.scan_interval_minutes) : '',
      dns_provider_name:  s.dns_provider_name ?? '',
      dhcp_provider_name: s.dhcp_provider_name ?? '',
      request_eligible:   s.request_eligible ?? false,
    })
    setEditParentId(s.parent_id ?? null)
    setShowRangePicker(false)
    setRangeForm({ start_ip: '', end_ip: '' })
  }

  const collisionCountForSubnet = (subnet: Subnet): number => {
    if (!allUnresolvedCollisions) return 0
    return allUnresolvedCollisions.filter(c => ipInCidr(c.ip_address, subnet.cidr)).length
  }

  const subnetById = useMemo(() => {
    if (!data) return new Map<number, Subnet>()
    return new Map(data.map((s: Subnet) => [s.id, s]))
  }, [data])

  const prefixLen     = selectedSubnet ? parseInt(selectedSubnet.cidr.split('/')[1]) : 0
  const isLargeSubnet = prefixLen < 24

  const subnetViewExtra = selectedSubnet ? (
    <>
      <div style={{ marginBottom: '1rem', display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
        <span style={{ fontSize: '0.75rem', color: 'var(--text-muted)' }}>Utilization</span>
        <UtilBar
          pct={selectedSubnet.utilization_pct}
          warn={warnAt}
          critical={criticalAt}
        />
        <span style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
          {selectedSubnet.used_count} / {selectedSubnet.total_count} hosts
        </span>
      </div>
      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">IP Addresses</div>
        {!subnetAddresses ? (
          <p className="loading">Loading…</p>
        ) : subnetAddresses.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No addresses tracked in this subnet.
          </p>
        ) : (
          <div className="table-wrap" style={{ marginTop: '0.5rem' }}>
            <table>
              <thead>
                <tr>
                  <th>Address</th>
                  <th>Hostname</th>
                  <th>Status</th>
                </tr>
              </thead>
              <tbody>
                {subnetAddresses.map(a => (
                  <tr key={a.id}>
                    <td><span className="font-mono">{a.address}</span></td>
                    <td>{a.hostname ?? <span className="text-muted">—</span>}</td>
                    <td>
                      <span className={`badge ${
                        a.status === 'assigned'   ? 'badge-blue'   :
                        a.status === 'available'  ? 'badge-green'  :
                        a.status === 'reserved'   ? 'badge-yellow' :
                        a.status === 'discovered' ? 'badge-yellow' :
                        'badge-gray'
                      }`}>{a.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">DHCP Scope</div>
        {matchedScopes.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No matching DHCP scope found.
          </p>
        ) : matchedScopes.map(s => (
          <div key={`${s.source}:${s.scope_id}`} className="detail-fields" style={{ marginTop: '0.5rem' }}>
            <div className="detail-field">
              <span className="detail-field-label">Scope</span>
              <span className="detail-field-value font-mono">{s.scope_id}</span>
            </div>
            <div className="detail-field">
              <span className="detail-field-label">Name</span>
              <span className="detail-field-value">{s.name || <span className="text-muted">—</span>}</span>
            </div>
            <div className="detail-field">
              <span className="detail-field-label">Range</span>
              <span className="detail-field-value font-mono">
                {s.start_range} – {s.end_range}
              </span>
            </div>
            <div className="detail-field">
              <span className="detail-field-label">Status</span>
              <span className="detail-field-value">
                <span className={`badge ${s.active ? 'badge-green' : 'badge-gray'}`}>
                  {s.active ? 'Active' : 'Inactive'}
                </span>
              </span>
            </div>
            {s.description && (
              <div className="detail-field">
                <span className="detail-field-label">Description</span>
                <span className="detail-field-value">{s.description}</span>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Scan section */}
      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <span>Scan</span>
          {scanStatus?.scanned_at && (
            <span style={{ fontSize: '0.65rem', color: 'var(--text-muted)', fontWeight: 400 }}>
              Last scanned {Math.floor((Date.now() - new Date(scanStatus.scanned_at).getTime()) / 1000)}s ago
            </span>
          )}
        </div>

        {scanStatus?.status === 'running' ? (
          <p className="loading" style={{ fontSize: '0.8rem' }}>Scanning…</p>
        ) : (
          <button
            className="btn-ghost btn-sm"
            onClick={() => isLargeSubnet ? setShowRangePicker(true) : triggerScanMutation.mutate(undefined)}
            disabled={triggerScanMutation.isPending}
            style={{ fontSize: '0.75rem', marginBottom: '0.5rem' }}
          >
            <Scan size={12} /> {isLargeSubnet ? 'Scan Range…' : 'Scan Subnet'}
          </button>
        )}

        {showRangePicker && (
          <div style={{ background: 'var(--surface-2)', border: '1px solid var(--border)', borderRadius: '6px', padding: '0.75rem', marginBottom: '0.5rem' }}>
            <div style={{ fontSize: '0.75rem', color: 'var(--text-muted)', marginBottom: '0.5rem' }}>
              Subnet is larger than /24. Specify a range (max 1,024 hosts).
            </div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '0.5rem', marginBottom: '0.5rem' }}>
              <div className="form-field">
                <label>Start IP</label>
                <input placeholder="10.0.0.1" value={rangeForm.start_ip} onChange={e => setRangeForm(f => ({ ...f, start_ip: e.target.value }))} />
              </div>
              <div className="form-field">
                <label>End IP</label>
                <input placeholder="10.0.0.254" value={rangeForm.end_ip} onChange={e => setRangeForm(f => ({ ...f, end_ip: e.target.value }))} />
              </div>
            </div>
            <div className="form-actions">
              <button
                className="btn-primary btn-sm"
                onClick={() => triggerScanMutation.mutate({ start_ip: rangeForm.start_ip, end_ip: rangeForm.end_ip })}
                disabled={!rangeForm.start_ip || !rangeForm.end_ip || triggerScanMutation.isPending}
              >
                Start Scan
              </button>
              <button className="btn-ghost btn-sm" onClick={() => setShowRangePicker(false)}>
                Cancel
              </button>
            </div>
          </div>
        )}

        {scanStatus?.status === 'error' && (
          <p style={{ fontSize: '0.75rem', color: 'var(--danger)', margin: '0.25rem 0' }}>
            Error: {scanStatus.error}
          </p>
        )}

        {scanStatus?.results && scanStatus.results.length > 0 && (
          <div className="table-wrap" style={{ marginTop: '0.5rem' }}>
            <table>
              <thead>
                <tr><th>IP</th><th>Status</th><th>Latency</th></tr>
              </thead>
              <tbody>
                {scanStatus.results.filter(r => r.reachable).map(r => {
                  const inIpam = subnetAddresses?.some(a => a.address === r.ip)
                  return (
                    <tr key={r.ip}>
                      <td><span className="font-mono">{r.ip}</span></td>
                      <td>
                        {inIpam
                          ? <span className="badge badge-green">tracked</span>
                          : <span className="badge badge-yellow">discovered</span>
                        }
                      </td>
                      <td><span className="text-muted">{r.latency_ms != null ? `${r.latency_ms.toFixed(1)}ms` : '—'}</span></td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        {subnetCollisions && subnetCollisions.length > 0 && (
          <div style={{ marginTop: '0.75rem' }}>
            <div style={{ fontSize: '0.75rem', fontWeight: 600, color: 'var(--warning, #f59e0b)', marginBottom: '0.4rem', display: 'flex', alignItems: 'center', gap: '4px' }}>
              <AlertTriangle size={12} /> {subnetCollisions.length} collision{subnetCollisions.length > 1 ? 's' : ''}
            </div>
            {subnetCollisions.map((c: Collision) => (
              <div key={c.id} style={{ fontSize: '0.75rem', display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '0.25rem 0', borderBottom: '1px solid var(--border)' }}>
                <span>
                  <span className="font-mono">{c.ip_address}</span>{' '}
                  <span className="badge badge-yellow" style={{ fontSize: '0.55rem' }}>
                    {c.collision_type.replace(/_/g, ' ')}
                  </span>
                </span>
                <button
                  className="btn-ghost btn-sm"
                  style={{ fontSize: '0.65rem' }}
                  onClick={() => setResolveTarget(c)}
                >
                  Resolve
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Access grants section */}
      {isAdmin && (
        <div style={{ marginTop: '1rem' }}>
          <div className="detail-section-title">Access</div>
          <SubnetGrants subnetId={selectedSubnet.id} />
        </div>
      )}
    </>
  ) : null

  return (
    <div>
      <div className="page-header">
        <h1>Subnets</h1>
        <div className="page-header-actions">
          <button
            className={treeView ? 'btn-primary btn-sm' : 'btn-ghost btn-sm'}
            onClick={() => setTreeView(v => !v)}
            title={treeView ? 'Switch to flat table' : 'Switch to tree view'}
          >
            {treeView ? '☰ Flat' : <><GitBranch size={13} /> Tree</>}
          </button>
          <a
            className="btn-ghost btn-sm"
            href={importExportApi.exportSubnetsUrl()}
            download="subnets.csv"
            title="Export subnets to CSV"
          >
            <Download size={13} /> Export
          </a>
          <button
            className="btn-ghost btn-sm"
            onClick={() => importRef.current?.click()}
            disabled={importing}
            title="Import subnets from CSV"
          >
            <Upload size={13} /> {importing ? 'Importing…' : 'Import'}
          </button>
          <input
            ref={importRef}
            type="file"
            accept=".csv"
            style={{ display: 'none' }}
            onChange={async e => {
              const file = e.target.files?.[0]
              if (!file) return
              setImporting(true)
              setImportResult(null)
              try {
                const result = await importExportApi.importSubnets(file)
                setImportResult(result)
                qc.invalidateQueries({ queryKey: ['subnets'] })
              } catch {
                setImportResult({ created: 0, updated: 0, skipped: 0, errors: ['Upload failed'] })
              } finally {
                setImporting(false)
                e.target.value = ''
              }
            }}
          />
          {!showForm && (
            <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
              <Plus size={13} /> Add Subnet
            </button>
          )}
        </div>
      </div>

      {importResult && (
        <div className={`inline-form ${importResult.errors.length ? 'border-l-4 border-yellow-500' : 'border-l-4 border-green-500'}`} style={{ marginBottom: '1rem' }}>
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
            <div>
              <strong>Import complete:</strong> {importResult.created} created, {importResult.updated} updated, {importResult.skipped} skipped
              {importResult.errors.length > 0 && (
                <ul style={{ marginTop: '0.5rem', paddingLeft: '1rem', fontSize: '0.85em', color: 'var(--color-warn, #b45309)' }}>
                  {importResult.errors.map((e, i) => <li key={i}>{e}</li>)}
                </ul>
              )}
            </div>
            <button className="btn-ghost btn-sm" aria-label="Dismiss import result" onClick={() => setImportResult(null)}>
              <X size={13} />
            </button>
          </div>
        </div>
      )}

      {showForm && (
        <div className="inline-form">
          <div className="form-grid">
            <div className="form-field">
              <label>Name</label>
              <input placeholder="Server Network" value={form.name} onChange={set('name')} autoFocus />
            </div>
            <div className="form-field">
              <label>CIDR</label>
              <input placeholder="10.0.1.0/24" value={form.cidr} onChange={set('cidr')} />
            </div>
            <div className="form-field">
              <label>VLAN ID</label>
              <input type="number" placeholder="Optional" value={form.vlan_id} onChange={set('vlan_id')} />
            </div>
            <div className="form-field">
              <label>Description</label>
              <input placeholder="Optional" value={form.description} onChange={set('description')} />
            </div>
            <div className="form-field">
              <label>Scan interval (min)</label>
              <input
                type="number"
                min={1}
                placeholder={`global default (${settingsData?.scan_interval_minutes ?? 30})`}
                value={form.scan_interval_minutes}
                onChange={set('scan_interval_minutes')}
              />
            </div>
            <div className="form-field">
              <label>DNS Provider</label>
              <input placeholder="Optional provider name" value={form.dns_provider_name} onChange={set('dns_provider_name')} />
            </div>
            <div className="form-field">
              <label>DHCP Provider</label>
              <input placeholder="Optional provider name" value={form.dhcp_provider_name} onChange={set('dhcp_provider_name')} />
            </div>
            <div className="form-field" style={{ gridColumn: '1 / -1' }}>
              <label>Parent Subnet</label>
              <select
                value={formParentId ?? ''}
                onChange={e => setFormParentId(e.target.value ? Number(e.target.value) : null)}
              >
                <option value="">— None (root subnet) —</option>
                {parentCandidates.length === 0 && form.cidr ? (
                  <option disabled value="">No containing subnets found</option>
                ) : (
                  parentCandidates.map(s => (
                    <option key={s.id} value={s.id}>{s.name} — {s.cidr}</option>
                  ))
                )}
              </select>
            </div>
          </div>
          <div className="form-actions">
            <button
              className="btn-primary btn-sm"
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || !form.name || !form.cidr}
            >
              {createMutation.isPending ? 'Adding…' : 'Add'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => { setShowForm(false); setForm(emptyForm); setFormParentId(null); setParentCandidates([]) }}>
              <X size={13} /> Cancel
            </button>
            {createMutation.isError && (
              <span className="feedback-error">
                {String((createMutation.error as Error).message)}
              </span>
            )}
          </div>
        </div>
      )}

      {isLoading && <p className="loading">Loading…</p>}
      {error    && <p className="feedback-error">Failed to load subnets.</p>}

      {data && !treeView && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
            <SearchInput
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder="Search name, CIDR, VLAN…"
            />
          </div>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th className="th-sortable" onClick={() => toggleSort('name')}><span>Name {sortIcon('name')}</span></th>
                <th className="th-sortable" onClick={() => toggleSort('cidr')}><span>CIDR {sortIcon('cidr')}</span></th>
                <th className="th-sortable" onClick={() => toggleSort('ip_version')}><span>Version {sortIcon('ip_version')}</span></th>
                <th className="th-sortable" onClick={() => toggleSort('vlan')}><span>VLAN {sortIcon('vlan')}</span></th>
                <th className="th-sortable" onClick={() => toggleSort('description')}><span>Description {sortIcon('description')}</span></th>
                <th className="th-sortable" onClick={() => toggleSort('utilization')}><span>Utilization {sortIcon('utilization')}</span></th>
                <th style={{ width: '2.5rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {visibleSubnets.length === 0 && (
                <tr><td colSpan={7} className="empty-state">
                  {data.length === 0 ? 'No subnets defined. Add one above.' : 'No subnets match search.'}
                </td></tr>
              )}
              {visibleSubnets.map((s: Subnet) => {
                const collisionCount = collisionCountForSubnet(s)
                return (
                <tr key={s.id} className="clickable" {...rowActivation(() => openDrawer(s))}>
                  <td>
                    <span style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
                      {s.name}
                      {s.parent_id != null && (
                        <span style={{ fontSize: '0.62rem', color: 'var(--text-muted)', background: 'var(--surface-2)', padding: '0.05rem 0.3rem', borderRadius: '3px' }}>
                          ↳ {subnetById.get(s.parent_id)?.name ?? `#${s.parent_id}`}
                        </span>
                      )}
                      {collisionCount > 0 && (
                        <span style={{ fontSize: '0.65rem', fontWeight: 600, color: 'var(--warning, #f59e0b)', display: 'flex', alignItems: 'center', gap: '2px' }}>
                          <AlertTriangle size={10} /> {collisionCount}
                        </span>
                      )}
                    </span>
                  </td>
                  <td><span className="font-mono">{s.cidr}</span></td>
                  <td><span className="badge badge-blue">IPv{s.ip_version}</span></td>
                  <td>{s.vlan_id ?? <span className="text-muted">—</span>}</td>
                  <td>{s.description ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <UtilBar pct={s.utilization_pct} warn={warnAt} critical={criticalAt} />
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className="btn-danger btn-sm"
                      title={s.used_count > 0 ? 'Remove all addresses first' : 'Delete subnet'}
                      disabled={deleteMutation.isPending || s.used_count > 0}
                      onClick={() => setConfirmSubnet(s)}
                    >
                      <X size={12} />
                    </button>
                  </td>
                </tr>
              )})}
            </tbody>
          </table>
          </div>
        </>
      )}

      {data && treeView && (
        <SubnetTree
          subnets={data}
          warnAt={warnAt}
          criticalAt={criticalAt}
          selectedId={treeSelectedId}
          onSelect={s => {
            setTreeSelectedId(s.id)
            openDrawer(s)
          }}
        />
      )}

      {confirmSubnet && (
        <ConfirmModal
          title="Delete Subnet"
          message={`Delete subnet "${confirmSubnet.name}" (${confirmSubnet.cidr})?`}
          onConfirm={() => deleteMutation.mutate(confirmSubnet.id)}
          onCancel={() => setConfirmSubnet(null)}
        />
      )}

      {resolveTarget && (
        <CollisionResolveDialog
          collision={resolveTarget}
          queryKeys={[
            ['collisions', selectedSubnet?.id],
            ['collisions-all'],
          ]}
          onClose={() => setResolveTarget(null)}
        />
      )}

      {selectedSubnet && (
        <DetailDrawer
          title={selectedSubnet.name}
          subtitle={selectedSubnet.cidr}
          viewExtra={subnetViewExtra}
          fields={[
            { label: 'Name',        value: selectedSubnet.name },
            { label: 'CIDR',        value: <span className="font-mono">{selectedSubnet.cidr}</span> },
            { label: 'IP Version',  value: <span className="badge badge-blue">IPv{selectedSubnet.ip_version}</span> },
            { label: 'VLAN',        value: selectedSubnet.vlan_id ?? <span className="text-muted">—</span> },
            { label: 'Description', value: selectedSubnet.description ?? <span className="text-muted">—</span> },
            { label: 'Notes',       value: selectedSubnet.notes ?? <span className="text-muted">—</span> },
          ]}
          onSave={() => updateMutation.mutate()}
          isSaving={updateMutation.isPending}
          onClose={() => { setSelectedSubnet(null); setEditParentCandidates([]) }}
        >
          <div className="form-field">
            <label>Name</label>
            <input value={editForm.name} onChange={setEdit('name')} />
          </div>
          <div className="form-field">
            <label>VLAN ID</label>
            <input type="number" value={editForm.vlan_id} onChange={setEdit('vlan_id')} />
          </div>
          <div className="form-field">
            <label>Description</label>
            <input value={editForm.description} onChange={setEdit('description')} />
          </div>
          <div className="form-field">
            <label>Scan interval (min)</label>
            <input
              type="number"
              min={1}
              placeholder={`global default (${settingsData?.scan_interval_minutes ?? 30})`}
              value={editForm.scan_interval_minutes}
              onChange={setEdit('scan_interval_minutes')}
            />
          </div>
          <div className="form-field">
            <label>DNS Provider</label>
            <input value={editForm.dns_provider_name} onChange={setEdit('dns_provider_name')} />
          </div>
          <div className="form-field">
            <label>DHCP Provider</label>
            <input value={editForm.dhcp_provider_name} onChange={setEdit('dhcp_provider_name')} />
          </div>
          {isAdmin && (
            <div className="form-field" style={{ gridColumn: '1 / -1' }}>
              <label>
                <input
                  type="checkbox"
                  checked={editForm.request_eligible}
                  onChange={e => setEditForm(f => ({ ...f, request_eligible: e.target.checked }))}
                />
                {' '}Request-eligible
              </label>
            </div>
          )}
          <div className="form-field" style={{ gridColumn: '1 / -1' }}>
            <label>Parent Subnet</label>
            <select
              value={editParentId ?? ''}
              onChange={e => setEditParentId(e.target.value ? Number(e.target.value) : null)}
            >
              <option value="">— None (root subnet) —</option>
              {editParentCandidates.map(s => (
                <option key={s.id} value={s.id}>{s.name} — {s.cidr}</option>
              ))}
            </select>
          </div>
          <div className="form-field" style={{ gridColumn: '1 / -1' }}>
            <label>Notes</label>
            <textarea
              value={editForm.notes}
              onChange={setEdit('notes')}
              rows={4}
              style={{ resize: 'vertical', width: '100%' }}
            />
          </div>
        </DetailDrawer>
      )}
    </div>
  )
}
