import { useState, useRef, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X, Download, Upload, Server, ArrowUp, ArrowDown, ArrowUpDown } from 'lucide-react'
import { addressesApi, subnetsApi, dnsApi, dhcpApi, scanHistoryApi, importExportApi, customFieldsApi, discoveryApi, type IPAddress, type ImportResult, type DeletePreview } from '../api/client'
import { formatRelative } from '../utils/time'
import { isValidIPv4, isValidIPv6, isValidEUI48 } from '../utils/ip'
import DetailDrawer from '../components/DetailDrawer'
import EmptyState from '../components/EmptyState'
import CustomFieldsEditor, { parseTags } from '../components/CustomFieldsEditor'
import SearchInput from '../components/SearchInput'
import { TableSkeleton } from '../components/Skeleton'
import ModalDialog from '../components/ModalDialog'
import { usePagedQuery } from '../hooks/usePagedQuery'
import { Pager } from '../components/Pager'
import { useToast } from '../contexts/ToastContext'
import { rowActivation } from '../utils/a11y'
import { apiError } from '../utils/apiError'

const STATUS_BADGE: Record<string, string> = {
  available:  'badge-green',
  assigned:   'badge-blue',
  reserved:   'badge-yellow',
  deprecated: 'badge-gray',
}

const STATUSES = ['available', 'assigned', 'reserved', 'deprecated'] as const

const emptyForm = {
  address: '', subnet_id: '', hostname: '', status: 'assigned' as string,
  mac_address: '', description: '',
}

const emptyEditForm = {
  hostname: '', status: 'assigned', mac_address: '', description: '', notes: '',
}

