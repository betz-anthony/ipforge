import { useState, useMemo, useEffect } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SlidersHorizontal, Plus, X, Trash2 } from 'lucide-react'
import { dnsApi, providersApi, addressesApi, subnetsApi, type DNSRecord, type DNSZone } from '../api/client'
import { ipInCidr } from '../utils/ip'
import SyncBar from '../components/SyncBar'
import DetailPanel from '../components/DetailPanel'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../contexts/ToastContext'
import { rowActivation } from '../utils/a11y'

const RECORD_TYPES = ['A', 'AAAA', 'CNAME', 'PTR', 'MX', 'TXT', 'NS']

const TYPE_BADGE: Record<string, string> = {
  A:     'badge-green',
  AAAA:  'badge-blue',
  CNAME: 'badge-yellow',
  PTR:   'badge-gray',
  MX:    'badge-red',
  TXT:   'badge-gray',
  NS:    'badge-gray',
}

const SOURCE_LABEL: Record<string, string> = {
  msdns: 'MS DNS', pihole: 'Pi-hole', bind: 'BIND',
}

const PINGABLE = new Set(['A', 'AAAA', 'CNAME', 'PTR'])

type ZoneType = 'forward' | 'reverse' | 'trust'

const ZONE_GROUPS: { key: ZoneType; label: string }[] = [
  { key: 'forward', label: 'Forward Lookup Zones' },
  { key: 'reverse', label: 'Reverse Lookup Zones' },
  { key: 'trust',   label: 'Trust Points' },
]

function classifyZone(zone: string): ZoneType {
  if (zone === 'TrustAnchors') return 'trust'
  if (zone.endsWith('.in-addr.arpa') || zone.endsWith('.ip6.arpa')) return 'reverse'
  return 'forward'
}

// Render a reverse-DNS zone name as its network CIDR (e.g.
// "2.1.10.in-addr.arpa" -> "10.1.2.0/24"). Returns null for forward zones.
function reverseZoneToCidr(zone: string): string | null {
  if (zone.endsWith('.in-addr.arpa')) {
    const labels = zone.slice(0, -'.in-addr.arpa'.length).split('.')
    if (labels.length === 0 || labels.length > 4) return null
    const octets = [...labels].reverse().map(Number)
    if (octets.some(o => !Number.isInteger(o) || o < 0 || o > 255)) return null
    const prefix = octets.length * 8
    while (octets.length < 4) octets.push(0)
    return `${octets.join('.')}/${prefix}`
  }
  if (zone.endsWith('.ip6.arpa')) {
    const labels = zone.slice(0, -'.ip6.arpa'.length).split('.')
    if (labels.length === 0 || labels.length > 32 || labels.some(l => !/^[0-9a-fA-F]$/.test(l))) return null
    const nibbles = [...labels].reverse()
    const prefix = nibbles.length * 4
    while (nibbles.length < 32) nibbles.push('0')
    const hextets: string[] = []
    for (let i = 0; i < 32; i += 4) {
      hextets.push(nibbles.slice(i, i + 4).join('').replace(/^0+/, '') || '0')
    }
    const sig = Math.max(1, Math.ceil(prefix / 16))
    const head = hextets.slice(0, sig).join(':')
    return sig < 8 ? `${head}::/${prefix}` : `${head}/${prefix}`
  }
  return null
}

type SortCol = 'name' | 'record_type' | 'value' | 'ttl'
type SortDir = 'asc' | 'desc'
type ViewMode = 'combined' | 'by-server'

const emptyForm = { name: '', record_type: 'A', value: '', ttl: 3600, source: '' }

