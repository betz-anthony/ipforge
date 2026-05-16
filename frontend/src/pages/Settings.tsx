import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Save, Plus, Pencil, Trash2, Check, X } from 'lucide-react'
import { useAuth } from '../contexts/AuthContext'
import {
  settingsApi, providerConfigsApi, cacheApi, usersApi, ldapApi,
  type AppSettingsUpdate, type ProviderConfig, type ProviderConfigCreate, type UserRecord,
  type LdapSettings,
} from '../api/client'

// ── Provider field definitions ─────────────────────────────────────────────

const TRANSPORT_OPTIONS = ['ntlm', 'kerberos', 'basic', 'certificate', 'credssp']
const TSIG_ALGORITHMS   = ['hmac-sha256', 'hmac-sha512', 'hmac-sha1', 'hmac-md5']

type FieldDef = {
  key: string
  label: string
  placeholder?: string
  type?: 'text' | 'number' | 'password' | 'select' | 'textarea'
  options?: string[]
  default?: string | number
}

const PROVIDER_FIELDS: Record<string, FieldDef[]> = {
  msdns: [
    { key: 'winrm_host',      label: 'WinRM Host',   placeholder: 'dc.domain.local' },
    { key: 'winrm_user',      label: 'Username',     placeholder: 'DOMAIN\\svcaccount' },
    { key: 'winrm_password',  label: 'Password',     type: 'password' },
    { key: 'winrm_port',      label: 'WinRM Port',   type: 'number', default: 5985 },
    { key: 'winrm_transport', label: 'Transport',    type: 'select', options: TRANSPORT_OPTIONS, default: 'ntlm' },
    { key: 'dns_server',      label: 'DNS Server',   placeholder: 'dns.domain.local' },
  ],
  msdhcp: [
    { key: 'winrm_host',      label: 'WinRM Host',   placeholder: 'dc.domain.local' },
    { key: 'winrm_user',      label: 'Username',     placeholder: 'DOMAIN\\svcaccount' },
    { key: 'winrm_password',  label: 'Password',     type: 'password' },
    { key: 'winrm_port',      label: 'WinRM Port',   type: 'number', default: 5985 },
    { key: 'winrm_transport', label: 'Transport',    type: 'select', options: TRANSPORT_OPTIONS, default: 'ntlm' },
    { key: 'dhcp_server',     label: 'DHCP Server',  placeholder: 'dhcp.domain.local' },
  ],
  bind: [
    { key: 'host',            label: 'Nameserver Host',          placeholder: 'ns1.domain.local' },
    { key: 'port',            label: 'Port',                     type: 'number', default: 53 },
    { key: 'tsig_key_name',   label: 'TSIG Key Name',            placeholder: 'ipam-key' },
    { key: 'tsig_key_secret', label: 'TSIG Key Secret (base64)', type: 'password' },
    { key: 'tsig_algorithm',  label: 'TSIG Algorithm',           type: 'select', options: TSIG_ALGORITHMS, default: 'hmac-sha256' },
    { key: 'zones',           label: 'Zones (comma-separated)',  placeholder: 'example.com, 1.168.192.in-addr.arpa', type: 'textarea' },
  ],
  pihole: [
    { key: 'url',      label: 'URL',            placeholder: 'http://192.168.1.1' },
    { key: 'password', label: 'Admin Password', type: 'password' },
  ],
  keadhcp: [
    { key: 'url',    label: 'Control Agent URL',        placeholder: 'http://kea-host:8000' },
    { key: 'secret', label: 'API Secret (if auth)',     type: 'password', placeholder: 'Leave blank if none' },
  ],
}

const DNS_TYPES  = [
  { value: 'msdns',  label: 'Microsoft DNS' },
  { value: 'pihole', label: 'Pi-hole v6' },
  { value: 'bind',   label: 'BIND (dnspython)' },
]
const DHCP_TYPES = [
  { value: 'msdhcp',  label: 'Microsoft DHCP' },
  { value: 'pihole',  label: 'Pi-hole v6' },
  { value: 'keadhcp', label: 'ISC Kea' },
]

