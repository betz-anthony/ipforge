import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2 } from 'lucide-react'
import { subnetRangesApi, addressesApi, type Subnet, type RangeKind, type MapCell } from '../api/client'
import { isValidIPv4, isValidIPv6, isValidEUI48 } from '../utils/ip'
import { useToast } from '../contexts/ToastContext'
import { apiError } from '../utils/apiError'

const KINDS: RangeKind[] = ['gateway', 'dhcp_pool', 'static', 'reserved']
const STATUSES = ['reserved', 'assigned', 'available'] as const
const emptyNewAddrForm = { status: 'reserved' as string, hostname: '', mac_address: '', description: '' }

const STATUS_COLOR: Record<string, string> = {
  free:       'var(--surface-2)',
  available:  '#4ade80',
  assigned:   '#60a5fa',
  reserved:   '#fbbf24',
  discovered: '#fbbf24',
  deprecated: 'var(--text-muted)',
}

export default function SubnetSpace({ subnet }: { subnet: Subnet }) {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const isV6 = subnet.ip_version === 6

  const { data: ranges } = useQuery({
    queryKey: ['ranges', subnet.id],
    queryFn: () => subnetRangesApi.list(subnet.id),
  })
  const { data: map } = useQuery({
    queryKey: ['subnet-map', subnet.id],
    queryFn: () => subnetRangesApi.map(subnet.id),
  })

  const [showAdd, setShowAdd] = useState(false)
  const [start, setStart] = useState('')
  const [end, setEnd] = useState('')
  const [kind, setKind] = useState<RangeKind>('reserved')
  const [label, setLabel] = useState('')
  const [ipErr, setIpErr] = useState('')
  const [selected, setSelected] = useState<MapCell | null>(null)
  const [newAddrForm, setNewAddrForm] = useState(emptyNewAddrForm)
  const [macError, setMacError] = useState('')

  const validIp = (v: string) => isV6 ? isValidIPv6(v) : isValidIPv4(v)

  const createRange = useMutation({
    mutationFn: () => subnetRangesApi.create(subnet.id, {
      start_ip: start.trim(), end_ip: (end.trim() || start.trim()), kind, label: label.trim() || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ranges', subnet.id] })
      qc.invalidateQueries({ queryKey: ['subnet-map', subnet.id] })
      qc.invalidateQueries({ queryKey: ['subnets'] })
      setShowAdd(false); setStart(''); setEnd(''); setLabel(''); setKind('reserved')
      showToast('Range added', 'success')
    },
    onError: (err: any) => {
      const e = apiError(err, 'Add failed')
      showToast(e.message, 'error', { hint: e.hint, detail: e.detail })
    },
  })

  const deleteRange = useMutation({
    mutationFn: (id: number) => subnetRangesApi.remove(subnet.id, id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ranges', subnet.id] })
      qc.invalidateQueries({ queryKey: ['subnet-map', subnet.id] })
      qc.invalidateQueries({ queryKey: ['subnets'] })
      showToast('Range deleted', 'success')
    },
    onError: (err: any) => {
      const e = apiError(err, 'Delete failed')
      showToast(e.message, 'error', { hint: e.hint, detail: e.detail })
    },
  })

  const createAddr = useMutation({
    mutationFn: (ip: string) => addressesApi.create({
      address: ip, subnet_id: subnet.id,
      status: newAddrForm.status as any,
      hostname: newAddrForm.hostname || null,
      mac_address: newAddrForm.mac_address || null,
      description: newAddrForm.description || null,
    } as any),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnet-map', subnet.id] })
      qc.invalidateQueries({ queryKey: ['subnets'] })
      qc.invalidateQueries({ queryKey: ['addresses'] })
      setSelected(null)
      setNewAddrForm(emptyNewAddrForm)
      showToast('Address created', 'success')
    },
    onError: (err: any) => {
      const e = apiError(err, 'Create failed')
      showToast(e.message, 'error', { hint: e.hint, detail: e.detail })
    },
  })

  const startValid = start && validIp(start)
  const endValid = !end || validIp(end)
  const canAdd = startValid && endValid

  return (
    <div style={{ marginBottom: '1rem' }}>
      <div className="detail-section-title">Reserved Ranges</div>
      {(ranges ?? []).length === 0 && !showAdd && (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.4rem 0' }}>No reserved ranges.</p>
      )}
      {(ranges ?? []).map(r => (
        <div key={r.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', fontSize: '0.8rem', padding: '0.2rem 0' }}>
          <span className="font-mono">{r.start_ip}{r.end_ip !== r.start_ip ? `–${r.end_ip}` : ''}</span>
          <span className="badge badge-gray">{r.kind}</span>
          {r.source && <span className="badge badge-blue" style={{ fontSize: '0.65rem' }}>synced · {r.source}</span>}
          {r.label && <span style={{ color: 'var(--text-muted)' }}>{r.label}</span>}
          <button className="btn-ghost btn-sm" style={{ marginLeft: 'auto' }} onClick={() => deleteRange.mutate(r.id)}>
            <Trash2 size={12} />
          </button>
        </div>
      ))}

      {showAdd ? (
        <div className="inline-form" style={{ marginTop: '0.5rem' }}>
          <div className="form-grid">
            <div className={`form-field${start && !startValid ? ' form-field-error' : ''}`}>
              <label htmlFor="range-start">Start IP</label>
              <input id="range-start" value={start} onChange={e => { setStart(e.target.value); setIpErr('') }}
                onBlur={() => setIpErr(start && !startValid ? 'Invalid IP' : '')} />
            </div>
            <div className={`form-field${end && !endValid ? ' form-field-error' : ''}`}>
              <label htmlFor="range-end">End IP (optional)</label>
              <input id="range-end" value={end} onChange={e => setEnd(e.target.value)} placeholder="same as start" />
            </div>
            <div className="form-field">
              <label htmlFor="range-kind">Kind</label>
              <select id="range-kind" value={kind} onChange={e => setKind(e.target.value as RangeKind)}>
                {KINDS.map(k => <option key={k} value={k}>{k}</option>)}
              </select>
            </div>
            <div className="form-field">
              <label htmlFor="range-label">Label</label>
              <input id="range-label" value={label} onChange={e => setLabel(e.target.value)} placeholder="optional" />
            </div>
          </div>
          {ipErr && <span className="form-field-error-msg">{ipErr}</span>}
          <div className="form-actions">
            <button className="btn-primary btn-sm" disabled={!canAdd || createRange.isPending} onClick={() => createRange.mutate()}>
              Add Range
            </button>
            <button className="btn-ghost btn-sm" onClick={() => setShowAdd(false)}>Cancel</button>
          </div>
        </div>
      ) : (
        <button className="btn-ghost btn-sm" style={{ marginTop: '0.4rem' }} onClick={() => setShowAdd(true)}>
          <Plus size={12} /> Add Range
        </button>
      )}

      <div className="detail-section-title" style={{ marginTop: '1rem' }}>Address Map</div>
      {!map ? (
        <p className="loading" style={{ fontSize: '0.8rem' }}>Loading…</p>
      ) : map.too_large ? (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>
          Subnet too large to map ({map.host_count.toLocaleString()} hosts) — drill into a child subnet.
        </p>
      ) : (
        <>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, 14px)', gap: '2px', marginTop: '0.5rem' }}>
            {map.cells!.map(c => (
              <button
                key={c.ip}
                title={`${c.ip} · ${c.status}${c.collision ? ' · collision' : ''}`}
                onClick={() => { setSelected(c); setNewAddrForm(emptyNewAddrForm); setMacError('') }}
                style={{
                  width: 14, height: 14, padding: 0, borderRadius: 2, cursor: 'pointer',
                  background: STATUS_COLOR[c.status] ?? 'var(--surface-2)',
                  outline: c.collision ? '2px solid var(--danger)' : 'none',
                  outlineOffset: -2,
                  border: selected?.ip === c.ip ? '1px solid var(--text)' : '1px solid transparent',
                }}
              />
            ))}
          </div>
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: '0.6rem', marginTop: '0.5rem', fontSize: '0.7rem', color: 'var(--text-muted)' }}>
            {['free', 'assigned', 'reserved', 'discovered', 'deprecated'].map(st => (
              <span key={st} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
                <span style={{ width: 10, height: 10, borderRadius: 2, background: STATUS_COLOR[st], display: 'inline-block' }} />
                {st}
              </span>
            ))}
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.25rem' }}>
              <span style={{ width: 10, height: 10, borderRadius: 2, outline: '2px solid var(--danger)', outlineOffset: -2, display: 'inline-block' }} />
              collision
            </span>
          </div>
          {selected && (
            <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', padding: '0.5rem', background: 'var(--surface-2)', borderRadius: 4 }}>
              <span className="font-mono">{selected.ip}</span> · {selected.status}
              {selected.collision && <span className="badge badge-red" style={{ marginLeft: '0.4rem' }}>collision</span>}
              {selected.status === 'free' && (
                <div style={{ marginTop: '0.5rem', display: 'flex', flexWrap: 'wrap', gap: '0.4rem', alignItems: 'flex-start' }}>
                  <select
                    aria-label="Status"
                    value={newAddrForm.status}
                    onChange={e => setNewAddrForm(f => ({ ...f, status: e.target.value }))}
                    style={{ width: '110px' }}
                  >
                    {STATUSES.map(s => <option key={s} value={s}>{s}</option>)}
                  </select>
                  <input
                    aria-label="Hostname"
                    placeholder="Hostname (optional)"
                    value={newAddrForm.hostname}
                    onChange={e => setNewAddrForm(f => ({ ...f, hostname: e.target.value }))}
                    style={{ width: '160px' }}
                  />
                  <div>
                    <input
                      aria-label="MAC address"
                      placeholder="MAC (optional)"
                      value={newAddrForm.mac_address}
                      onChange={e => { setNewAddrForm(f => ({ ...f, mac_address: e.target.value })); if (macError) setMacError('') }}
                      onBlur={() => setMacError(newAddrForm.mac_address && !isValidEUI48(newAddrForm.mac_address) ? 'Invalid MAC' : '')}
                      style={{ width: '150px' }}
                    />
                    {macError && <div className="form-field-error-msg" style={{ fontSize: '0.7rem' }}>{macError}</div>}
                  </div>
                  <input
                    aria-label="Description"
                    placeholder="Description (optional)"
                    value={newAddrForm.description}
                    onChange={e => setNewAddrForm(f => ({ ...f, description: e.target.value }))}
                    style={{ width: '160px' }}
                  />
                  <button className="btn-primary btn-sm"
                    disabled={createAddr.isPending || !!macError}
                    onClick={() => createAddr.mutate(selected.ip)}>
                    Create address here
                  </button>
                  <button className="btn-ghost btn-sm"
                    onClick={() => { setSelected(null); setNewAddrForm(emptyNewAddrForm); setMacError('') }}>
                    Cancel
                  </button>
                </div>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
