import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, Trash2, X } from 'lucide-react'
import { groupsApi, usersApi } from '../api/client'
import ConfirmModal from '../components/ConfirmModal'
import { useToast } from '../contexts/ToastContext'

export default function Groups() {
  const qc = useQueryClient()
  const { showToast } = useToast()
  const [showForm, setShowForm]   = useState(false)
  const [name, setName]           = useState('')
  const [description, setDescription] = useState('')
  const [confirmId, setConfirmId] = useState<number | null>(null)
  const [expandedId, setExpandedId] = useState<number | null>(null)
  const [addUserId, setAddUserId] = useState('')

  const { data: groups } = useQuery({ queryKey: ['groups'], queryFn: groupsApi.list })
  const { data: users }  = useQuery({ queryKey: ['users'], queryFn: usersApi.list })
  const { data: members } = useQuery({
    queryKey: ['group-members', expandedId],
    queryFn: () => groupsApi.members(expandedId!),
    enabled: expandedId !== null,
  })

  const createMut = useMutation({
    mutationFn: () => groupsApi.create({ name, description: description || null }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['groups'] })
      setShowForm(false); setName(''); setDescription('')
    },
  })
  const deleteMut = useMutation({
    mutationFn: (id: number) => groupsApi.remove(id),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['groups'] })
      setConfirmId(null)
      showToast('Group deleted', 'success')
    },
  })
  const addMemberMut = useMutation({
    mutationFn: (id: number) => groupsApi.addMember(id, Number(addUserId)),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['group-members', expandedId] })
      setAddUserId('')
    },
  })
  const removeMemberMut = useMutation({
    mutationFn: ({ gid, uid }: { gid: number; uid: number }) =>
      groupsApi.removeMember(gid, uid),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['group-members', expandedId] }),
  })

  return (
    <div>
      <div className="page-header">
        <h1>Groups</h1>
        {!showForm && (
          <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
            <Plus size={13} /> New Group
          </button>
        )}
      </div>

      {showForm && (
        <div className="inline-form">
          <div className="form-grid">
            <div className="form-field">
              <label htmlFor="group-name">Name</label>
              <input id="group-name" value={name} onChange={e => setName(e.target.value)} />
            </div>
            <div className="form-field">
              <label htmlFor="group-desc">Description</label>
              <input id="group-desc" value={description}
                     onChange={e => setDescription(e.target.value)} />
            </div>
          </div>
          <div className="form-actions">
            <button className="btn-primary btn-sm" disabled={createMut.isPending || !name.trim()}
                    onClick={() => createMut.mutate()}>
              {createMut.isPending ? 'Creating…' : 'Create'}
            </button>
            <button className="btn-ghost btn-sm"
                    onClick={() => { setShowForm(false); setName(''); setDescription('') }}>
              <X size={13} /> Cancel
            </button>
          </div>
        </div>
      )}

      <div className="table-wrap">
        <table>
          <thead>
            <tr><th scope="col">Name</th><th scope="col">Description</th><th scope="col">Members</th><th scope="col" style={{ width: '2.5rem' }}></th></tr>
          </thead>
          <tbody>
            {(groups ?? []).length === 0 && (
              <tr><td colSpan={4} className="empty-state">No groups.</td></tr>
            )}
            {(groups ?? []).map(g => (
              <tr key={g.id}>
                <td>{g.name}</td>
                <td><span className="text-muted">{g.description ?? '—'}</span></td>
                <td>
                  <button className="btn-ghost btn-sm"
                          onClick={() => setExpandedId(expandedId === g.id ? null : g.id)}>
                    {expandedId === g.id ? 'Hide' : 'Manage'}
                  </button>
                </td>
                <td>
                  <button className="btn-danger btn-sm" aria-label={`Delete group ${g.name}`}
                          onClick={() => setConfirmId(g.id)}>
                    <Trash2 size={12} />
                  </button>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {expandedId !== null && (
        <div className="inline-form" style={{ marginTop: '1rem' }}>
          <div className="section-label">Members</div>
          {(members ?? []).map(m => (
            <div key={m.id} style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <span style={{ flex: 1 }}>{m.username} <span className="text-muted">({m.role})</span></span>
              <button className="btn-ghost btn-sm" aria-label={`Remove ${m.username}`}
                      onClick={() => removeMemberMut.mutate({ gid: expandedId, uid: m.id })}>
                <X size={12} />
              </button>
            </div>
          ))}
          {(members ?? []).length === 0 && <div className="text-muted">No members.</div>}
          <div className="form-actions">
            <select value={addUserId} onChange={e => setAddUserId(e.target.value)}>
              <option value="">Select user…</option>
              {(users ?? []).map(u => <option key={u.id} value={u.id}>{u.username}</option>)}
            </select>
            <button className="btn-primary btn-sm" disabled={!addUserId}
                    onClick={() => addMemberMut.mutate(expandedId)}>
              Add member
            </button>
          </div>
        </div>
      )}

      {confirmId !== null && (
        <ConfirmModal
          title="Delete group"
          message="Delete this group? Its grants and memberships are removed."
          onConfirm={() => deleteMut.mutate(confirmId)}
          onCancel={() => setConfirmId(null)}
        />
      )}
    </div>
  )
}
