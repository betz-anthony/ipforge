import { useEffect, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { Eye, EyeOff, Save } from 'lucide-react'
import { settingsApi, type AppSettingsUpdate } from '../api/client'

const TRANSPORT_OPTIONS = ['ntlm', 'kerberos', 'basic', 'certificate', 'credssp']
const TSIG_ALGORITHMS   = ['hmac-sha256', 'hmac-sha512', 'hmac-sha1', 'hmac-md5']

const DNS_OPTIONS  = [
  { value: 'msdns',  label: 'Microsoft DNS' },
  { value: 'pihole', label: 'Pi-hole v6' },
  { value: 'bind',   label: 'BIND (dnspython)' },
]
const DHCP_OPTIONS = [
  { value: 'msdhcp',  label: 'Microsoft DHCP' },
  { value: 'pihole',  label: 'Pi-hole v6' },
  { value: 'keadhcp', label: 'ISC Kea' },
]

function toggleProvider(current: string, value: string): string {
  const parts = current.split(',').map(s => s.trim()).filter(Boolean)
  const idx = parts.indexOf(value)
  if (idx >= 0) parts.splice(idx, 1)
  else parts.push(value)
  return parts.join(',')
}

function hasProvider(current: string, value: string): boolean {
  return current.split(',').map(s => s.trim()).includes(value)
}

type FormState = AppSettingsUpdate & {
  _ms_dns_password:  string
  _ms_dhcp_password: string
  _pihole_password:  string
  _bind_secret:      string
  _kea_secret:       string
}

const defaults: FormState = {
  dns_provider: 'msdns', dhcp_provider: 'msdhcp',
  ms_dns_winrm_host: '', ms_dns_winrm_user: '', ms_dns_winrm_port: 5985,
  ms_dns_winrm_transport: 'ntlm', ms_dns_server: '',
  ms_dhcp_winrm_host: '', ms_dhcp_winrm_user: '', ms_dhcp_winrm_port: 5985,
  ms_dhcp_winrm_transport: 'ntlm', ms_dhcp_server: '',
  pihole_url: '',
  bind_host: '', bind_port: 53, bind_tsig_key_name: '',
  bind_tsig_algorithm: 'hmac-sha256', bind_zones: '',
  kea_url: '',
  util_warn_threshold: 80,
  util_critical_threshold: 95,
  util_dashboard_top_n: 5,
  _ms_dns_password: '', _ms_dhcp_password: '', _pihole_password: '',
  _bind_secret: '', _kea_secret: '',
}

function Field({ label, hint, children }: { label: string; hint?: string; children: React.ReactNode }) {
  return (
    <div className="form-field">
      <label>{label}{hint && <span style={{ color: 'var(--accent)', marginLeft: '0.375rem', fontSize: '0.7rem' }}>{hint}</span>}</label>
      {children}
    </div>
  )
}

function SecretField({
  label, value, onChange, placeholder, isSet,
}: {
  label: string; value: string; onChange: (v: string) => void
  placeholder?: string; isSet?: boolean
}) {
  const [show, setShow] = useState(false)
  return (
    <Field label={label} hint={isSet ? '● set' : undefined}>
      <div className="password-wrap">
        <input
          type={show ? 'text' : 'password'}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={isSet ? 'Leave blank to keep' : (placeholder ?? 'Enter value')}
        />
        <button type="button" className="btn-ghost btn-sm" onClick={() => setShow(s => !s)}>
          {show ? <EyeOff size={13} /> : <Eye size={13} />}
        </button>
      </div>
    </Field>
  )
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return <div className="settings-section-title">{children}</div>
}

export default function SettingsPage() {
  const qc = useQueryClient()
  const { data, isLoading } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })
  const [form, setForm] = useState<FormState>(defaults)
  const [saved, setSaved] = useState(false)

  useEffect(() => {
    if (!data) return
    setForm(f => ({
      ...f,
      dns_provider:           data.dns_provider,
      dhcp_provider:          data.dhcp_provider,
      ms_dns_winrm_host:      data.ms_dns_winrm_host,
      ms_dns_winrm_user:      data.ms_dns_winrm_user,
      ms_dns_winrm_port:      data.ms_dns_winrm_port,
      ms_dns_winrm_transport: data.ms_dns_winrm_transport,
      ms_dns_server:          data.ms_dns_server,
      ms_dhcp_winrm_host:     data.ms_dhcp_winrm_host,
      ms_dhcp_winrm_user:     data.ms_dhcp_winrm_user,
      ms_dhcp_winrm_port:     data.ms_dhcp_winrm_port,
      ms_dhcp_winrm_transport:data.ms_dhcp_winrm_transport,
      ms_dhcp_server:         data.ms_dhcp_server,
      pihole_url:             data.pihole_url,
      bind_host:           data.bind_host,
      bind_port:           data.bind_port,
      bind_tsig_key_name:  data.bind_tsig_key_name,
      bind_tsig_algorithm: data.bind_tsig_algorithm,
      bind_zones:          data.bind_zones,
      kea_url:             data.kea_url,
      util_warn_threshold:     data.util_warn_threshold,
      util_critical_threshold: data.util_critical_threshold,
      util_dashboard_top_n:    data.util_dashboard_top_n,
    }))
  }, [data])

  const mutation = useMutation({
    mutationFn: () => {
      const payload: AppSettingsUpdate = {
        dns_provider:            form.dns_provider,
        dhcp_provider:           form.dhcp_provider,
        ms_dns_winrm_host:       form.ms_dns_winrm_host,
        ms_dns_winrm_user:       form.ms_dns_winrm_user,
        ms_dns_winrm_port:       form.ms_dns_winrm_port,
        ms_dns_winrm_transport:  form.ms_dns_winrm_transport,
        ms_dns_server:           form.ms_dns_server,
        ms_dhcp_winrm_host:      form.ms_dhcp_winrm_host,
        ms_dhcp_winrm_user:      form.ms_dhcp_winrm_user,
        ms_dhcp_winrm_port:      form.ms_dhcp_winrm_port,
        ms_dhcp_winrm_transport: form.ms_dhcp_winrm_transport,
        ms_dhcp_server:          form.ms_dhcp_server,
        pihole_url:              form.pihole_url,
        bind_host:               form.bind_host,
        bind_port:               form.bind_port,
        bind_tsig_key_name:      form.bind_tsig_key_name,
        bind_tsig_algorithm:     form.bind_tsig_algorithm,
        bind_zones:              form.bind_zones,
        kea_url:                 form.kea_url,
        util_warn_threshold:     form.util_warn_threshold,
        util_critical_threshold: form.util_critical_threshold,
        util_dashboard_top_n:    form.util_dashboard_top_n,
      }
      if (form._ms_dns_password)  payload.ms_dns_winrm_password  = form._ms_dns_password
      if (form._ms_dhcp_password) payload.ms_dhcp_winrm_password = form._ms_dhcp_password
      if (form._pihole_password)  payload.pihole_password         = form._pihole_password
      if (form._bind_secret)      payload.bind_tsig_key_secret    = form._bind_secret
      if (form._kea_secret)       payload.kea_secret              = form._kea_secret
      return settingsApi.update(payload)
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['settings'] })
      setForm(f => ({ ...f, _ms_dns_password: '', _ms_dhcp_password: '', _pihole_password: '', _bind_secret: '', _kea_secret: '' }))
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const s = <K extends keyof FormState>(key: K) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) =>
      setForm(f => ({ ...f, [key]: (
        key === 'ms_dns_winrm_port' || key === 'ms_dhcp_winrm_port' || key === 'bind_port' ||
        key === 'util_warn_threshold' || key === 'util_critical_threshold' ||
        key === 'util_dashboard_top_n'
      ) ? Number(e.target.value) : e.target.value }))

  const needsMSDNS  = hasProvider(form.dns_provider  ?? '', 'msdns')
  const needsMSDHCP = hasProvider(form.dhcp_provider ?? '', 'msdhcp')
  const needsPihole = hasProvider(form.dns_provider ?? '', 'pihole') || hasProvider(form.dhcp_provider ?? '', 'pihole')
  const needsBind   = hasProvider(form.dns_provider ?? '', 'bind')
  const needsKea    = hasProvider(form.dhcp_provider ?? '', 'keadhcp')

  if (isLoading) return <p className="loading">Loading…</p>

  return (
    <div style={{ maxWidth: '760px' }}>
      <div className="page-header"><h1>Settings</h1></div>

      <form onSubmit={e => { e.preventDefault(); mutation.mutate() }}>

        {/* ── Provider selection ── */}
        <div className="settings-section">
          <SectionTitle>Providers</SectionTitle>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
            <div>
              <div className="provider-group-label">DNS</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {DNS_OPTIONS.map(opt => (
                  <label key={opt.value} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={hasProvider(form.dns_provider ?? '', opt.value)}
                      onChange={() => setForm(f => ({ ...f, dns_provider: toggleProvider(f.dns_provider ?? '', opt.value) }))}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>
            <div>
              <div className="provider-group-label">DHCP</div>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.35rem' }}>
                {DHCP_OPTIONS.map(opt => (
                  <label key={opt.value} className="checkbox-label">
                    <input
                      type="checkbox"
                      checked={hasProvider(form.dhcp_provider ?? '', opt.value)}
                      onChange={() => setForm(f => ({ ...f, dhcp_provider: toggleProvider(f.dhcp_provider ?? '', opt.value) }))}
                    />
                    {opt.label}
                  </label>
                ))}
              </div>
            </div>
          </div>
        </div>

        {/* ── Microsoft DNS ── */}
        {needsMSDNS && (
          <div className="settings-section">
            <SectionTitle>Microsoft DNS</SectionTitle>
            <div className="form-grid">
              <Field label="WinRM Host">
                <input value={form.ms_dns_winrm_host ?? ''} onChange={s('ms_dns_winrm_host')} placeholder="dc.domain.local" />
              </Field>
              <Field label="Username">
                <input value={form.ms_dns_winrm_user ?? ''} onChange={s('ms_dns_winrm_user')} placeholder="DOMAIN\svcaccount" />
              </Field>
              <SecretField
                label="Password" value={form._ms_dns_password}
                onChange={v => setForm(f => ({ ...f, _ms_dns_password: v }))}
                isSet={data?.ms_dns_winrm_password_set}
              />
              <Field label="WinRM Port">
                <input type="number" value={form.ms_dns_winrm_port ?? 5985} onChange={s('ms_dns_winrm_port')} />
              </Field>
              <Field label="Transport">
                <select value={form.ms_dns_winrm_transport ?? 'ntlm'} onChange={s('ms_dns_winrm_transport')}>
                  {TRANSPORT_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="DNS Server">
                <input value={form.ms_dns_server ?? ''} onChange={s('ms_dns_server')} placeholder="dns.domain.local" />
              </Field>
            </div>
          </div>
        )}

        {/* ── Microsoft DHCP ── */}
        {needsMSDHCP && (
          <div className="settings-section">
            <SectionTitle>Microsoft DHCP</SectionTitle>
            <div className="form-grid">
              <Field label="WinRM Host">
                <input value={form.ms_dhcp_winrm_host ?? ''} onChange={s('ms_dhcp_winrm_host')} placeholder="dc.domain.local" />
              </Field>
              <Field label="Username">
                <input value={form.ms_dhcp_winrm_user ?? ''} onChange={s('ms_dhcp_winrm_user')} placeholder="DOMAIN\svcaccount" />
              </Field>
              <SecretField
                label="Password" value={form._ms_dhcp_password}
                onChange={v => setForm(f => ({ ...f, _ms_dhcp_password: v }))}
                isSet={data?.ms_dhcp_winrm_password_set}
              />
              <Field label="WinRM Port">
                <input type="number" value={form.ms_dhcp_winrm_port ?? 5985} onChange={s('ms_dhcp_winrm_port')} />
              </Field>
              <Field label="Transport">
                <select value={form.ms_dhcp_winrm_transport ?? 'ntlm'} onChange={s('ms_dhcp_winrm_transport')}>
                  {TRANSPORT_OPTIONS.map(t => <option key={t} value={t}>{t}</option>)}
                </select>
              </Field>
              <Field label="DHCP Server">
                <input value={form.ms_dhcp_server ?? ''} onChange={s('ms_dhcp_server')} placeholder="dhcp.domain.local" />
              </Field>
            </div>
          </div>
        )}

        {/* ── Pi-hole ── */}
        {needsPihole && (
          <div className="settings-section">
            <SectionTitle>Pi-hole v6</SectionTitle>
            <div className="form-grid">
              <Field label="URL">
                <input value={form.pihole_url ?? ''} onChange={s('pihole_url')} placeholder="http://192.168.1.1" />
              </Field>
              <SecretField
                label="Admin Password" value={form._pihole_password}
                onChange={v => setForm(f => ({ ...f, _pihole_password: v }))}
                isSet={data?.pihole_password_set}
              />
            </div>
          </div>
        )}

        {/* ── BIND ── */}
        {needsBind && (
          <div className="settings-section">
            <SectionTitle>BIND DNS</SectionTitle>
            <div className="form-grid">
              <Field label="Nameserver Host">
                <input value={form.bind_host ?? ''} onChange={s('bind_host')} placeholder="ns1.domain.local" />
              </Field>
              <Field label="Port">
                <input type="number" value={form.bind_port ?? 53} onChange={s('bind_port')} />
              </Field>
              <Field label="TSIG Key Name">
                <input value={form.bind_tsig_key_name ?? ''} onChange={s('bind_tsig_key_name')} placeholder="ipam-key" />
              </Field>
              <SecretField
                label="TSIG Key Secret (base64)" value={form._bind_secret}
                onChange={v => setForm(f => ({ ...f, _bind_secret: v }))}
                isSet={data?.bind_tsig_key_secret_set}
              />
              <Field label="TSIG Algorithm">
                <select value={form.bind_tsig_algorithm ?? 'hmac-sha256'} onChange={s('bind_tsig_algorithm')}>
                  {TSIG_ALGORITHMS.map(a => <option key={a} value={a}>{a}</option>)}
                </select>
              </Field>
              <Field label="Zones (comma-separated)" hint="required">
                <input
                  value={form.bind_zones ?? ''}
                  onChange={s('bind_zones')}
                  placeholder="example.com, 1.168.192.in-addr.arpa"
                />
              </Field>
            </div>
          </div>
        )}

        {/* ── ISC Kea ── */}
        {needsKea && (
          <div className="settings-section">
            <SectionTitle>ISC Kea Control Agent</SectionTitle>
            <div className="form-grid">
              <Field label="Control Agent URL">
                <input value={form.kea_url ?? ''} onChange={s('kea_url')} placeholder="http://kea-host:8000" />
              </Field>
              <SecretField
                label="API Secret (if auth enabled)" value={form._kea_secret}
                onChange={v => setForm(f => ({ ...f, _kea_secret: v }))}
                isSet={data?.kea_secret_set}
                placeholder="Leave blank if no auth"
              />
            </div>
          </div>
        )}

        {/* ── Utilization ── */}
        <div className="settings-section">
          <SectionTitle>Utilization Thresholds</SectionTitle>
          <div className="form-grid">
            <Field label="Warn threshold (%)" hint="default 80">
              <input
                type="number" min={1} max={99}
                value={form.util_warn_threshold ?? 80}
                onChange={s('util_warn_threshold')}
              />
            </Field>
            <Field label="Critical threshold (%)" hint="default 95">
              <input
                type="number" min={1} max={100}
                value={form.util_critical_threshold ?? 95}
                onChange={s('util_critical_threshold')}
              />
            </Field>
            <Field label="Dashboard top N subnets" hint="default 5">
              <input
                type="number" min={1} max={20}
                value={form.util_dashboard_top_n ?? 5}
                onChange={s('util_dashboard_top_n')}
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
    </div>
  )
}
