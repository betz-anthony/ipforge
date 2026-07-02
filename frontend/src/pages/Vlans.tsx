import { useState, useMemo } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Pencil, Trash2, Check, X } from 'lucide-react'
import { vlansApi, type Vlan, type VlanIn } from '../api/client'
import { useAuth } from '../contexts/AuthContext'
import { useToast } from '../contexts/ToastContext'
import ConfirmModal from '../components/ConfirmModal'
import SearchInput from '../components/SearchInput'
import { TableSkeleton } from '../components/Skeleton'
import { useTableSort } from '../hooks/useTableSort'

const emptyForm: VlanIn = { vlan_id: 1, name: '', description: '', notes: '' }

export default function Vlans() {
  const { user } = useAuth()
  const { showToast } = useToast()
  const qc = useQueryClient()
  const canWrite = user?.role === 'admin' || user?.role === 'operator'

  const { data: vlans = [], isLoading, error } = useQuery({
    queryKey: ['vlans'],
    queryFn: vlansApi.list,
  })

  const [showForm, setShowForm]     = useState(false)
  const [editId, setEditId]         = useState<number | null>(null)
  const [form, setForm]             = useState<VlanIn>(emptyForm)
  const [vlanIdError, setVlanIdErr] = useState('')
  const [mutErr, setMutErr]         = useState('')
  const [confirmDelete, setConfirmDelete] = useState<Vlan | null>(null)

  const createMut = useMutation({
    mutationFn: () => vlansApi.create({
      vlan_id: Number(form.vlan_id),
      name: form.name,
      description: form.description || null,
      notes: form.notes || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vlans'] })
      setShowForm(false); setForm(emptyForm); setMutErr('')
      showToast('VLAN created', 'success')
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setMutErr(d ?? 'Create failed')
    },
  })

  const updateMut = useMutation({
    mutationFn: ({ id }: { id: number }) => vlansApi.update(id, {
      vlan_id: Number(form.vlan_id),
      name: form.name,
      description: form.description || null,
      notes: form.notes || null,
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vlans'] })
      setEditId(null); setForm(emptyForm); setMutErr('')
      showToast('VLAN updated', 'success')
    },
    onError: (e: unknown) => {
      const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail
      setMutErr(d ?? 'Update failed')
    },
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => vlansApi.delete(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['vlans'] })
      setConfirmDelete(null)
      showToast('VLAN deleted', 'success')
    },
    onError: () => { setConfirmDelete(null); showToast('Delete failed', 'error') },
  })

  const [searchTerm, setSearchTerm] = useState('')
  const { sortKey, toggleSort, sortIcon, dir } = useTableSort<
    'vlan_id' | 'name' | 'description' | 'subnet_count'
  >('vlan_id')

  const visibleVlans = useMemo(() => {
    const q = searchTerm.trim().toLowerCase()
    const filtered = q
      ? vlans.filter(v =>
          String(v.vlan_id).includes(q) ||
          v.name.toLowerCase().includes(q) ||
          (v.description ?? '').toLowerCase().includes(q)
        )
      : vlans.slice()
    const cmp = (a: Vlan, b: Vlan) => {
      switch (sortKey) {
        case 'vlan_id':      return (a.vlan_id - b.vlan_id) * dir
        case 'name':         return a.name.localeCompare(b.name) * dir
        case 'description':  return (a.description ?? '').localeCompare(b.description ?? '') * dir
        case 'subnet_count': return (a.subnet_count - b.subnet_count) * dir
      }
    }
    return filtered.sort(cmp)
  }, [vlans, searchTerm, sortKey, dir])

  const startEdit = (v: Vlan) => {
    setEditId(v.id); setShowForm(false)
    setForm({ vlan_id: v.vlan_id, name: v.name, description: v.description ?? '', notes: v.notes ?? '' })
    setMutErr(''); setVlanIdErr('')
  }

  const validateVlanId = (n: number) =>
    Number.isInteger(n) && n >= 1 && n <= 4094 ? '' : 'VLAN ID must be 1–4094'

  const formInvalid =
    !form.name.trim() ||
    !!validateVlanId(Number(form.vlan_id))

  return (
    <div>
      <div className="page-header">
        <h1>VLANs</h1>
        {canWrite && !showForm && editId === null && (
          <button className="btn-primary btn-sm" onClick={() => {
            setShowForm(true); setForm(emptyForm); setMutErr(''); setVlanIdErr('')
          }}>
            <Plus size={13} /> Add VLAN
          </button>
        )}
      </div>

      {(showForm || editId !== null) && (
        <div className="inline-form">
          <div className="form-grid">
            <div className={`form-field${vlanIdError ? ' form-field-error' : ''}`}>
              <label htmlFor="vlan-id">VLAN ID (1–4094)</label>
              <input
                id="vlan-id"
                type="number"
                min={1}
                max={4094}
                value={form.vlan_id}
                onChange={e => { setForm(f => ({ ...f, vlan_id: Number(e.target.value) })); if (vlanIdError) setVlanIdErr('') }}
                onBlur={() => setVlanIdErr(validateVlanId(Number(form.vlan_id)))}
                autoFocus
              />
              {vlanIdError && <span className="form-field-error-msg">{vlanIdError}</span>}
            </div>
            <div className="form-field">
              <label htmlFor="vlan-name">Name</label>
              <input
                id="vlan-name"
                placeholder="Production"
                value={form.name}
                onChange={e => setForm(f => ({ ...f, name: e.target.value }))}
              />
            </div>
            <div className="form-field" style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="vlan-desc">Description</label>
              <input
                id="vlan-desc"
                placeholder="Optional"
                value={form.description ?? ''}
                onChange={e => setForm(f => ({ ...f, description: e.target.value }))}
              />
            </div>
            <div className="form-field" style={{ gridColumn: '1 / -1' }}>
              <label htmlFor="vlan-notes">Notes</label>
              <textarea
                id="vlan-notes"
                value={form.notes ?? ''}
                onChange={e => setForm(f => ({ ...f, notes: e.target.value }))}
                rows={3}
                style={{ resize: 'vertical', width: '100%' }}
              />
            </div>
          </div>
          <div className="form-actions">
            <button
              className="btn-primary btn-sm"
              disabled={formInvalid || createMut.isPending || updateMut.isPending}
              onClick={() => editId !== null ? updateMut.mutate({ id: editId }) : createMut.mutate()}
            >
              <Check size={13} />
              {editId !== null
                ? (updateMut.isPending ? 'Saving…' : 'Update')
                : (createMut.isPending ? 'Adding…' : 'Add')}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => {
              setShowForm(false); setEditId(null); setForm(emptyForm); setMutErr('')
            }}>
              <X size={13} /> Cancel
            </button>
            {mutErr && <span className="feedback-error">{mutErr}</span>}
          </div>
        </div>
      )}

      <div style={{ display: 'flex', justifyContent: 'flex-end', marginBottom: '0.5rem' }}>
        <SearchInput
          value={searchTerm}
          onChange={setSearchTerm}
          placeholder="Search VLAN ID, name…"
        />
      </div>

      {isLoading && <TableSkeleton cols={5} />}
      {error    && <p className="feedback-error">Failed to load VLANs.</p>}

      {!isLoading && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('vlan_id')}><span>VLAN ID {sortIcon('vlan_id')}</span></th>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('name')}><span>Name {sortIcon('name')}</span></th>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('description')}><span>Description {sortIcon('description')}</span></th>
                <th scope="col" className="th-sortable" onClick={() => toggleSort('subnet_count')}><span>Subnets {sortIcon('subnet_count')}</span></th>
                <th scope="col" style={{ width: canWrite ? '6rem' : 0 }}></th>
              </tr>
            </thead>
            <tbody>
              {visibleVlans.length === 0 && (
                <tr><td colSpan={5} className="empty-state">
                  {vlans.length === 0 ? 'No VLANs defined. Add one above.' : 'No VLANs match search.'}
                </td></tr>
              )}
              {visibleVlans.map(v => (
                <tr key={v.id}>
                  <td><span className="font-mono">{v.vlan_id}</span></td>
                  <td>{v.name}</td>
                  <td>{v.description ?? <span className="text-muted">—</span>}</td>
                  <td>{v.subnet_count}</td>
                  <td style={{ display: 'flex', gap: '0.3rem', justifyContent: 'flex-end' }}>
                    {canWrite && (
                      <>
                        <button className="btn-ghost btn-sm" onClick={() => startEdit(v)} title="Edit">
                          <Pencil size={12} />
                        </button>
                        <button
                          className="btn-danger btn-sm"
                          disabled={v.subnet_count > 0}
                          title={v.subnet_count > 0 ? 'VLAN in use by subnets — remove association first' : 'Delete VLAN'}
                          onClick={() => setConfirmDelete(v)}
                        >
                          <Trash2 size={12} />
                        </button>
                      </>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {confirmDelete && (
        <ConfirmModal
          title="Delete VLAN"
          message={`Delete VLAN ${confirmDelete.vlan_id} (${confirmDelete.name})?`}
          onConfirm={() => deleteMut.mutate(confirmDelete.id)}
          onCancel={() => setConfirmDelete(null)}
        />
      )}
    </div>
  )
}
