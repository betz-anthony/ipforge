import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { SlidersHorizontal, Plus, X, Trash2 } from 'lucide-react'
import { dnsApi, type DNSRecord } from '../api/client'

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

const emptyForm = { name: '', record_type: 'A', value: '', ttl: 3600 }

export default function DNS() {
  const [selectedZone, setSelectedZone] = useState<string | null>(null)
  const [filter, setFilter]             = useState('')
  const [showForm, setShowForm]         = useState(false)
  const [form, setForm]                 = useState(emptyForm)
  const qc = useQueryClient()

  const { data: zones, isLoading: loadingZones } = useQuery({
    queryKey: ['dns-zones'],
    queryFn: dnsApi.listZones,
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
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (record: DNSRecord) => dnsApi.deleteRecord(selectedZone!, record),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['dns-records', selectedZone] }),
  })

  const q = filter.toLowerCase()
  const filtered: DNSRecord[] = records?.filter(r =>
    !q || r.name.toLowerCase().includes(q) || r.value.toLowerCase().includes(q) || r.record_type.toLowerCase().includes(q)
  ) ?? []

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: key === 'ttl' ? Number(e.target.value) : e.target.value }))

  return (
    <div>
      <div className="page-header">
        <h1>DNS</h1>
      </div>

      <div className="two-panel">
        <div className="panel-list">
          <div className="panel-list-header">Zones</div>
          {loadingZones && <p className="loading" style={{ padding: '0.75rem' }}>Loading…</p>}
          {zones?.map(z => (
            <div
              key={z}
              className={'panel-list-item' + (selectedZone === z ? ' active' : '')}
              onClick={() => { setSelectedZone(z); setFilter(''); setShowForm(false) }}
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
                      placeholder="Filter records…"
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
                        <th>Name</th>
                        <th>Type</th>
                        <th>Value</th>
                        <th>TTL</th>
                        <th></th>
                      </tr>
                    </thead>
                    <tbody>
                      {filtered.length === 0 && (
                        <tr><td colSpan={5} className="empty-state">No records{filter ? ' matching filter' : ''}.</td></tr>
                      )}
                      {filtered.map((r, i) => (
                        <tr key={i}>
                          <td><span className="font-mono">{r.name}</span></td>
                          <td>
                            <span className={`badge ${TYPE_BADGE[r.record_type] ?? 'badge-gray'}`}>
                              {r.record_type}
                            </span>
                          </td>
                          <td><span className="font-mono">{r.value}</span></td>
                          <td><span className="text-muted">{r.ttl}</span></td>
                          <td>
                            <button
                              className="btn-danger btn-sm"
                              onClick={() => deleteMutation.mutate(r)}
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