function SortArrow({ col, sortCol, sortDir }: { col: SortCol; sortCol: SortCol | null; sortDir: SortDir }) {
  const active = col === sortCol
  return (
    <span className="sort-arrow">
      {active ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
    </span>
  )
}

function PtrCheckbox({ label, checked, onChange, disabled = false, disabledNote }: {
  label: string
  checked: boolean
  onChange: (value: boolean) => void
  disabled?: boolean
  disabledNote?: string
}) {
  return (
    <label className={'checkbox-label' + (disabled ? ' disabled' : '')}>
      <input
        type="checkbox"
        checked={checked}
        onChange={e => onChange(e.target.checked)}
        disabled={disabled}
      />
      <span>
        {label}
        {disabled && disabledNote && (
          <span className="text-muted checkbox-note">{disabledNote}</span>
        )}
      </span>
    </label>
  )
}

export default function DNS() {
  const [selectedZone, setSelectedZone]         = useState<string | null>(null)
  const [selectedZoneSource, setSelectedZoneSource] = useState<string | null>(null)
  const [filter, setFilter]                 = useState('')
  const [typeFilter, setTypeFilter]         = useState<string>('')
  const [sortCol, setSortCol]               = useState<SortCol | null>(null)
  const [sortDir, setSortDir]               = useState<SortDir>('asc')
  const [showForm, setShowForm]             = useState(false)
  const [form, setForm]                     = useState(emptyForm)
  const [viewMode, setViewMode]             = useState<ViewMode>('combined')
  const [selectedRecord, setSelectedRecord] = useState<DNSRecord | null>(null)
  const [expandedGroups, setExpandedGroups] = useState<Set<string>>(new Set())
  const [zoneSearch, setZoneSearch]       = useState('')
  const [confirmRecord, setConfirmRecord] = useState<DNSRecord | null>(null)
  const [registerPtr, setRegisterPtr]   = useState(false)
  const [deletePtr, setDeletePtr]       = useState(true)
  const { showToast } = useToast()
  const [editingNotes, setEditingNotes]           = useState(false)
  const [notesValue, setNotesValue]               = useState('')
  const [selectedAddSubnetId, setSelectedAddSubnetId] = useState<number | null>(null)
  const qc = useQueryClient()

  const { data: zones, isLoading: loadingZones } = useQuery({
    queryKey: ['dns-zones'],
    queryFn: dnsApi.listZones,
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: providersApi.get,
  })

  const dnsProviders = providers?.dns ?? []

  const selectedZoneIsPihole = selectedZoneSource === 'pihole'

  const { data: records, isLoading: loadingRecords } = useQuery({
    queryKey: ['dns-records', selectedZone],
    queryFn: () => dnsApi.listRecords(selectedZone!),
    enabled: !!selectedZone,
  })

  const createMutation = useMutation({
    mutationFn: () => dnsApi.createRecord(selectedZone!, {
      ...form,
      ...(form.record_type === 'A' && registerPtr ? { register_ptr: true } : {}),
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dns-records', selectedZone] })
      setForm(f => ({ ...emptyForm, source: f.source }))
      setRegisterPtr(false)
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (record: DNSRecord) =>
      dnsApi.deleteRecord(
        selectedZone!,
        record,
        record.record_type === 'A' ? { delete_ptr: deletePtr } : undefined,
      ),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dns-records', selectedZone] })
      setConfirmRecord(null)
      setDeletePtr(true)
      showToast('Record deleted', 'success')
    },
    onError: (err: any) => {
      showToast(err?.response?.data?.detail ?? 'Delete failed', 'error')
    },
  })

  const ipamQuery = useQuery({
    queryKey: ['ipam-address', selectedRecord?.value],
    queryFn: () => addressesApi.byIp(selectedRecord!.value),
    enabled: !!selectedRecord && ['A', 'AAAA'].includes(selectedRecord.record_type),
    retry: false,
  })

  const { data: subnets } = useQuery({ queryKey: ['subnets'], queryFn: subnetsApi.list })

  const matchingSubnet = useMemo(() => {
    if (!selectedRecord || !subnets || !['A', 'AAAA'].includes(selectedRecord.record_type)) return null
    return subnets.find(s => ipInCidr(selectedRecord.value, s.cidr)) ?? null
  }, [selectedRecord, subnets])

  const effectiveSubnetId = matchingSubnet?.id ?? selectedAddSubnetId

  const createIpamMutation = useMutation({
    mutationFn: () => addressesApi.create({
      address: selectedRecord!.value,
      subnet_id: effectiveSubnetId!,
      status: 'assigned',
      hostname: selectedRecord!.name || null,
      mac_address: null,
      description: null,
      notes: null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ipam-address', selectedRecord?.value] })
      setEditingNotes(true)
    },
  })

  const updateNotesMutation = useMutation({
    mutationFn: () => addressesApi.update(ipamQuery.data!.id, { notes: notesValue || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ipam-address', selectedRecord?.value] })
      setEditingNotes(false)
    },
  })

  useEffect(() => {
    setNotesValue(ipamQuery.data?.notes ?? '')
    setEditingNotes(false)
    setSelectedAddSubnetId(null)
  }, [ipamQuery.data])

  // Only show zones from configured providers
  const filteredZones = useMemo(
    () => dnsProviders.length
      ? (zones ?? []).filter(z => dnsProviders.includes(z.source))
      : (zones ?? []),
    [zones, dnsProviders]
  )

  // Zones matching the zone-list search box (zone name or reverse-zone CIDR)
  const searchedZones = useMemo(() => {
    const q = zoneSearch.trim().toLowerCase()
    if (!q) return filteredZones
    return filteredZones.filter(z =>
      z.zone.toLowerCase().includes(q) ||
      (reverseZoneToCidr(z.zone)?.toLowerCase().includes(q) ?? false)
    )
  }, [filteredZones, zoneSearch])

  // Zones deduplicated by name for combined view
  const combinedZones = useMemo(() => {
    const seen = new Set<string>()
    return searchedZones.filter(z => {
      if (seen.has(z.zone)) return false
      seen.add(z.zone)
      return true
    })
  }, [searchedZones])

  // Zones grouped by source for by-server view
  const groupedZones = useMemo(() => {
    const groups = new Map<string, DNSZone[]>()
    for (const z of searchedZones) {
      if (!groups.has(z.source)) groups.set(z.source, [])
      groups.get(z.source)!.push(z)
    }
    return groups
  }, [searchedZones])

  // Unique sources present in zones (ground truth for multi-provider detection)
  const uniqueZoneSources = useMemo(
    () => new Set(filteredZones.map(z => z.source).filter(Boolean)),
    [filteredZones]
  )

  const presentTypes = useMemo(
    () => [...new Set((records ?? []).map(r => r.record_type))].sort(),
    [records]
  )

  const handleSort = (col: SortCol) => {
    if (sortCol === col) setSortDir(d => d === 'asc' ? 'desc' : 'asc')
    else { setSortCol(col); setSortDir('asc') }
  }

  const processed = useMemo(() => {
    const q = filter.toLowerCase()
    let result = (records ?? []).filter(r =>
      (!q || r.name.toLowerCase().includes(q) || r.value.toLowerCase().includes(q)) &&
      (!typeFilter || r.record_type === typeFilter)
    )
    if (sortCol) {
      result = [...result].sort((a, b) => {
        const av = sortCol === 'ttl' ? a.ttl : a[sortCol].toLowerCase()
        const bv = sortCol === 'ttl' ? b.ttl : b[sortCol].toLowerCase()
        return av < bv ? (sortDir === 'asc' ? -1 : 1)
             : av > bv ? (sortDir === 'asc' ?  1 : -1)
             : 0
      })
    }
    return result
  }, [records, filter, typeFilter, sortCol, sortDir])

  const groupedByServer = useMemo(() => {
    const groups = new Map<string, DNSRecord[]>()
    for (const r of processed) {
      const src = r.source || 'unknown'
      if (!groups.has(src)) groups.set(src, [])
      groups.get(src)!.push(r)
    }
    return groups
  }, [processed])

  const recordSources = useMemo(
    () => new Set((records ?? []).map(r => r.source).filter(Boolean)),
    [records]
  )

  const multiProvider =
    uniqueZoneSources.size > 1 ||
    recordSources.size > 1 ||
    (providers?.dns?.length ?? 0) > 1

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: key === 'ttl' ? Number(e.target.value) : e.target.value }))

  const resetZone = (z: string, source?: string) => {
    setSelectedZone(z)
    setSelectedZoneSource(source ?? filteredZones.find(fz => fz.zone === z)?.source ?? null)
    setFilter(''); setTypeFilter('')
    setSortCol(null); setShowForm(false); setSelectedRecord(null)
  }

  const thProps = (col: SortCol) => ({
    className: 'sortable' + (sortCol === col ? ' sorted' : ''),
    onClick: () => handleSort(col),
  })

  const renderTable = (recs: DNSRecord[]) => (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>
            <th {...thProps('name')}>Name <SortArrow col="name" sortCol={sortCol} sortDir={sortDir} /></th>
            <th {...thProps('record_type')}>Type <SortArrow col="record_type" sortCol={sortCol} sortDir={sortDir} /></th>
            <th {...thProps('value')}>Value <SortArrow col="value" sortCol={sortCol} sortDir={sortDir} /></th>
            <th {...thProps('ttl')}>TTL <SortArrow col="ttl" sortCol={sortCol} sortDir={sortDir} /></th>
            {multiProvider && <th>Source</th>}
            <th style={{ width: '2.5rem' }}></th>
          </tr>
        </thead>
        <tbody>
          {recs.length === 0 && (
            <tr>
              <td colSpan={multiProvider ? 6 : 5} className="empty-state">
                No records{filter || typeFilter ? ' matching filters' : ''}.
              </td>
            </tr>
          )}
          {recs.map((r, i) => (
            <tr key={i} className="clickable" {...rowActivation(() => setSelectedRecord(r))}>
              <td><span className="font-mono">{r.name}</span></td>
              <td>
                <span className={`badge ${TYPE_BADGE[r.record_type] ?? 'badge-gray'}`}>
                  {r.record_type}
                </span>
              </td>
              <td><span className="font-mono">{r.value}</span></td>
              <td><span className="text-muted">{r.ttl}</span></td>
              {multiProvider && (
                <td>
                  {r.source && (
                    <span className="badge badge-gray" style={{ fontSize: '0.65rem' }}>
                      {SOURCE_LABEL[r.source] ?? r.source}
                    </span>
                  )}
                </td>
              )}
              <td onClick={e => e.stopPropagation()}>
                <button
                  className="btn-danger btn-sm"
                  aria-label={`Delete ${r.record_type} record ${r.name}`}
                  onClick={() => setConfirmRecord(r)}
                  disabled={deleteMutation.isPending}
                >
                  <Trash2 size={12} />
                </button>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )

  const renderZoneItem = (z: DNSZone, key: string) => {
    const cidr = reverseZoneToCidr(z.zone)
    return (
      <div
        key={key}
        className={'panel-list-item' + (selectedZone === z.zone ? ' active' : '')}
        onClick={() => resetZone(z.zone, z.source)}
        title={z.zone}
      >
        {cidr ?? z.zone}
        {cidr && <div className="panel-list-item-sub">{z.zone}</div>}
      </div>
    )
  }

  const toggleGroup = (key: string) =>
    setExpandedGroups(prev => {
      const next = new Set(prev)
      next.has(key) ? next.delete(key) : next.add(key)
      return next
    })

  const renderZoneTypeGroups = (zoneList: DNSZone[], keyPrefix: string) =>
    ZONE_GROUPS.map(({ key, label }) => {
      const items = zoneList.filter(z => classifyZone(z.zone) === key)
      if (items.length === 0) return null
      const groupKey = `${keyPrefix}:${key}`
      const expanded = zoneSearch.trim() !== '' || expandedGroups.has(groupKey)
      return (
        <div key={groupKey}>
          <div className="zone-type-header" onClick={() => toggleGroup(groupKey)}>
            <span className="zone-type-arrow">{expanded ? '▼' : '▶'}</span>
            <span>{label}</span>
            <span className="panel-server-count">{items.length}</span>
          </div>
          {expanded && items.map(z => renderZoneItem(z, `${keyPrefix}:${z.zone}`))}
        </div>
      )
    })

  return (
    <div>
      <div className="page-header">
        <h1>DNS</h1>
        <SyncBar type="dns" />
      </div>

      <div className="two-panel">
        <div className="panel-list">
          <div className="panel-list-header" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
            <span>Zones</span>
            {multiProvider && (
              <div className="view-toggle">
                <button
                  className={viewMode === 'combined' ? 'active' : ''}
                  onClick={() => setViewMode('combined')}
                >
                  All
                </button>
                <button
                  className={viewMode === 'by-server' ? 'active' : ''}
                  onClick={() => setViewMode('by-server')}
                >
                  By Server
                </button>
              </div>
            )}
          </div>
          <div className="panel-list-search">
            <input
              type="text"
              placeholder="Filter zones…"
              value={zoneSearch}
              onChange={e => setZoneSearch(e.target.value)}
              aria-label="Filter zones"
            />
          </div>
          {loadingZones && <p className="loading" style={{ padding: '0.75rem' }}>Loading…</p>}
          {viewMode === 'combined' ? (
            renderZoneTypeGroups(combinedZones, 'combined')
          ) : (
            [...groupedZones.entries()].map(([src, zoneList]) => (
              <div key={src}>
                <div className="panel-server-header">
                  <span>{SOURCE_LABEL[src] ?? src}</span>
                  <span className="panel-server-count">{zoneList.length}</span>
                </div>
                {renderZoneTypeGroups(zoneList, src)}
              </div>
            ))
          )}
          {searchedZones.length === 0 && !loadingZones && (
            <p className="loading" style={{ padding: '0.75rem' }}>
              {zoneSearch.trim() ? 'No zones match the filter.' : 'No zones found.'}
            </p>
          )}
        </div>

        <div className="panel-main">
          {selectedZone ? (
            <>
              <div className="page-header">
                <h1 title={selectedZone ?? ''}>
                  {(selectedZone && reverseZoneToCidr(selectedZone)) || selectedZone}
                </h1>
                <div className="page-header-actions">
                  <div className="filter-bar" style={{ margin: 0 }}>
                    <SlidersHorizontal size={14} style={{ color: 'var(--text-muted)', flexShrink: 0 }} />
                    <input
                      placeholder="Filter name or value…"
                      value={filter}
                      onChange={e => setFilter(e.target.value)}
                      style={{ width: '200px' }}
                    />
                  </div>
                  {!showForm && (
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => {
                        const defaultSource = selectedZoneSource ?? dnsProviders[0] ?? ''
                        setForm({ ...emptyForm, source: defaultSource })
                        setShowForm(true)
                      }}
                    >
                      <Plus size={13} /> Add Record
                    </button>
                  )}
                </div>
              </div>

              {presentTypes.length > 0 && (
                <div className="type-chips">
                  <button
                    className={'type-chip' + (!typeFilter ? ' active' : '')}
                    onClick={() => setTypeFilter('')}
                  >
                    All ({(records ?? []).length})
                  </button>
                  {presentTypes.map(t => (
                    <button
                      key={t}
                      className={'type-chip' + (typeFilter === t ? ' active' : '')}
                      onClick={() => setTypeFilter(typeFilter === t ? '' : t)}
                    >
                      {t} ({(records ?? []).filter(r => r.record_type === t).length})
                    </button>
                  ))}
                </div>
              )}

              {showForm && (
                <div className="inline-form">
                  <div className="form-grid">
                    <div className="form-field">
                      <label>Name</label>
                      <input placeholder="server01" value={form.name} onChange={set('name')} />
                    </div>
                    <div className="form-field">
                      <label>Type</label>
                      <select value={form.record_type} onChange={set('record_type')}>
                        {RECORD_TYPES.map(t => <option key={t} value={t}>{t}</option>)}
                      </select>
                    </div>
                    <div className="form-field">
                      <label>Value</label>
                      <input placeholder="10.0.0.1" value={form.value} onChange={set('value')} />
                    </div>
                    <div className="form-field">
                      <label>TTL (seconds)</label>
                      <input type="number" value={form.ttl} onChange={set('ttl')} />
                    </div>
                    {multiProvider && (
                      <div className="form-field">
                        <label>Provider</label>
                        <select value={form.source} onChange={set('source')}>
                          {dnsProviders.map(p => (
                            <option key={p} value={p}>{SOURCE_LABEL[p] ?? p}</option>
                          ))}
                        </select>
                      </div>
                    )}
                  </div>
                  {form.record_type === 'A' && (
                    <div className="form-field form-field-wide">
                      <PtrCheckbox
                        label="Also create PTR record"
                        checked={registerPtr}
                        onChange={setRegisterPtr}
                        disabled={selectedZoneIsPihole}
                        disabledNote="(provider does not support PTR)"
                      />
                    </div>
                  )}
                  <div className="form-actions">
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => createMutation.mutate()}
                      disabled={createMutation.isPending || !form.name || !form.value}
                    >
                      {createMutation.isPending ? 'Adding…' : 'Add'}
                    </button>
                    <button className="btn-ghost btn-sm" onClick={() => { setShowForm(false); setForm(emptyForm); setRegisterPtr(false) }}>
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

              {loadingRecords ? (
                <p className="loading">Loading records…</p>
              ) : viewMode === 'combined' ? (
                renderTable(processed)
              ) : (
                <>
                  {[...groupedByServer.entries()].map(([src, recs]) => (
                    <div key={src} className="server-group">
                      <div className="server-group-header">
                        <span>{SOURCE_LABEL[src] ?? src}</span>
                        <span style={{ fontSize: '0.7rem', fontWeight: 500, letterSpacing: 0, textTransform: 'none', color: 'var(--text-muted)' }}>
                          {recs.length} record{recs.length !== 1 ? 's' : ''}
                        </span>
                      </div>
                      {renderTable(recs)}
                    </div>
                  ))}
                  {groupedByServer.size === 0 && renderTable([])}
                </>
              )}
            </>
          ) : (
            <div className="empty-state">Select a zone from the list.</div>
          )}
        </div>
      </div>

      {confirmRecord && (
        <ConfirmModal
          title="Delete DNS Record"
          message={`Delete ${confirmRecord.record_type} record "${confirmRecord.name}"?`}
          onConfirm={() => { deleteMutation.mutate(confirmRecord); setConfirmRecord(null) }}
          onCancel={() => { setConfirmRecord(null); setDeletePtr(true) }}
          extra={confirmRecord.record_type === 'A' ? (
            <PtrCheckbox
              label="Also delete matching PTR record"
              checked={deletePtr}
              onChange={setDeletePtr}
            />
          ) : undefined}
        />
      )}

      {selectedRecord && (
        <DetailPanel
          title={selectedRecord.name}
          subtitle={`${selectedRecord.record_type} · ${selectedRecord.zone}`}
          pingTarget={PINGABLE.has(selectedRecord.record_type) ? selectedRecord.value : undefined}
          fields={[
            { label: 'Name',   value: <span className="font-mono">{selectedRecord.name}</span> },
            { label: 'Type',   value: <span className={`badge ${TYPE_BADGE[selectedRecord.record_type] ?? 'badge-gray'}`}>{selectedRecord.record_type}</span> },
            { label: 'Value',  value: <span className="font-mono">{selectedRecord.value}</span> },
            { label: 'TTL',    value: `${selectedRecord.ttl}s` },
            { label: 'Zone',   value: selectedRecord.zone },
            { label: 'Source', value: (SOURCE_LABEL[selectedRecord.source] ?? selectedRecord.source) || '—' },
          ]}
          extra={['A', 'AAAA'].includes(selectedRecord.record_type) ? (
            <div>
              <div className="detail-section-title" style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                IPAM Notes
                <span className="badge badge-gray" style={{ fontSize: '0.6rem' }}>IPAM</span>
              </div>
              {ipamQuery.isLoading ? (
                <p className="loading" style={{ fontSize: '0.8rem' }}>Loading…</p>
              ) : !ipamQuery.data ? (
                <div style={{ margin: '0.5rem 0' }}>
                  <div style={{ fontSize: '0.8rem', color: 'var(--text-muted)', marginBottom: '0.4rem' }}>Not tracked in IPAM.</div>
                  {!matchingSubnet && subnets && subnets.length > 0 && (
                    <select
                      value={selectedAddSubnetId ?? ''}
                      onChange={e => setSelectedAddSubnetId(Number(e.target.value) || null)}
                      style={{ fontSize: '0.75rem', marginBottom: '0.4rem', width: '100%' }}
                    >
                      <option value="">Select subnet…</option>
                      {subnets.map(s => (
                        <option key={s.id} value={s.id}>{s.name} ({s.cidr})</option>
                      ))}
                    </select>
                  )}
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => createIpamMutation.mutate()}
                    disabled={createIpamMutation.isPending || !effectiveSubnetId}
                    style={{ fontSize: '0.7rem' }}
                  >
                    {createIpamMutation.isPending ? 'Adding…' : 'Add to IPAM'}
                  </button>
                </div>
              ) : editingNotes ? (
                <div>
                  <textarea
                    value={notesValue}
                    onChange={e => setNotesValue(e.target.value)}
                    rows={4}
                    autoFocus
                    style={{ resize: 'vertical', width: '100%', marginBottom: '0.5rem' }}
                  />
                  <div className="form-actions">
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => updateNotesMutation.mutate()}
                      disabled={updateNotesMutation.isPending}
                    >
                      {updateNotesMutation.isPending ? 'Saving…' : 'Save'}
                    </button>
                    <button className="btn-ghost btn-sm" onClick={() => setEditingNotes(false)}>Cancel</button>
                  </div>
                </div>
              ) : (
                <div style={{ display: 'flex', gap: '0.5rem', alignItems: 'flex-start' }}>
                  <span style={{ flex: 1, fontSize: '0.82rem', color: notesValue ? 'inherit' : 'var(--text-muted)', whiteSpace: 'pre-wrap' }}>
                    {notesValue || '—'}
                  </span>
                  <button
                    className="btn-ghost btn-sm"
                    onClick={() => setEditingNotes(true)}
                    style={{ fontSize: '0.7rem', fontWeight: 500, flexShrink: 0 }}
                  >
                    Edit
                  </button>
                </div>
              )}
            </div>
          ) : undefined}
          syncedAt={selectedRecord.synced_at}
          onClose={() => { setSelectedRecord(null); setEditingNotes(false) }}
        />
      )}
    </div>
  )
}