const TYPE_LABEL: Record<string, string> = Object.fromEntries(
  [...DNS_TYPES, ...DHCP_TYPES].map(t => [t.value, t.label])
)

// ── Small reusable components ──────────────────────────────────────────────

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="form-field">
      <label>{label}{hint && <span style={{ color: 'var(--accent)', marginLeft: '0.375rem', fontSize: '0.7rem' }}>{hint}</span>}</label>
      {children}
    </div>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="settings-section-title">{children}</div>
}

// ── Provider inline form ───────────────────────────────────────────────────

function ProviderForm({
  category,
  editing,
  onSave,
  onCancel,
  error,
  pending,
}: {
  category: 'dns' | 'dhcp'
  editing: ProviderConfig | null  // null = create
  onSave: (name: string, providerType: string, cfg: Record<string, unknown>) => void
  onCancel: () => void
  error?: string
  pending: boolean
}) {
  const typeOptions = category === 'dns' ? DNS_TYPES : DHCP_TYPES
  const [ptype, setPtype] = useState(editing?.provider_type ?? typeOptions[0].value)
  const [name, setName]   = useState(editing?.name ?? '')
  const [cfg, setCfg]     = useState<Record<string, unknown>>(
    (editing?.config as Record<string, unknown>) ?? {}
  )

  const fields = PROVIDER_FIELDS[ptype] ?? []

  const [showSecrets, setShowSecrets] = useState<Record<string, boolean>>({})

  function cfgVal(key: string): string {
    const v = cfg[key]
    return v !== undefined && v !== null ? String(v) : ''
  }

  function setCfgKey(key: string, value: unknown) {
    setCfg(c => ({ ...c, [key]: value }))
  }

  return (
    <div className="inline-form" style={{ marginTop: '0.75rem' }}>
      <div className="form-grid">
        {!editing && (
          <Field label="Type">
            <select value={ptype} onChange={e => { setPtype(e.target.value); setCfg({}) }}>
              {typeOptions.map(t => <option key={t.value} value={t.value}>{t.label}</option>)}
            </select>
          </Field>
        )}
        <Field label="Name / ID" hint="slug: lowercase, hyphens, underscores">
          <input
            value={name}
            onChange={e => setName(e.target.value.toLowerCase())}
            placeholder={`${ptype}-1`}
            disabled={!!editing}
          />
        </Field>
        {fields.map(f => {
          if (f.type === 'password') {
            const show = showSecrets[f.key] ?? false
            const isSet = editing?.secrets_set?.[f.key] ?? false
            return (
              <Field key={f.key} label={f.label} hint={isSet && !cfgVal(f.key) ? '● set' : undefined}>
                <div className="password-wrap">
                  <input
                    type={show ? 'text' : 'password'}
                    value={cfgVal(f.key)}
                    onChange={e => setCfgKey(f.key, e.target.value)}
                    placeholder={isSet ? 'Leave blank to keep' : (f.placeholder ?? 'Enter value')}
                  />
                  <button type="button" className="btn-ghost btn-sm" onClick={() => setShowSecrets(s => ({ ...s, [f.key]: !show }))}>
                    {show ? <EyeOff size={13} /> : <Eye size={13} />}
                  </button>
                </div>
              </Field>
            )
          }
          if (f.type === 'select') {
            return (
              <Field key={f.key} label={f.label}>
                <select value={cfgVal(f.key) || String(f.default ?? '')} onChange={e => setCfgKey(f.key, e.target.value)}>
                  {(f.options ?? []).map(o => <option key={o} value={o}>{o}</option>)}
                </select>
              </Field>
            )
          }
          if (f.type === 'textarea') {
            return (
              <Field key={f.key} label={f.label}>
                <input value={cfgVal(f.key)} onChange={e => setCfgKey(f.key, e.target.value)} placeholder={f.placeholder} />
              </Field>
            )
          }
          if (f.type === 'number') {
            return (
              <Field key={f.key} label={f.label}>
                <input
                  type="number"
                  value={cfgVal(f.key) || String(f.default ?? '')}
                  onChange={e => setCfgKey(f.key, Number(e.target.value))}
                />
              </Field>
            )
          }
          return (
            <Field key={f.key} label={f.label}>
              <input value={cfgVal(f.key)} onChange={e => setCfgKey(f.key, e.target.value)} placeholder={f.placeholder} />
            </Field>
          )
        })}
      </div>
      <div className="form-actions">
        <button
          className="btn-primary btn-sm"
          disabled={pending || !name}
          onClick={() => onSave(name, ptype, cfg)}
        >
          <Check size={13} />
          {pending ? 'Saving…' : (editing ? 'Update' : 'Add')}
        </button>
        <button className="btn-ghost btn-sm" onClick={onCancel}><X size={13} /> Cancel</button>
        {error && <span className="feedback-error">{error}</span>}
      </div>
    </div>
  )
}

