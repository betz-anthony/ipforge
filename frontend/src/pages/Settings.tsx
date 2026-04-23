import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { settingsApi, type AppSettingsUpdate } from '../api/client'

const TRANSPORT_OPTIONS = ['ntlm', 'kerberos', 'basic', 'certificate', 'credssp']

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '4px' }}>
      <label style={{ fontSize: '0.85rem', fontWeight: 600, color: '#444' }}>{label}</label>
      {children}
    </div>
  )
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <section style={{ marginBottom: '2rem' }}>
      <h2 style={{
        fontSize: '0.8rem', textTransform: 'uppercase', letterSpacing: '0.06em',
        color: '#888', marginBottom: '0.75rem', borderBottom: '1px solid #e0e0e0', paddingBottom: '0.4rem',
      }}>
        {title}
      </h2>
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(260px, 1fr))', gap: '0.75rem' }}>
        {children}
      </div>
    </section>
  )
}

export default function Settings() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })

  const [form, setForm] = useState<AppSettingsUpdate & { _password: string }>({
    dns_provider: '',
    dhcp_provider: '',
    ms_winrm_host: '',
    ms_winrm_user: '',
    _password: '',
    ms_winrm_port: 5985,
    ms_winrm_transport: 'ntlm',
    ms_dns_server: '',
    ms_dhcp_server: '',
  })
  const [showPassword, setShowPassword] = useState(false)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (data) {
      setForm(f => ({
        ...f,
        dns_provider: data.dns_provider,
        dhcp_provider: data.dhcp_provider,
        ms_winrm_host: data.ms_winrm_host,
        ms_winrm_user: data.ms_winrm_user,
        ms_winrm_port: data.ms_winrm_port,
        ms_winrm_transport: data.ms_winrm_transport,
        ms_dns_server: data.ms_dns_server,
        ms_dhcp_server: data.ms_dhcp_server,
      }))
    }
  }, [data])

  const mutation = useMutation({
    mutationFn: () => {
      const payload: AppSettingsUpdate = {
        dns_provider: form.dns_provider,
        dhcp_provider: form.dhcp_provider,
        ms_winrm_host: form.ms_winrm_host,
        ms_winrm_user: form.ms_winrm_user,
        ms_winrm_port: form.ms_winrm_port,
        ms_winrm_transport: form.ms_winrm_transport,
        ms_dns_server: form.ms_dns_server,
        ms_dhcp_server: form.ms_dhcp_server,
      }
      if (form._password) payload.ms_winrm_password = form._password
      return settingsApi.update(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      setForm(f => ({ ...f, _password: '' }))
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const set = (key: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
    setForm(f => ({ ...f, [key]: key === 'ms_winrm_port' ? Number(e.target.value) : e.target.value }))

  if (isLoading) return <p>Loading…</p>

  return (
    <div style={{ maxWidth: '800px' }}>
      <h1>Settings</h1>

      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }}>

        <Section title="WinRM Connection">
          <Field label="Host">
            <input value={form.ms_winrm_host ?? ''} onChange={set('ms_winrm_host')} placeholder="dc.domain.local" />
          </Field>
          <Field label="Username">
            <input value={form.ms_winrm_user ?? ''} onChange={set('ms_winrm_user')} placeholder="DOMAIN\svcaccount" />
          </Field>
          <Field label={`Password${data?.ms_winrm_password_set ? ' (set — leave blank to keep)' : ''}`}>
            <div style={{ display: 'flex', gap: '4px' }}>
              <input
                type={showPassword ? 'text' : 'password'}
                value={form._password}
                onChange={e => setForm(f => ({ ...f, _password: e.target.value }))}
                placeholder={data?.ms_winrm_password_set ? '••••••••' : 'Enter password'}
                style={{ flex: 1 }}
              />
              <button type="button" onClick={() => setShowPassword(s => !s)} style={{ whiteSpace: 'nowrap' }}>
                {showPassword ? 'Hide' : 'Show'}
              </button>
            </div>
          </Field>
          <Field label="Port">
            <input type="number" value={form.ms_winrm_port ?? 5985} onChange={set('ms_winrm_port')} />
          </Field>
          <Field label="Transport">
            <select value={form.ms_winrm_transport ?? 'ntlm'} onChange={set('ms_winrm_transport')}>
              {TRANSPORT_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
            </select>
          </Field>
        </Section>

        <Section title="DNS">
          <Field label="Provider">
            <select value={form.dns_provider ?? 'msdns'} onChange={set('dns_provider')}>
              <option value="msdns">msdns (Microsoft DNS)</option>
            </select>
          </Field>
          <Field label="DNS Server">
            <input value={form.ms_dns_server ?? ''} onChange={set('ms_dns_server')} placeholder="dns.domain.local" />
          </Field>
        </Section>

        <Section title="DHCP">
          <Field label="Provider">
            <select value={form.dhcp_provider ?? 'msdhcp'} onChange={set('dhcp_provider')}>
              <option value="msdhcp">msdhcp (Microsoft DHCP)</option>
            </select>
          </Field>
          <Field label="DHCP Server">
            <input value={form.ms_dhcp_server ?? ''} onChange={set('ms_dhcp_server')} placeholder="dhcp.domain.local" />
          </Field>
        </Section>

        <div style={{ display: 'flex', alignItems: 'center', gap: '1rem' }}>
          <button type="submit" disabled={mutation.isPending}>
            {mutation.isPending ? 'Saving…' : 'Save Settings'}
          </button>
          {saved && <span style={{ color: 'green', fontSize: '0.9rem' }}>Saved.</span>}
          {mutation.isError && (
            <span style={{ color: 'red', fontSize: '0.9rem' }}>
              Error: {String((mutation.error as Error).message)}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
