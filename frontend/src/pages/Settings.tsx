import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Save } from 'lucide-react'
import { settingsApi, type AppSettingsUpdate } from '../api/client'

const TRANSPORT_OPTIONS = ['ntlm', 'kerberos', 'basic', 'certificate', 'credssp']

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })

  const [form, setForm] = useState<AppSettingsUpdate & { _password: string }>({
    dns_provider:       'msdns',
    dhcp_provider:      'msdhcp',
    ms_winrm_host:      '',
    ms_winrm_user:      '',
    _password:          '',
    ms_winrm_port:      5985,
    ms_winrm_transport: 'ntlm',
    ms_dns_server:      '',
    ms_dhcp_server:     '',
  })
  const [showPw, setShowPw] = useState(false)
  const [saved, setSaved]   = useState(false)

  useEffect(() => {
    if (data) setForm(f => ({
      ...f,
      dns_provider:       data.dns_provider,
      dhcp_provider:      data.dhcp_provider,
      ms_winrm_host:      data.ms_winrm_host,
      ms_winrm_user:      data.ms_winrm_user,
      ms_winrm_port:      data.ms_winrm_port,
      ms_winrm_transport: data.ms_winrm_transport,
      ms_dns_server:      data.ms_dns_server,
      ms_dhcp_server:     data.ms_dhcp_server,
    }))
  }, [data])

  const mutation = useMutation({
    mutationFn: () => {
      const payload: AppSettingsUpdate = {
        dns_provider:       form.dns_provider,
        dhcp_provider:      form.dhcp_provider,
        ms_winrm_host:      form.ms_winrm_host,
        ms_winrm_user:      form.ms_winrm_user,
        ms_winrm_port:      form.ms_winrm_port,
        ms_winrm_transport: form.ms_winrm_transport,
        ms_dns_server:      form.ms_dns_server,
        ms_dhcp_server:     form.ms_dhcp_server,
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

  const set = (key: keyof typeof form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: key === 'ms_winrm_port' ? Number(e.target.value) : e.target.value }))

  if (isLoading) return <p className="loading">Loading…</p>

  return (
    <div style={{ maxWidth: '720px' }}>
      <div className="page-header">
        <h1>Settings</h1>
      </div>

      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }}>

        <div className="settings-section">
          <div className="settings-section-title">WinRM Connection</div>
          <div className="form-grid">
            <div className="form-field">
              <label>Host</label>
              <input value={form.ms_winrm_host ?? ''} onChange={set('ms_winrm_host')} placeholder="dc.domain.local" />
            </div>
            <div className="form-field">
              <label>Username</label>
              <input value={form.ms_winrm_user ?? ''} onChange={set('ms_winrm_user')} placeholder="DOMAIN\svcaccount" />
            </div>
            <div className="form-field">
              <label>
                Password{data?.ms_winrm_password_set
                  ? <span style={{ color: 'var(--accent)', marginLeft: '0.375rem', fontSize: '0.7rem' }}>● set</span>
                  : null}
              </label>
              <div className="password-wrap">
                <input
                  type={showPw ? 'text' : 'password'}
                  value={form._password}
                  onChange={e => setForm(f => ({ ...f, _password: e.target.value }))}
                  placeholder={data?.ms_winrm_password_set ? 'Leave blank to keep' : 'Enter password'}
                />
                <button type="button" className="btn-ghost btn-sm" onClick={() => setShowPw(s => !s)}>
                  {showPw ? <EyeOff size={13} /> : <Eye size={13} />}
                </button>
              </div>
            </div>
            <div className="form-field">
              <label>Port</label>
              <input type="number" value={form.ms_winrm_port ?? 5985} onChange={set('ms_winrm_port')} />
            </div>
            <div className="form-field">
              <label>Transport</label>
              <select value={form.ms_winrm_transport ?? 'ntlm'} onChange={set('ms_winrm_transport')}>
                {TRANSPORT_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
              </select>
            </div>
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">DNS</div>
          <div className="form-grid">
            <div className="form-field">
              <label>Provider</label>
              <select value={form.dns_provider ?? 'msdns'} onChange={set('dns_provider')}>
                <option value="msdns">msdns — Microsoft DNS</option>
              </select>
            </div>
            <div className="form-field">
              <label>DNS Server</label>
              <input value={form.ms_dns_server ?? ''} onChange={set('ms_dns_server')} placeholder="dns.domain.local" />
            </div>
          </div>
        </div>

        <div className="settings-section">
          <div className="settings-section-title">DHCP</div>
          <div className="form-grid">
            <div className="form-field">
              <label>Provider</label>
              <select value={form.dhcp_provider ?? 'msdhcp'} onChange={set('dhcp_provider')}>
                <option value="msdhcp">msdhcp — Microsoft DHCP</option>
              </select>
            </div>
            <div className="form-field">
              <label>DHCP Server</label>
              <input value={form.ms_dhcp_server ?? ''} onChange={set('ms_dhcp_server')} placeholder="dhcp.domain.local" />
            </div>
          </div>
        </div>

        <div className="form-actions">
          <button type="submit" className="btn-primary" disabled={mutation.isPending}>
            <Save size={13} />
            {mutation.isPending ? 'Saving…' : 'Save Settings'}
          </button>
          {saved && <span className="feedback-success">Saved.</span>}
          {mutation.isError && (
            <span className="feedback-error">
              {String((mutation.error as Error).message)}
            </span>
          )}
        </div>
      </form>
    </div>
  )
}