// ── Provider list section ──────────────────────────────────────────────────

function ProviderSection({
  category,
  providers,
  qc,
}: {
  category: 'dns' | 'dhcp'
  providers: ProviderConfig[]
  qc: ReturnType<typeof useQueryClient>
}) {
  const [adding, setAdding]   = useState(false)
  const [editId, setEditId]   = useState<number | null>(null)
  const [mutErr, setMutErr]   = useState('')

  const invalidate = () => qc.invalidateQueries({ queryKey: ['provider-configs'] })

  const createMut = useMutation({
    mutationFn: (d: ProviderConfigCreate) => providerConfigsApi.create(d),
    onSuccess: () => { setAdding(false); setMutErr(''); invalidate() },
    onError: (e: Error) => setMutErr(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof providerConfigsApi.update>[1] }) =>
      providerConfigsApi.update(id, data),
    onSuccess: () => { setEditId(null); setMutErr(''); invalidate() },
    onError: (e: Error) => setMutErr(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => providerConfigsApi.delete(id),
    onSuccess: () => { invalidate() },
  })

  const cachePurgeMut = useMutation({
    mutationFn: ({ source }: { source: string }) =>
      cacheApi.purge(category as 'dns' | 'dhcp', source),
  })

  const toggleMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      providerConfigsApi.update(id, { enabled }),
    onSuccess: () => { invalidate() },
  })

  const mine = providers.filter(p => p.category === category)

  return (
    <div className="settings-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <SectionTitle>{category === 'dns' ? 'DNS' : 'DHCP'} Providers</SectionTitle>
        {!adding && (
          <button className="btn-ghost btn-sm" onClick={() => { setAdding(true); setEditId(null) }}>
            <Plus size={13} /> Add
          </button>
        )}
      </div>

      {mine.length === 0 && !adding && (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)', margin: '0.5rem 0' }}>
          No {category === 'dns' ? 'DNS' : 'DHCP'} providers configured.
        </p>
      )}

      {mine.map(p => (
        <div key={p.id}>
          {editId === p.id ? (
            <ProviderForm
              category={category}
              editing={p}
              pending={updateMut.isPending}
              error={mutErr}
              onCancel={() => { setEditId(null); setMutErr('') }}
              onSave={(_name, _type, cfg) =>
                updateMut.mutate({ id: p.id, data: { config: cfg } })
              }
            />
          ) : (
            <div
              style={{
                display: 'flex', alignItems: 'center', gap: '0.5rem',
                padding: '0.45rem 0.6rem', border: '1px solid var(--border)',
                borderRadius: '6px', marginBottom: '0.4rem',
                background: p.enabled ? 'var(--surface)' : 'var(--surface-2)',
                opacity: p.enabled ? 1 : 0.6,
              }}
            >
              <span className="badge badge-gray" style={{ fontSize: '0.6rem', flexShrink: 0 }}>
                {TYPE_LABEL[p.provider_type] ?? p.provider_type}
              </span>
              <span style={{ flex: 1, fontSize: '0.82rem', fontFamily: 'var(--font-mono)' }}>{p.name}</span>
              <button
                className={`btn-ghost btn-sm`}
                style={{ fontSize: '0.7rem' }}
                onClick={() => toggleMut.mutate({ id: p.id, enabled: !p.enabled })}
                title={p.enabled ? 'Disable' : 'Enable'}
              >
                {p.enabled ? 'Enabled' : 'Disabled'}
              </button>
              <button
                className="btn-ghost btn-sm"
                onClick={() => { setEditId(p.id); setAdding(false) }}
                title="Edit"
              >
                <Pencil size={12} />
              </button>
              <button
                className="btn-ghost btn-sm"
                onClick={() => window.confirm(`Clear all cached ${category.toUpperCase()} data for "${p.name}"?`) && cachePurgeMut.mutate({ source: p.name })}
                title="Clear Cache"
                style={{ fontSize: '0.65rem' }}
              >
                Clear Cache
              </button>
              <button
                className="btn-danger btn-sm"
                onClick={() => window.confirm(`Delete provider "${p.name}"?`) && deleteMut.mutate(p.id)}
                title="Delete"
              >
                <Trash2 size={12} />
              </button>
            </div>
          )}
        </div>
      ))}

      {adding && (
        <ProviderForm
          category={category}
          editing={null}
          pending={createMut.isPending}
          error={mutErr}
          onCancel={() => { setAdding(false); setMutErr('') }}
          onSave={(name, providerType, cfg) =>
            createMut.mutate({ category, provider_type: providerType, name, config: cfg })
          }
        />
      )}
    </div>
  )
}

