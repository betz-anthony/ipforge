import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SlidersHorizontal, Plus, X, Trash2 } from 'lucide-react'
import { dnsApi, providersApi, type DNSRecord } from '../api/client'
import SyncBar from '../components/SyncBar'

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

type SortCol = 'name' | 'record_type' | 'value' | 'ttl'
type SortDir = 'asc' | 'desc'

const emptyForm = { name: '', record_type: 'A', value: '', ttl: 3600, source: '' }

function SortArrow({ col, sortCol, sortDir }: { col: SortCol; sortCol: SortCol | null; sortDir: SortDir }) {
  const active = col === sortCol
  return (
    <span className="sort-arrow">
      {active ? (sortDir === 'asc' ? '▲' : '▼') : '⇅'}
    </span>
  )
}

export default function DNS() {
  const [selectedZone, setSelectedZone] = useState<string | null>(null)
  const [filter, setFilter]             = useState('')
  const [typeFilter, setTypeFilter]     = useState<string>('')
  const [sortCol, setSortCol]           = useState<SortCol | null>(null)
  const [sortDir, setSortDir]           = useState<SortDir>('asc')
  const [showForm, setShowForm]         = useState(false)
  const [form, setForm]                 = useState(emptyForm)
  const qc = useQueryClient()

  const { data: zones, isLoading: loadingZones } = useQuery({
    queryKey: ['dns-zones'],
    queryFn: dnsApi.listZones,
  })

  const { data: providers } = useQuery({
    queryKey: ['providers'],
    queryFn: providersApi.get,
  })

  const { data: records, isLoading: loadingRecords } = useQuery({
    queryKey: ['dns-records', selectedZone],
    queryFn: () => dnsApi.listRecords(selectedZone!),
    enabled: !!selectedZone,
  })

  const createMutation = useMutation({
    mutationFn: () => dnsApi.createRecord(selectedZone!, form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['dns-records', selectedZone] })
      setForm(f => ({ ...emptyForm, source: f.source }))
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (record: DNSRecord) => dnsApi.deleteRecord(selectedZone!, record),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dns-records', selectedZone] }),
  })

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

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: key === 'ttl' ? Number(e.target.value) : e.target.value }))

  const resetZone = (z: string) => {
    setSelectedZone(z); setFilter(''); setTypeFilter('')
    setSortCol(null); setShowForm(false)
  }

  const thProps = (col: SortCol) => ({
    className: 'sortable' + (sortCol === col ? ' sorted' : ''),
    onClick: () => handleSort(col),
  })

  const dnsProviders = providers?.dns ?? []
  const multiProvider = dnsProviders.length > 1

  return (
    <div>
      <div className="page-header">
        <h1>DNS</h1>
        <SyncBar type="dns" />
      </div>

      <div className="two-panel">
        <div className="panel-list">
          <div className="panel-list-header">Zones</div>
          {loadingZones && <p className="loading" style={{ padding: '0.75rem' }}>Loading…</p>}
          {zones?.map(z => (
            <div
              key={z}
              className={'panel-list-item' + (selectedZone === z ? ' active' : '')}
              onClick={() => resetZone(z)}
            >
              {z}
            </div>
          ))}
          {zones?.length === 0 && <p className="loading" style={{ padding: '0.75rem' }}>No zones found.</p>}
        </div>

        <div className="panel-main">
          {selectedZone ? (
            <>
              <div className="page-header">
                <h1>{selectedZone}</h1>
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
                    <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
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
                  <div className="form-actions">
                    <button
                      className="btn-primary btn-sm"
                      onClick={() => createMutation.mutate()}
                      disabled={createMutation.isPending || !form.name || !form.value}
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

              {loadingRecords ? (
                <p className="loading">Loading records…</p>
              ) : (
                <div className="table-wrap">
                  <table>
                    <thead>
                      <tr>
                        <th {...thProps('name')}>Name <SortArrow col="name" sortCol={sortCol} sortDir={sortDir} /></th>
                        <th {...thProps('record_type')}>Type <SortArrow col="record_type" sortCol={sortCol} sortDir={sortDir} /></th>
                        <th {...thProps('value')}>Value <SortArrow col="value" sortCol={sortCol} sortDir={sortDir} /></th>
                        <th {...thProps('ttl')}>TTL <SortArrow col="ttl" sortCol={sortCol} sortDir={sortDir} /></th>
                        {multiProvider && <th>Source</th>}
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {processed.length === 0 && (
                        <tr>
                          <td colSpan={multiProvider ? 6 : 5} className="empty-state">
                            No records{filter || typeFilter ? ' matching filters' : ''}.
                          </td>
                        </tr>
                      )}
                      {processed.map((r, i) => (
                        <tr key={i}>
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
                          <td>
                            <button
                              className="btn-danger btn-sm"
                              onClick={() => window.confirm(`Delete ${r.record_type} record "${r.name}"?`) && deleteMutation.mutate(r)}
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
              )}
            </>
          ) : (
            <div className="empty-state">Select a zone from the list.</div>
          )}
        </div>
      </div>
    </div>
  )
}
