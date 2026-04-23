import { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Plus, X } from 'lucide-react'
import { subnetsApi, type Subnet } from '../api/client'

const emptyForm = { name: '', cidr: '', vlan_id: '', description: '' }

export default function Subnets() {
  const [showForm, setShowForm] = useState(false)
  const [form, setForm]         = useState(emptyForm)
  const qc = useQueryClient()

  const { data, isLoading, error } = useQuery({
    queryKey: ['subnets'],
    queryFn: subnetsApi.list,
  })

  const createMutation = useMutation({
    mutationFn: () => subnetsApi.create({
      name:        form.name,
      cidr:        form.cidr,
      vlan_id:     form.vlan_id ? Number(form.vlan_id) : null,
      description: form.description || null,
      ip_version:  4,  // derived by backend from CIDR
    }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['subnets'] })
      setForm(emptyForm)
      setShowForm(false)
    },
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => subnetsApi.delete(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['subnets'] }),
  })

  const set = (key: keyof typeof emptyForm) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(f => ({ ...f, [key]: e.target.value }))

  return (
    <div>
      <div className="page-header">
        <h1>Subnets</h1>
        <div className="page-header-actions">
          {!showForm && (
            <button className="btn-primary btn-sm" onClick={() => setShowForm(true)}>
              <Plus size={13} /> Add Subnet
            </button>
          )}
        </div>
      </div>

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
          </div>
          <div className="form-actions">
            <button
              className="btn-primary btn-sm"
              onClick={() => createMutation.mutate()}
              disabled={createMutation.isPending || !form.name || !form.cidr}
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

      {isLoading && <p className="loading">Loading…</p>}
      {error    && <p className="feedback-error">Failed to load subnets.</p>}

      {data && (
        <div className="table-wrap">
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>CIDR</th>
                <th>Version</th>
                <th>VLAN</th>
                <th>Description</th>
                <th style={{ width: '2.5rem' }}></th>
              </tr>
            </thead>
            <tbody>
              {data.length === 0 && (
                <tr><td colSpan={6} className="empty-state">No subnets defined. Add one above.</td></tr>
              )}
              {data.map((s: Subnet) => (
                <tr key={s.id}>
                  <td>{s.name}</td>
                  <td><span className="font-mono">{s.cidr}</span></td>
                  <td><span className="badge badge-blue">IPv{s.ip_version}</span></td>
                  <td>{s.vlan_id ?? <span className="text-muted">—</span>}</td>
                  <td>{s.description ?? <span className="text-muted">—</span>}</td>
                  <td>
                    <button
                      className="btn-danger btn-sm"
                      onClick={() =>
                        window.confirm(`Delete subnet "${s.name}" (${s.cidr})?`) &&
                        deleteMutation.mutate(s.id)
                      }
                      disabled={deleteMutation.isPending}
                    >
                      <X size={12} />
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