// ── Users section ─────────────────────────────────────────────────────────

const ROLE_OPTIONS = ['readonly', 'operator', 'admin']

function UsersSection({ currentUsername }: { currentUsername: string }) {
  const qc = useQueryClient()
  const { data: users = [], isLoading } = useQuery({ queryKey: ['users'], queryFn: usersApi.list })

  const [adding, setAdding]   = useState(false)
  const [editId, setEditId]   = useState<number | null>(null)
  const [mutErr, setMutErr]   = useState('')

  const [newUsername, setNewUsername] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [newRole, setNewRole]         = useState('operator')

  const [editRole, setEditRole]         = useState('')
  const [editPassword, setEditPassword] = useState('')
  const [editEnabled, setEditEnabled]   = useState(true)

  const invalidate = () => qc.invalidateQueries({ queryKey: ['users'] })

  const createMut = useMutation({
    mutationFn: () => usersApi.create(newUsername, newPassword, newRole),
    onSuccess: () => {
      setAdding(false); setMutErr('')
      setNewUsername(''); setNewPassword(''); setNewRole('operator')
      invalidate()
    },
    onError: (e: Error) => setMutErr(e.message),
  })

  const updateMut = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Parameters<typeof usersApi.update>[1] }) =>
      usersApi.update(id, data),
    onSuccess: () => { setEditId(null); setMutErr(''); invalidate() },
    onError: (e: Error) => setMutErr(e.message),
  })

  const deleteMut = useMutation({
    mutationFn: (id: number) => usersApi.delete(id),
    onSuccess: () => { invalidate() },
  })

  function startEdit(u: UserRecord) {
    setEditId(u.id); setEditRole(u.role); setEditPassword(''); setEditEnabled(u.enabled)
    setAdding(false); setMutErr('')
  }

  if (isLoading) return null

  return (
    <div className="settings-section">
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <SectionTitle>Users</SectionTitle>
        {!adding && (
          <button className="btn-ghost btn-sm" onClick={() => { setAdding(true); setEditId(null) }}>
            <Plus size={13} /> Add
          </button>
        )}
      </div>

      {users.map(u => (
        <div key={u.id}>
          {editId === u.id ? (
            <div className="inline-form" style={{ marginTop: '0.5rem' }}>
              <div className="form-grid">
                <Field label="Role">
                  <select value={editRole} onChange={e => setEditRole(e.target.value)}>
                    {ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
                  </select>
                </Field>
                {u.auth_source !== 'ldap' && (
                  <Field label="New Password" hint="leave blank to keep">
                    <input
                      type="password"
                      value={editPassword}
                      onChange={e => setEditPassword(e.target.value)}
                      placeholder="Leave blank to keep"
                    />
                  </Field>
                )}
                {u.username !== currentUsername && (
                  <Field label="Enabled">
                    <select value={editEnabled ? 'yes' : 'no'} onChange={e => setEditEnabled(e.target.value === 'yes')}>
                      <option value="yes">Enabled</option>
                      <option value="no">Disabled</option>
                    </select>
                  </Field>
                )}
              </div>
              <div className="form-actions">
                <button
                  className="btn-primary btn-sm"
                  disabled={updateMut.isPending}
                  onClick={() => {
                    const data: Parameters<typeof usersApi.update>[1] = { role: editRole, enabled: editEnabled }
                    if (editPassword && u.auth_source !== 'ldap') data.password = editPassword
                    updateMut.mutate({ id: u.id, data })
                  }}
                >
                  <Check size={13} />
                  {updateMut.isPending ? 'Saving…' : 'Update'}
                </button>
                <button className="btn-ghost btn-sm" onClick={() => { setEditId(null); setMutErr('') }}>
                  <X size={13} /> Cancel
                </button>
                {mutErr && <span className="feedback-error">{mutErr}</span>}
              </div>
            </div>
          ) : (
            <div style={{
              display: 'flex', alignItems: 'center', gap: '0.5rem',
              padding: '0.45rem 0.6rem', border: '1px solid var(--border)',
              borderRadius: '6px', marginBottom: '0.4rem',
              background: u.enabled ? 'var(--surface)' : 'var(--surface-2)',
              opacity: u.enabled ? 1 : 0.6,
            }}>
              <span style={{ flex: 1, fontSize: '0.82rem', fontFamily: 'var(--font-mono)' }}>{u.username}</span>
              <span className="badge badge-gray" style={{ fontSize: '0.6rem' }}>{u.role}</span>
              {u.auth_source === 'ldap' && (
                <span className="badge badge-blue" style={{ fontSize: '0.6rem' }}>ldap</span>
              )}
              {!u.enabled && (
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)' }}>disabled</span>
              )}
              <button className="btn-ghost btn-sm" onClick={() => startEdit(u)} title="Edit">
                <Pencil size={12} />
              </button>
              {u.username !== currentUsername && (
                <button
                  className="btn-danger btn-sm"
                  onClick={() => window.confirm(`Delete user "${u.username}"?`) && deleteMut.mutate(u.id)}
                  title="Delete"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </div>
          )}
        </div>
      ))}

      {adding && (
        <div className="inline-form" style={{ marginTop: '0.75rem' }}>
          <div className="form-grid">
            <Field label="Username">
              <input value={newUsername} onChange={e => setNewUsername(e.target.value)} placeholder="username" />
            </Field>
            <Field label="Password">
              <input type="password" value={newPassword} onChange={e => setNewPassword(e.target.value)} placeholder="Min 8 characters" />
            </Field>
            <Field label="Role">
              <select value={newRole} onChange={e => setNewRole(e.target.value)}>
                {ROLE_OPTIONS.map(r => <option key={r} value={r}>{r}</option>)}
              </select>
            </Field>
          </div>
          <div className="form-actions">
            <button
              className="btn-primary btn-sm"
              disabled={createMut.isPending || !newUsername || !newPassword}
              onClick={() => createMut.mutate()}
            >
              <Check size={13} />
              {createMut.isPending ? 'Adding…' : 'Add User'}
            </button>
            <button className="btn-ghost btn-sm" onClick={() => { setAdding(false); setMutErr('') }}>
              <X size={13} /> Cancel
            </button>
            {mutErr && <span className="feedback-error">{mutErr}</span>}
          </div>
        </div>
      )}
    </div>
  )
}

// ── LDAP settings section ──────────────────────────────────────────────────

function LdapSection() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['ldap-settings'], queryFn: ldapApi.get })

  const defaults: LdapSettings = {
    ldap_enabled: false,
    ldap_host: '', ldap_port: 389, ldap_use_ssl: false,
    ldap_bind_dn: '', ldap_bind_password: '', ldap_base_dn: '',
    ldap_user_filter: '(sAMAccountName={username})',
    ldap_group_admin: '', ldap_group_operator: '', ldap_group_readonly: '',
    ldap_default_role: 'readonly',
  }
  const [form, setForm] = useState<LdapSettings>(defaults)
  const [showPass, setShowPass] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (data) setForm({ ...data, ldap_bind_password: '' })
  }, [data])

  const mutation = useMutation({
    mutationFn: () => {
      const payload: Partial<LdapSettings> = { ...form }
      if (!payload.ldap_bind_password) delete payload.ldap_bind_password
      return ldapApi.update(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['ldap-settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const set = (key: keyof LdapSettings) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
      const val = e.target.type === 'checkbox'
        ? (e.target as HTMLInputElement).checked
        : e.target.type === 'number' ? Number(e.target.value) : e.target.value
      setForm(f => ({ ...f, [key]: val }))
    }

  if (isLoading) return null

  return (
    <div className="settings-section">
      <SectionTitle>LDAP / Active Directory</SectionTitle>
      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }}>
        <div className="form-grid">
          <Field label="Enable LDAP">
            <select value={form.ldap_enabled ? 'yes' : 'no'}
              onChange={e => setForm(f => ({ ...f, ldap_enabled: e.target.value === 'yes' }))}>
              <option value="no">Disabled</option>
              <option value="yes">Enabled</option>
            </select>
          </Field>
          <Field label="LDAP Host">
            <input value={form.ldap_host} onChange={set('ldap_host')} placeholder="ldap.example.com" />
          </Field>
          <Field label="Port">
            <input type="number" value={form.ldap_port} onChange={set('ldap_port')} />
          </Field>
          <Field label="Use SSL (LDAPS)">
            <select value={form.ldap_use_ssl ? 'yes' : 'no'}
              onChange={e => setForm(f => ({ ...f, ldap_use_ssl: e.target.value === 'yes' }))}>
              <option value="no">No</option>
              <option value="yes">Yes</option>
            </select>
          </Field>
          <Field label="Bind DN">
            <input value={form.ldap_bind_dn} onChange={set('ldap_bind_dn')}
              placeholder="cn=svc-ipam,dc=example,dc=com" />
          </Field>
          <Field label="Bind Password" hint="leave blank to keep existing">
            <div className="password-wrap">
              <input
                type={showPass ? 'text' : 'password'}
                value={form.ldap_bind_password}
                onChange={set('ldap_bind_password')}
                placeholder="Leave blank to keep"
              />
              <button type="button" className="btn-ghost btn-sm"
                onClick={() => setShowPass(s => !s)}>
                {showPass ? <EyeOff size={13} /> : <Eye size={13} />}
              </button>
            </div>
          </Field>
          <Field label="Base DN">
            <input value={form.ldap_base_dn} onChange={set('ldap_base_dn')}
              placeholder="dc=example,dc=com" />
          </Field>
          <Field label="User Filter" hint="{username} replaced at runtime">
            <input value={form.ldap_user_filter} onChange={set('ldap_user_filter')}
              placeholder="(sAMAccountName={username})" />
          </Field>
          <Field label="Admin Group DN" hint="optional">
            <input value={form.ldap_group_admin} onChange={set('ldap_group_admin')}
              placeholder="CN=IPAM-Admins,dc=example,dc=com" />
          </Field>
          <Field label="Operator Group DN" hint="optional">
            <input value={form.ldap_group_operator} onChange={set('ldap_group_operator')}
              placeholder="CN=IPAM-Ops,dc=example,dc=com" />
          </Field>
          <Field label="Readonly Group DN" hint="optional">
            <input value={form.ldap_group_readonly} onChange={set('ldap_group_readonly')}
              placeholder="CN=IPAM-RO,dc=example,dc=com" />
          </Field>
          <Field label="Default Role" hint="when no group match">
            <select value={form.ldap_default_role}
              onChange={e => setForm(f => ({ ...f, ldap_default_role: e.target.value }))}>
              <option value="readonly">readonly</option>
              <option value="operator">operator</option>
              <option value="admin">admin</option>
            </select>
          </Field>
        </div>
        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            <Save size={13} />
            {mutation.isPending ? 'Saving…' : 'Save LDAP Settings'}
          </button>
          {saved && <span className="feedback-success">Saved.</span>}
          {mutation.isError && (
            <span className="feedback-error">{String((mutation.error as Error).message)}</span>
          )}
        </div>
      </form>
    </div>
  )
}

// ── Main settings page ─────────────────────────────────────────────────────

export default function SettingsPage() {
  const qc = useQueryClient()
  const { user } = useAuth()
  const { data: settingsData, isLoading } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })
  const { data: providerConfigs = [] } = useQuery({ queryKey: ['provider-configs'], queryFn: providerConfigsApi.list })

  const [form, setForm] = useState<AppSettingsUpdate>({
    util_warn_threshold:     80,
    util_critical_threshold: 95,
    util_dashboard_top_n:    5,
    scan_interval_minutes:   30,
    stale_reclaim_days:      30,
  })
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!settingsData) return
    setForm({
      util_warn_threshold:     settingsData.util_warn_threshold,
      util_critical_threshold: settingsData.util_critical_threshold,
      util_dashboard_top_n:    settingsData.util_dashboard_top_n,
      scan_interval_minutes:   settingsData.scan_interval_minutes,
      stale_reclaim_days:      settingsData.stale_reclaim_days,
    })
  }, [settingsData])

  const mutation = useMutation({
    mutationFn: () => settingsApi.update(form),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const s = (key: keyof AppSettingsUpdate) =>
    (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm(f => ({ ...f, [key]: Number(e.target.value) }))

  if (isLoading) return <p className="loading">Loading…</p>

  return (
    <div style={{ maxWidth: '760px' }}>
      <div className="page-header"><h1>Settings</h1></div>

      {/* ── Providers ── */}
      <ProviderSection category="dns"  providers={providerConfigs} qc={qc} />
      <ProviderSection category="dhcp" providers={providerConfigs} qc={qc} />

      {/* ── LDAP ── */}
      <LdapSection />

      {/* ── Utilization ── */}
      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }}>
        <div className="settings-section">
          <SectionTitle>Utilization Thresholds</SectionTitle>
          <div className="form-grid">
            <Field label="Warn threshold (%)" hint="default 80">
              <input type="number" min={1} max={99} value={form.util_warn_threshold ?? 80} onChange={s('util_warn_threshold')} />
            </Field>
            <Field label="Critical threshold (%)" hint="default 95">
              <input type="number" min={1} max={100} value={form.util_critical_threshold ?? 95} onChange={s('util_critical_threshold')} />
            </Field>
            <Field label="Dashboard top N subnets" hint="default 5">
              <input type="number" min={1} max={20} value={form.util_dashboard_top_n ?? 5} onChange={s('util_dashboard_top_n')} />
            </Field>
            <Field label="Default scan interval (min)" hint="default 30">
              <input
                type="number"
                min={1}
                value={form.scan_interval_minutes ?? 30}
                onChange={s('scan_interval_minutes')}
              />
            </Field>
            <Field label="Stale Reclaim Threshold (days)" hint="0 = disabled, default 30">
              <input
                type="number"
                min={0}
                value={form.stale_reclaim_days ?? 30}
                onChange={s('stale_reclaim_days')}
              />
            </Field>
          </div>
        </div>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            <Save size={13} />
            {mutation.isPending ? 'Saving…' : 'Save Settings'}
          </button>
          {saved && <span className="feedback-success">Saved.</span>}
          {mutation.isError && (
            <span className="feedback-error">{String((mutation.error as Error).message)}</span>
          )}
        </div>
      </form>

      {/* ── Users ── */}
      {user && <UsersSection currentUsername={user.username} />}
    </div>
  )
}
