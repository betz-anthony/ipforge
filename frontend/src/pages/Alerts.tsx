import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { CheckCircle2, Bell } from 'lucide-react'
import { alertEventsApi, alertChannelsApi } from '../api/client'
import { useToast } from '../contexts/ToastContext'
import SearchInput from '../components/SearchInput'
import EmptyState from '../components/EmptyState'
import { TableSkeleton } from '../components/Skeleton'
import { useTableSort } from '../hooks/useTableSort'

const TRIGGERS = [
  { value: '',             label: 'All triggers' },
  { value: 'collision',    label: 'Collision' },
  { value: 'utilization',  label: 'Utilization' },
  { value: 'rogue',        label: 'Rogue device' },
  { value: 'sync_error',   label: 'Sync error' },
  { value: 'stale_queue',          label: 'Stale-IP queue' },
  { value: 'ip_request_submitted', label: 'IP request submitted' },
  { value: 'ip_request_resolved',  label: 'IP request resolved' },
]

export default function Alerts() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const [state, setState] = useState('')
  const [trigger, setTrigger] = useState('')

  const { data: events = [], isLoading } = useQuery({
    queryKey: ['alert-events', state, trigger],
    queryFn: () => alertEventsApi.list({
      state: state || undefined,
      trigger_type: trigger || undefined,
    }),
    refetchInterval: 15000,
  })
  const { data: channels = [] } = useQuery({
    queryKey: ['alert-channels'],
    queryFn: alertChannelsApi.list,
  })

  const ack = useMutation({
    mutationFn: (id: number) => alertEventsApi.ack(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['alert-events'] })
      showToast('Acknowledged', 'success')
    },
    onError: () => showToast('Acknowledge failed', 'error'),
  })

  const chName = (id: number) => channels.find(c => c.id === id)?.name ?? `#${id}`

  const [searchTerm, setSearchTerm] = useState('')
  const { sortKey, toggleSort, sortIcon, dir } = useTableSort<
    'state' | 'resource' | 'first' | 'last'
  >('last', 'desc')

  const visibleEvents = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    const filtered = q
      ? events.filter(e => e.resource_key.toLowerCase().includes(q) || e.state.toLowerCase().includes(q))
      : events.slice()
    const cmp = (a: typeof events[number], b: typeof events[number]) => {
      switch (sortKey) {
        case 'state':    return a.state.localeCompare(b.state) * dir
        case 'resource': return a.resource_key.localeCompare(b.resource_key) * dir
        case 'first':    return (a.first_fired_at ?? '').localeCompare(b.first_fired_at ?? '') * dir
        case 'last':     return (a.last_fired_at ?? '').localeCompare(b.last_fired_at ?? '') * dir
      }
    }
    return filtered.sort(cmp)
  }, [events, searchTerm, sortKey, dir])

  return (
    <div>
      <h1 className="page-title">Alerts</h1>
      <div className="filters" style={{ marginBottom: '1rem', display: 'flex', gap: '0.5rem', alignItems: 'center', justifyContent: 'space-between' }}>
        <div style={{ display: 'flex', gap: '0.5rem' }}>
          <select value={state} onChange={e => setState(e.target.value)}>
            <option value="">All states</option>
            <option value="firing">Firing</option>
            <option value="resolved">Resolved</option>
          </select>
          <select value={trigger} onChange={e => setTrigger(e.target.value)}>
            {TRIGGERS.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
          </select>
        </div>
        <SearchInput
          value={searchTerm}
          onChange={setSearchTerm}
          placeholder="Search resource…"
        />
      </div>

      {isLoading ? <TableSkeleton cols={6} /> : (
      <table className="data-table">
        <thead>
          <tr>
            <th scope="col" className="th-sortable" onClick={() => toggleSort('state')}><span>State {sortIcon('state')}</span></th>
            <th scope="col" className="th-sortable" onClick={() => toggleSort('resource')}><span>Resource {sortIcon('resource')}</span></th>
            <th scope="col" className="th-sortable" onClick={() => toggleSort('first')}><span>First fired {sortIcon('first')}</span></th>
            <th scope="col" className="th-sortable" onClick={() => toggleSort('last')}><span>Last fired {sortIcon('last')}</span></th>
            <th scope="col">Deliveries</th>
            <th scope="col"></th>
          </tr>
        </thead>
        <tbody>
          {visibleEvents.map(e => (
            <tr key={e.id}>
              <td><span className={e.state === 'firing' ? 'badge badge-red' : 'badge badge-green'}>{e.state}</span></td>
              <td>{e.resource_key}</td>
              <td>{e.first_fired_at}</td>
              <td>{e.last_fired_at}</td>
              <td>
                {e.deliveries.map((d, i) => (
                  <span key={i} title={d.error || ''} style={{ marginRight: '0.5rem' }}>
                    {d.status === 'sent' ? '✅' : '❌'} {chName(d.channel_id)}
                  </span>
                ))}
                {e.deliveries.length === 0 && <span style={{ color: 'var(--text-muted)' }}>—</span>}
              </td>
              <td>
                {e.state === 'firing' && (
                  <button className="btn-ghost btn-sm" onClick={() => ack.mutate(e.id)}>
                    <CheckCircle2 size={13} /> Ack
                  </button>
                )}
              </td>
            </tr>
          ))}
          {visibleEvents.length === 0 && (
            <tr><td colSpan={6}>
              {events.length === 0 ? (
                <EmptyState icon={Bell} title="No alerts" description="Reachability and trigger events will show up here." />
              ) : (
                <EmptyState
                  icon={Bell}
                  title="No alerts match search"
                  action={<button className="btn-ghost btn-sm" onClick={() => setSearchTerm('')}>Clear search</button>}
                />
              )}
            </td></tr>
          )}
        </tbody>
      </table>
      )}
    </div>
  )
}