export default function Addresses() {
  const [showForm, setShowForm]               = useState(false)
  const [form, setForm]                       = useState(emptyForm)
  const [filterStatus, setFilter]             = useState('')
  const [filterSubnet, setFilterSubnet]       = useState<number | ''>('')
  const [selectedAddress, setSelectedAddress] = useState<IPAddress | null>(null)
  const [editForm, setEditForm]               = useState(emptyEditForm)
  const [cfValues, setCfValues]               = useState<Record<string, string>>({})
  const [tagsText, setTagsText]               = useState('')
  const { data: fieldDefs } = useQuery({
    queryKey: ['custom-fields', 'address'],
    queryFn: () => customFieldsApi.list('address'),
  })
  const qc = useQueryClient()
  const { showToast } = useToast()
  const [deletingId, setDeletingId]         = useState<number | null>(null)
  const [deletePreview, setDeletePreview]   = useState<DeletePreview | null>(null)
  const [previewLoading, setPreviewLoading] = useState(false)
  const [checkedKeys, setCheckedKeys]       = useState<Set<string>>(new Set())
  const [importResult, setImportResult] = useState<ImportResult | null>(null)
  const importRef = useRef<HTMLInputElement>(null)
  const [importing, setImporting] = useState(false)
  const [ipError, setIpError]   = useState('')
  const [macError, setMacError] = useState('')

  const { data: ipDnsRecords } = useQuery({
    queryKey: ['dns-by-ip', selectedAddress?.address],
    queryFn: () => dnsApi.byIp(selectedAddress!.address),
    enabled: !!selectedAddress,
    retry: false,
  })

  const { data: ipDhcpLeases } = useQuery({
    queryKey: ['dhcp-by-ip', selectedAddress?.address],
    queryFn: () => dhcpApi.byIp(selectedAddress!.address),
    enabled: !!selectedAddress,
    retry: false,
  })

  const { data: discoveryEndpoints } = useQuery({
    queryKey: ['discovery-by-address', selectedAddress?.id],
    queryFn: () => discoveryApi.addressDiscovery(selectedAddress!.id),
    enabled: !!selectedAddress,
    retry: false,
  })

  const [asOf, setAsOf] = useState('')
  const { data: history } = useQuery({
    queryKey: ['addr-history', selectedAddress?.id, asOf],
    queryFn: () => selectedAddress!.address && asOf
      ? addressesApi.historyByIp(selectedAddress!.address, asOf)
      : addressesApi.history(selectedAddress!.id),
    enabled: !!selectedAddress,
    retry: false,
  })

  const { data: scanHistory } = useQuery({
    queryKey: ['scan-history', selectedAddress?.id],
    queryFn: () => scanHistoryApi.list(selectedAddress!.id),
    enabled: !!selectedAddress,
    retry: false,
  })

  const {
    items: visibleAddresses,
    total,
    page,
    setPage,
    sort: sortKey,
    dir: sortDirRaw,
    setSort: toggleSort,
    q: searchTerm,
    setQuery: setSearchTerm,
    pageSize,
    setPageSize,
    isFetching,
    isLoading,
    error,
  } = usePagedQuery({
    queryKey: ['addresses'],
    queryFn: (params) => addressesApi.list(params),
    filters: {
      subnet_id: filterSubnet !== '' ? filterSubnet : undefined,
      status: filterStatus !== '' ? filterStatus : undefined,
    } as { subnet_id?: number; status?: string },
    defaultSort: 'address',
    defaultDir: 'asc',
  })

  useEffect(() => { setPage(1) }, [filterStatus, filterSubnet])

  const sortIcon = (key: string) => {
    if (sortKey !== key) return <ArrowUpDown size={11} className="sort-icon-idle" />
    return sortDirRaw === 'asc' ? <ArrowUp size={11} /> : <ArrowDown size={11} />
  }

  const { data: subnets } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => addressesApi.create({
      address:     form.address,
      subnet_id:   Number(form.subnet_id),
      hostname:    form.hostname || null,
      status:      form.status as IPAddress['status'],
      mac_address: form.mac_address || null,
      description: form.description || null,
      notes:       null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['addresses'] })
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const updateMutation = useMutation({
    mutationFn: () => addressesApi.update(selectedAddress!.id, {
      hostname:    editForm.hostname    || null,
      status:      editForm.status      as IPAddress['status'],
      mac_address: editForm.mac_address || null,
      description: editForm.description || null,
      notes:       editForm.notes       || null,
      custom_fields: cfValues,
      tags:          parseTags(tagsText),
    }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['addresses'] }),
  })

  const deleteWithCleanupMutation = useMutation({
    mutationFn: ({ id, keys }: { id: number; keys: string[] }) =>
      addressesApi.deleteWithCleanup(id, keys),
    onSuccess: (_, { keys }) => {
      qc.invalidateQueries({ queryKey: ['addresses'] })
      qc.invalidateQueries({ queryKey: ['stale-count'] })
      showToast(
        keys.length
          ? `Address deleted (${keys.length} provider record${keys.length > 1 ? 's' : ''} cleaned up)`
          : 'Address deleted',
        'success',
      )
      setDeletingId(null)
      setDeletePreview(null)
    },
    onError: (err: any) => {
      const e = apiError(err, 'Delete failed')
      showToast(e.message, 'error', { hint: e.hint, detail: e.detail })
      setDeletingId(null)
      setDeletePreview(null)
    },
  })

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: e.target.value }))

  const setEdit = (key: keyof typeof emptyEditForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement | HTMLTextAreaElement>) =>
      setEditForm(f => ({ ...f, [key]: e.target.value }))

  const openDrawer = (a: IPAddress) => {
    setSelectedAddress(a)
    setEditForm({
      hostname:    a.hostname    ?? '',
      status:      a.status,
      mac_address: a.mac_address ?? '',
      description: a.description ?? '',
      notes:       a.notes       ?? '',
    })
    setCfValues(a.custom_fields ?? {})
    setTagsText((a.tags ?? []).join(', '))
  }


  const SOURCE_LABEL: Record<string, string> = {
    msdhcp: 'MS DHCP', pihole: 'Pi-hole', keadhcp: 'Kea',
    msdns: 'MS DNS', bind: 'BIND',
  }

  const addressViewExtra = selectedAddress ? (
    <>
      {discoveryEndpoints && discoveryEndpoints.length > 0 && (
        <div style={{ marginBottom: '1rem' }}>
          <div className="detail-section-title">Network location</div>
          {discoveryEndpoints.map(e => (
            <div key={e.id} style={{ fontSize: '0.8rem', padding: '0.2rem 0' }}>
              <span className="font-mono">{e.port_name ?? `if${e.ifindex ?? '?'}`}</span>
              {e.vlan != null && <span className="badge badge-blue" style={{ marginLeft: '0.4rem' }}>VLAN {e.vlan}</span>}
              <span style={{ color: 'var(--text-muted)', marginLeft: '0.4rem' }}>
                on {e.source}{e.mac ? ` · ${e.mac}` : ''}
              </span>
            </div>
          ))}
        </div>
      )}
      {history && (
        <div style={{ marginBottom: '1rem' }}>
          <div className="detail-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>History</span>
            <input type="date" value={asOf} onChange={e => setAsOf(e.target.value)}
              title="Reconstruct state as of this date"
              style={{ fontSize: '0.7rem', padding: '0.1rem 0.3rem' }} />
          </div>
          {asOf && history.point_in_time && (
            <div style={{ fontSize: '0.78rem', padding: '0.4rem', background: 'var(--surface-2)', borderRadius: 4, margin: '0.4rem 0' }}>
              As of {asOf}: <strong>{String((history.point_in_time as any).state)}</strong>
              {(history.point_in_time as any).hostname && ` · ${(history.point_in_time as any).hostname}`}
              {(history.point_in_time as any).status && ` · ${(history.point_in_time as any).status}`}
            </div>
          )}
          {asOf && history.point_in_time === null && (
            <div style={{ fontSize: '0.78rem', color: 'var(--text-muted)', margin: '0.4rem 0' }}>No record as of {asOf}.</div>
          )}
          {history.timeline.length === 0 ? (
            <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.4rem 0' }}>No history.</p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.3rem', marginTop: '0.4rem' }}>
              {history.timeline.slice(0, 50).map((e, i) => (
                <div key={i} style={{ fontSize: '0.76rem', display: 'flex', gap: '0.5rem' }}>
                  <span style={{ color: 'var(--text-muted)', minWidth: 130 }}>{e.ts ? new Date(e.ts).toLocaleString() : ''}</span>
                  <span>
                    {e.kind === 'change' && <><span className="badge badge-blue">{e.action}</span> {e.user && <span style={{ color: 'var(--text-muted)' }}>by {e.user}</span>}</>}
                    {e.kind === 'drift' && <><span className="badge badge-yellow">drift</span> {e.category}</>}
                    {e.kind === 'reachability' && <><span className={`badge ${e.event_type === 'came_back' ? 'badge-green' : 'badge-red'}`}>{e.event_type}</span></>}
                  </span>
                </div>
              ))}
            </div>
          )}
        </div>
      )}
      {scanHistory && scanHistory.length > 0 && (() => {
        const last30 = scanHistory.slice(0, 30)
        const totalUp = last30.reduce((s, r) => s + r.up_count, 0)
        const totalScans = last30.reduce((s, r) => s + r.total_count, 0)
        const uptime30 = totalScans > 0 ? Math.round(totalUp / totalScans * 100) : 0
        const avgLatency = (() => {
          const rows = last30.filter(r => r.avg_latency_ms !== null && r.up_count > 0)
          if (!rows.length) return null
          return Math.round(rows.reduce((s, r) => s + r.avg_latency_ms! * r.up_count, 0) /
                            rows.reduce((s, r) => s + r.up_count, 0) * 10) / 10
        })()
        const uptimeColor = uptime30 >= 90 ? 'var(--success, #4ade80)'
          : uptime30 >= 50 ? 'var(--warning, #facc15)'
          : 'var(--danger, #f87171)'

        // Build last-7-days dot array (newest last = rightmost)
        const today = new Date()
        const days7 = Array.from({ length: 7 }, (_, i) => {
          const d = new Date(today)
          d.setDate(d.getDate() - (6 - i))
          const iso = d.toISOString().slice(0, 10)
          const DAY_LABELS = ['S','M','T','W','T','F','S']
          const label = DAY_LABELS[d.getDay()]
          const row = last30.find(r => r.date === iso)
          const color = !row ? '#555'
            : row.uptime_pct >= 90 ? 'var(--success, #4ade80)'
            : row.uptime_pct >= 50 ? 'var(--warning, #facc15)'
            : 'var(--danger, #f87171)'
          return { label, color }
        })

        return (
          <div style={{ marginTop: '1rem' }}>
            <div className="detail-section-title">Reachability</div>
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr 1fr', gap: '0.4rem', margin: '0.5rem 0' }}>
              <div style={{ background: 'var(--surface-2, #1e1e2e)', border: '1px solid var(--border)', borderRadius: '4px', padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                <div style={{ fontSize: '0.95rem', fontWeight: 700, color: uptimeColor }}>{uptime30}%</div>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>30d uptime</div>
              </div>
              <div style={{ background: 'var(--surface-2, #1e1e2e)', border: '1px solid var(--border)', borderRadius: '4px', padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                <div style={{ fontSize: '0.95rem', fontWeight: 700 }}>{avgLatency !== null ? `${avgLatency} ms` : '—'}</div>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>avg latency</div>
              </div>
              <div style={{ background: 'var(--surface-2, #1e1e2e)', border: '1px solid var(--border)', borderRadius: '4px', padding: '0.4rem 0.5rem', textAlign: 'center' }}>
                <div style={{ fontSize: '0.85rem', fontWeight: 700 }}>{formatRelative(selectedAddress.last_seen)}</div>
                <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '0.1rem' }}>last seen</div>
              </div>
            </div>
            <div style={{ display: 'flex', gap: '3px', marginTop: '0.4rem' }}>
              {days7.map((d, i) => (
                <div key={i} style={{ flex: 1, display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '2px' }}>
                  <div style={{ width: '100%', height: '16px', borderRadius: '2px', background: d.color }} />
                  <span style={{ fontSize: '0.55rem', color: 'var(--text-muted)' }}>{d.label}</span>
                </div>
              ))}
            </div>
          </div>
        )
      })()}

      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">DNS Records</div>
        {!ipDnsRecords ? (
          <p className="loading">Loading…</p>
        ) : ipDnsRecords.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No DNS records found for this IP.
          </p>
        ) : (
          <div className="detail-fields" style={{ marginTop: '0.5rem' }}>
            {ipDnsRecords.map((r, i) => (
              <div key={i} className="detail-field">
                <span className="detail-field-label">
                  <span className="badge badge-gray" style={{ fontSize: '0.6rem', marginRight: '0.3rem' }}>
                    {r.record_type}
                  </span>
                  {r.zone}
                </span>
                <span className="detail-field-value font-mono">{r.name}</span>
              </div>
            ))}
          </div>
        )}
      </div>

      <div style={{ marginTop: '1rem' }}>
        <div className="detail-section-title">DHCP</div>
        {!ipDhcpLeases ? (
          <p className="loading">Loading…</p>
        ) : ipDhcpLeases.length === 0 ? (
          <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
            No DHCP reservation found for this IP.
          </p>
        ) : (
          <div className="detail-fields" style={{ marginTop: '0.5rem' }}>
            {ipDhcpLeases.map((l, i) => (
              <div key={i} style={{ marginBottom: i < ipDhcpLeases.length - 1 ? '0.75rem' : 0 }}>
                <div className="detail-field">
                  <span className="detail-field-label">Scope</span>
                  <span className="detail-field-value font-mono">{l.scope_id}</span>
                </div>
                {l.mac_address && (
                  <div className="detail-field">
                    <span className="detail-field-label">MAC</span>
                    <span className="detail-field-value font-mono">{l.mac_address}</span>
                  </div>
                )}
                {l.client_duid && (
                  <div className="detail-field">
                    <span className="detail-field-label">DUID</span>
                    <span className="detail-field-value font-mono">{l.client_duid}</span>
                  </div>
                )}
                {l.name && (
                  <div className="detail-field">
                    <span className="detail-field-label">Name</span>
                    <span className="detail-field-value">{l.name}</span>
                  </div>
                )}
                <div className="detail-field">
                  <span className="detail-field-label">Source</span>
                  <span className="detail-field-value">
                    <span className="badge badge-gray" style={{ fontSize: '0.65rem' }}>
                      {SOURCE_LABEL[l.source ?? ''] ?? l.source ?? l.scope_id}
                    </span>
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </>
  ) : null

  return (
    <div>
      <div className="page-header">
        <h1>IP Addresses</h1>
        <div className="page-header-actions">
          <select
            value={filterStatus}
            onChange={e => setFilter(e.target.value)}
            style={{ fontSize: '0.8rem' }}
          >
            <option value="">All statuses</option>
            {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
          </select>
          <select
            value={filterSubnet}
            onChange={e => setFilterSubnet(e.target.value === '' ? '' : Number(e.target.value))}
            style={{ fontSize: '0.8rem' }}
          >
            <option value="">All subnets</option>
            {(subnets ?? []).map(s => (
              <option key={s.id} value={s.id}>{s.name} ({s.cidr})</option>
            ))}
          </select>
          <a
            className="btn-ghost btn-sm"
            href={importExportApi.exportAddressesUrl()}
            download="addresses.csv"
            title="Export addresses to CSV"
          >
            <Download size={13} /> Export
          </a>
          <button
            className="btn-ghost btn-sm"
            onClick={() => importRef.current?.click()}
            disabled={importing}
            title="Import addresses from CSV"
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
                const result = await importExportApi.importAddresses(file)
                setImportResult(result)
                qc.invalidateQueries({ queryKey: ['addresses'] })
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
              <Plus size={13} /> Add Address
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
            <div className={`form-field${ipError ? ' form-field-error' : ''}`}>
              <label htmlFor="addr-new-ip">IP Address</label>
              <input
                id="addr-new-ip"
                placeholder="10.0.1.50"
                value={form.address}
                autoFocus
                onChange={e => { setForm(f => ({ ...f, address: e.target.value })); if (ipError) setIpError('') }}
                onBlur={() => setIpError(form.address && !isValidIPv4(form.address) && !isValidIPv6(form.address) ? 'Invalid IP address' : '')}
              />
              {ipError && <span className="form-field-error-msg">{ipError}</span>}
            </div>
            <div className="form-field">
              <label htmlFor="addr-new-subnet">Subnet</label>
              <select id="addr-new-subnet" value={form.subnet_id} onChange={set('subnet_id')}>
                <option value="">— select —</option>
                {(subnets ?? []).map(s => (
                  <option key={s.id} value={s.id}>{s.name} ({s.cidr})</option>
                ))}
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="addr-new-status">Status</label>
              <select id="addr-new-status" value={form.status} onChange={set('status')}>
                {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="addr-new-hostname">Hostname</label>
              <input id="addr-new-hostname" placeholder="Optional" value={form.hostname} onChange={set('hostname')} />
            </div>
            <div className={`form-field${macError ? ' form-field-error' : ''}`}>
              <label htmlFor="addr-new-mac">MAC Address</label>
              <input
                id="addr-new-mac"
                placeholder="Optional — aa:bb:cc:dd:ee:ff"
                value={form.mac_address}
                onChange={e => { setForm(f => ({ ...f, mac_address: e.target.value })); if (macError) setMacError('') }}
                onBlur={() => setMacError(form.mac_address && !isValidEUI48(form.mac_address) ? 'Invalid MAC — expected e.g. aa:bb:cc:dd:ee:ff' : '')}
              />
              {macError && <span className="form-field-error-msg">{macError}</span>}
            </div>
            <div className="form-field">
              <label htmlFor="addr-new-desc">Description</label>
              <input id="addr-new-desc" placeholder="Optional" value={form.description} onChange={set('description')} />
            </div>
          </div>
          <div className="form-actions">
            <button
              className="btn-primary btn-sm"
              onClick={() => createMutation.mutate()}
              disabled={
                createMutation.isPending || !form.address || !form.subnet_id ||
                (!isValidIPv4(form.address) && !isValidIPv6(form.address)) ||
                (!!form.mac_address && !isValidEUI48(form.mac_address))
              }
            >
              {createMutation.isPending ? 'Adding…' : 'Add'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => { setShowForm(false); setForm(emptyForm) }}>
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

      {isLoading && <TableSkeleton cols={7} />}
      {!!error   && <p className="feedback-error">Failed to load addresses.</p>}

      {!isLoading && (
        <>
          <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
            <SearchInput
              value={searchTerm}
              onChange={setSearchTerm}
              placeholder="Search IP, hostname, MAC…"
            />
          </div>
          <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('address')}><span>Address {sortIcon('address')}</span></th>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('hostname')}><span>Hostname {sortIcon('hostname')}</span></th>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('status')}><span>Status {sortIcon('status')}</span></th>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('mac_address')}><span>MAC {sortIcon('mac_address')}</span></th>
                <th scope="col"><span>Description</span></th>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('last_seen')}><span>Last Seen {sortIcon('last_seen')}</span></th>
                <th scope="col" style={{ width: '2.5rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {visibleAddresses.length === 0 && (
                <tr><td colSpan={7}>
                  {total === 0 && !searchTerm && !filterStatus && !filterSubnet ? (
                    <EmptyState
                      icon={Server}
                      title="No addresses tracked"
                      description="Add an address manually or run a subnet scan to discover hosts."
                      action={!showForm && (
                        <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
                          <Plus size={13} /> Add Address
                        </button>
                      )}
                    />
                  ) : (
                    <EmptyState
                      icon={Server}
                      title="No addresses match filters"
                      description="Try a different term or clear the search."
                      action={<button className="btn-ghost btn-sm" onClick={() => setSearchTerm('')}>Clear search</button>}
                    />
                  )}
                </td></tr>
              )}
              {visibleAddresses.map((a: IPAddress) => (
                <tr key={a.id} className={`clickable${selectedAddress?.id === a.id ? ' row-selected' : ''}`} {...rowActivation(() => openDrawer(a))}>
                  <td><span className="font-mono">{a.address}</span></td>
                  <td>{a.hostname ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <span className={`badge ${STATUS_BADGE[a.status] ?? 'badge-gray'}`}>
                      {a.status}
                    </span>
                  </td>
                  <td><span className="font-mono">{a.mac_address ?? <span className="text-muted">—</span>}</span></td>
                  <td>{a.description ?? <span className="text-muted">—</span>}</td>
                  <td style={{ fontSize: '0.78rem', color: 'var(--text-muted)' }}>
                    {formatRelative(a.last_seen)}
                  </td>
                  <td onClick={e => e.stopPropagation()}>
                    <button
                      className="btn-danger btn-sm"
                      disabled={previewLoading && deletingId === a.id}
                      onClick={async () => {
                        setPreviewLoading(true)
                        setDeletingId(a.id)
                        try {
                          const preview = await addressesApi.deletePreview(a.id)
                          setDeletePreview(preview)
                          setCheckedKeys(new Set(preview.items.map(i => i.key)))
                        } catch {
                          showToast('Failed to load delete preview', 'error')
                          setDeletingId(null)
                        } finally {
                          setPreviewLoading(false)
                        }
                      }}
                    >
                      {previewLoading && deletingId === a.id ? '…' : <X size={12} />}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          </div>
          <Pager
            page={page}
            total={total}
            pageSize={pageSize}
            isFetching={isFetching}
            onPage={setPage}
            onPageSize={setPageSize}
          />
        </>
      )}

      {deletePreview && deletingId !== null && (
        <ModalDialog
          title={`Delete ${deletePreview.address}${deletePreview.hostname ? ` (${deletePreview.hostname})` : ''}?`}
          onClose={() => { setDeletingId(null); setDeletePreview(null) }}
        >
          <>
            {deletePreview.items.length > 0 ? (
              <>
                <p className="modal-section-title">Provider cleanup</p>
                <div className="modal-checklist">
                  {deletePreview.items.map(item => (
                    <label key={item.key} className="modal-checklist-item">
                      <input
                        type="checkbox"
                        checked={checkedKeys.has(item.key)}
                        onChange={() => setCheckedKeys(prev => {
                          const next = new Set(prev)
                          next.has(item.key) ? next.delete(item.key) : next.add(item.key)
                          return next
                        })}
                      />
                      {item.type === 'dns'
                        ? `DNS ${item.record_type} "${item.name}" → ${item.value} [${item.provider}]`
                        : `DHCP reservation ${item.ip_address} (${item.mac_address}) [${item.provider}]`}
                    </label>
                  ))}
                </div>
              </>
            ) : (
              <p className="modal-empty-note">
                No provider records found — address will be removed from IPAM only.
              </p>
            )}
            <div className="modal-actions">
              <button className="btn btn-ghost"
                      onClick={() => { setDeletingId(null); setDeletePreview(null) }}>
                Cancel
              </button>
              <button
                className="btn btn-danger"
                disabled={deleteWithCleanupMutation.isPending}
                onClick={() => deleteWithCleanupMutation.mutate({
                  id: deletingId,
                  keys: [...checkedKeys],
                })}
              >
                {deleteWithCleanupMutation.isPending ? 'Deleting…' : 'Delete'}
              </button>
            </div>
          </>
        </ModalDialog>
      )}

      {selectedAddress && (
        <DetailDrawer
          title={selectedAddress.address}
          subtitle={selectedAddress.hostname ?? undefined}
          viewExtra={addressViewExtra}
          fields={[
            { label: 'Address',     value: <span className="font-mono">{selectedAddress.address}</span> },
            { label: 'Status',      value: <span className={`badge ${STATUS_BADGE[selectedAddress.status]}`}>{selectedAddress.status}</span> },
            { label: 'MAC',         value: selectedAddress.mac_address ? <span className="font-mono">{selectedAddress.mac_address}</span> : <span className="text-muted">—</span> },
            { label: 'Description', value: selectedAddress.description ?? <span className="text-muted">—</span> },
            { label: 'Notes',       value: selectedAddress.notes ?? <span className="text-muted">—</span> },
          ]}
          onSave={() => updateMutation.mutate()}
          isSaving={updateMutation.isPending}
          onClose={() => setSelectedAddress(null)}
        >
          <div className="form-field">
            <label htmlFor="addr-edit-hostname">Hostname</label>
            <input id="addr-edit-hostname" value={editForm.hostname} onChange={setEdit('hostname')} />
          </div>
          <div className="form-field">
            <label htmlFor="addr-edit-status">Status</label>
            <select id="addr-edit-status" value={editForm.status} onChange={setEdit('status')}>
              {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
            </select>
          </div>
          <div className="form-field">
            <label htmlFor="addr-edit-mac">MAC Address</label>
            <input id="addr-edit-mac" value={editForm.mac_address} onChange={setEdit('mac_address')} />
          </div>
          <div className="form-field">
            <label htmlFor="addr-edit-desc">Description</label>
            <input id="addr-edit-desc" value={editForm.description} onChange={setEdit('description')} />
          </div>
          <div className="form-field" style={{ gridColumn: '1 / -1' }}>
            <label htmlFor="addr-edit-notes">Notes</label>
            <textarea
              id="addr-edit-notes"
              value={editForm.notes}
              onChange={setEdit('notes')}
              rows={4}
              style={{ resize: 'vertical', width: '100%' }}
            />
          </div>
          <CustomFieldsEditor
            defs={fieldDefs ?? []}
            values={cfValues}
            tagsText={tagsText}
            onValueChange={(name, value) => setCfValues(v => ({ ...v, [name]: value }))}
            onTagsChange={setTagsText}
          />
        </DetailDrawer>
      )}
    </div>
  )
}
