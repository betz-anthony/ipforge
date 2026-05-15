import { useState } from 'react'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Network, List, Server, Globe, Search } from 'lucide-react'
import { statsApi, dnsApi, dhcpApi, scanApi, subnetsApi, settingsApi, scanAlertsApi, type Collision } from '../api/client'
import { formatRelative } from '../utils/time'
import SlidePanel from '../components/SlidePanel'
import UtilBar from '../components/UtilBar'
import CollisionResolveDialog from './CollisionResolveDialog'

const TILES = [
  { to: '/subnets',   icon: Network, title: 'Subnets',   desc: 'Manage IP subnets and CIDRs' },
  { to: '/addresses', icon: List,    title: 'Addresses', desc: 'Track IP address assignments' },
  { to: '/dhcp',      icon: Server,  title: 'DHCP',      desc: 'Scopes, leases, and reservations' },
  { to: '/dns',       icon: Globe,   title: 'DNS',        desc: 'Zones and resource records' },
  { to: '/search',    icon: Search,  title: 'Search',    desc: 'Find by IP, MAC, or hostname' },
]

const SOURCE_LABEL: Record<string, string> = {
  msdhcp: 'MS DHCP', pihole: 'Pi-hole', keadhcp: 'Kea',
  msdns: 'MS DNS', bind: 'BIND',
}

type PanelKey = 'dns_zones' | 'dns_records' | 'dhcp_scopes' | 'dhcp_leases' | 'collisions' | 'scan_alerts'

function count(val: number | undefined) {
  return val === undefined ? '—' : val.toLocaleString()
}

export default function Dashboard() {
  const [openPanel, setOpenPanel] = useState<PanelKey | null>(null)

  const { data: stats } = useQuery({ queryKey: ['stats'], queryFn: statsApi.get })

  const { data: zones } = useQuery({
    queryKey: ['dns-zones'],
    queryFn: dnsApi.listZones,
    enabled: openPanel === 'dns_zones' || openPanel === 'dns_records',
  })

  const { data: scopes } = useQuery({
    queryKey: ['dhcp-scopes'],
    queryFn: dhcpApi.listScopes,
    enabled: openPanel === 'dhcp_scopes' || openPanel === 'dhcp_leases',
  })

  const { data: collisions } = useQuery({
    queryKey: ['collisions-dashboard'],
    queryFn: () => scanApi.collisions({ resolved: false }),
  })

  const { data: scanAlerts, refetch: refetchAlerts } = useQuery({
    queryKey: ['scan-alerts-dashboard'],
    queryFn: () => scanAlertsApi.list({ acknowledged: false, limit: 10 }),
  })

  const acknowledgeAllMutation = useMutation({
    mutationFn: () => scanAlertsApi.acknowledgeAll(),
    onSuccess: () => refetchAlerts(),
  })

  const { data: subnets }      = useQuery({ queryKey: ['subnets'],  queryFn: subnetsApi.list })
  const { data: settingsData } = useQuery({ queryKey: ['settings'], queryFn: settingsApi.get })

  const warnAt     = settingsData?.util_warn_threshold     ?? 80
  const criticalAt = settingsData?.util_critical_threshold  ?? 95
  const topN       = settingsData?.util_dashboard_top_n     ?? 5

  const topSubnets = subnets
    ? [...subnets].sort((a, b) => b.utilization_pct - a.utilization_pct).slice(0, topN)
    : []

  const [resolveTarget, setResolveTarget] = useState<Collision | null>(null)

  const toggle = (key: PanelKey) =>
    setOpenPanel(prev => (prev === key ? null : key))

  return (
    <div>
      <div className="page-header">
        <h1>Dashboard</h1>
      </div>

      <p className="section-label">Overview</p>
      <div className="stats-grid">
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dns_zones')}
        >
          <div className="stat-value">{count(stats?.dns_zones)}</div>
          <div className="stat-label">DNS Zones</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dns_records')}
        >
          <div className="stat-value">{count(stats?.dns_records)}</div>
          <div className="stat-label">DNS Records</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dhcp_scopes')}
        >
          <div className="stat-value">{count(stats?.dhcp_scopes)}</div>
          <div className="stat-label">DHCP Scopes</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('dhcp_leases')}
        >
          <div className="stat-value accent">{count(stats?.dhcp_leases)}</div>
          <div className="stat-label">DHCP Leases</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('collisions')}
        >
          <div
            className="stat-value"
            style={{ color: collisions && collisions.length > 0 ? 'var(--warning, #f59e0b)' : undefined }}
          >
            {collisions?.length ?? '—'}
          </div>
          <div className="stat-label">Collisions</div>
          <div className="stat-sub">unresolved</div>
        </div>
        <div
          className="stat-card"
          style={{ cursor: 'pointer' }}
          onClick={() => toggle('scan_alerts')}
        >
          <div
            className="stat-value"
            style={{ color: scanAlerts && scanAlerts.length > 0 ? 'var(--danger, #f87171)' : undefined }}
          >
            {scanAlerts?.length ?? '—'}
          </div>
          <div className="stat-label">Scan Alerts</div>
          <div className="stat-sub">unacknowledged</div>
        </div>
      </div>

      <p className="section-label">Sections</p>
      <div className="nav-tiles">
        {TILES.map(({ to, icon: Icon, title, desc }) => (
          <Link key={to} to={to} className="nav-tile">
            <div className="nav-tile-icon"><Icon size={18} strokeWidth={1.75} /></div>
            <div className="nav-tile-title">{title}</div>
            <div className="nav-tile-desc">{desc}</div>
          </Link>
        ))}
      </div>

      <p className="section-label">Subnet Utilization</p>
      {!subnets ? (
        <p className="loading">Loading…</p>
      ) : topSubnets.length === 0 ? (
        <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No subnets defined.</p>
      ) : (
        <div className="stat-card" style={{ padding: '0.75rem 1rem' }}>
          <div style={{ display: 'flex', flexDirection: 'column', gap: '0.6rem' }}>
            {topSubnets.map(s => (
              <div key={s.id} style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <span style={{ width: '120px', fontSize: '0.78rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', color: 'var(--text-subtle)' }}>
                  {s.name}
                </span>
                <span className="font-mono" style={{ width: '110px', fontSize: '0.72rem', color: 'var(--text-muted)', flexShrink: 0 }}>
                  {s.cidr}
                </span>
                <UtilBar pct={s.utilization_pct} warn={warnAt} critical={criticalAt} />
                <span style={{ fontSize: '0.7rem', color: 'var(--text-muted)', marginLeft: 'auto' }}>
                  {s.used_count}/{s.total_count}
                </span>
              </div>
            ))}
          </div>
        </div>
      )}

      {(openPanel === 'dns_zones' || openPanel === 'dns_records') && (
        <SlidePanel
          title={openPanel === 'dns_zones' ? 'DNS Zones' : 'DNS Records'}
          subtitle={
            openPanel === 'dns_zones'
              ? `${stats?.dns_zones ?? '—'} zones`
              : `${stats?.dns_records ?? '—'} records across ${stats?.dns_zones ?? '—'} zones`
          }
          onClose={() => setOpenPanel(null)}
        >
          <div>
            {!zones ? (
              <p className="loading">Loading…</p>
            ) : zones.length === 0 ? (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No zones found.</p>
            ) : (
              <div className="detail-fields">
                {zones.map((z, i) => (
                  <div key={i} className="detail-field">
                    <span className="detail-field-label font-mono" style={{ fontSize: '0.78rem' }}>
                      {z.zone}
                    </span>
                    <span className="detail-field-value">
                      <span className="badge badge-gray" style={{ fontSize: '0.6rem' }}>
                        {SOURCE_LABEL[z.source] ?? z.source}
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: '1rem' }}>
              <Link to="/dns" className="btn-ghost btn-sm" onClick={() => setOpenPanel(null)}>
                View all in DNS →
              </Link>
            </div>
          </div>
        </SlidePanel>
      )}

      {(openPanel === 'dhcp_scopes' || openPanel === 'dhcp_leases') && (
        <SlidePanel
          title={openPanel === 'dhcp_scopes' ? 'DHCP Scopes' : 'DHCP Leases'}
          subtitle={
            openPanel === 'dhcp_scopes'
              ? `${stats?.dhcp_scopes ?? '—'} scopes`
              : `${stats?.dhcp_leases ?? '—'} total reservations`
          }
          onClose={() => setOpenPanel(null)}
        >
          <div>
            {!scopes ? (
              <p className="loading">Loading…</p>
            ) : scopes.length === 0 ? (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No scopes found.</p>
            ) : (
              <div className="detail-fields">
                {scopes.map((s, i) => (
                  <div key={i} className="detail-field">
                    <span className="detail-field-label" style={{ fontSize: '0.78rem' }}>
                      <span className={`badge ${s.active ? 'badge-green' : 'badge-gray'}`}
                        style={{ fontSize: '0.55rem', marginRight: '0.3rem' }}>
                        IPv{s.ip_version}
                      </span>
                      {s.name || s.scope_id}
                    </span>
                    <span className="detail-field-value font-mono" style={{ fontSize: '0.75rem' }}>
                      {s.scope_id}
                    </span>
                  </div>
                ))}
              </div>
            )}
            <div style={{ marginTop: '1rem' }}>
              <Link to="/dhcp" className="btn-ghost btn-sm" onClick={() => setOpenPanel(null)}>
                View all in DHCP →
              </Link>
            </div>
          </div>
        </SlidePanel>
      )}

      {openPanel === 'collisions' && (
        <SlidePanel
          title="IP Collisions"
          subtitle={`${collisions?.length ?? 0} unresolved`}
          onClose={() => setOpenPanel(null)}
        >
          {!collisions || collisions.length === 0 ? (
            <p style={{ fontSize: '0.85rem', color: 'var(--text-muted)', padding: '1rem 0' }}>
              No unresolved collisions.
            </p>
          ) : (
            <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
              {collisions.map(c => (
                <div key={c.id} style={{ padding: '0.75rem', background: 'var(--surface-2)', borderRadius: '6px', border: '1px solid var(--border)' }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: '0.4rem' }}>
                    <span className="font-mono" style={{ fontSize: '0.85rem', fontWeight: 600 }}>{c.ip_address}</span>
                    <button
                      className="btn-ghost btn-sm"
                      style={{ fontSize: '0.65rem' }}
                      onClick={() => setResolveTarget(c)}
                    >
                      Resolve
                    </button>
                  </div>
                  <span className="badge badge-yellow" style={{ fontSize: '0.6rem' }}>
                    {c.collision_type.replace(/_/g, ' ')}
                  </span>
                  {c.details && (() => {
                    try {
                      const d = JSON.parse(c.details)
                      return (
                        <div style={{ fontSize: '0.72rem', color: 'var(--text-muted)', marginTop: '0.4rem' }}>
                          {Object.entries(d).map(([k, v]) => (
                            <span key={k} style={{ marginRight: '0.75rem' }}>
                              {k}: <strong>{typeof v === 'object' ? JSON.stringify(v) : String(v)}</strong>
                            </span>
                          ))}
                        </div>
                      )
                    } catch { return null }
                  })()}
                  <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', marginTop: '0.25rem' }}>
                    {c.detected_at
                      ? `Detected ${Math.floor((Date.now() - new Date(c.detected_at).getTime()) / 60000)}m ago`
                      : 'Detected: unknown'}
                  </div>
                </div>
              ))}
              <Link to="/subnets" className="btn-ghost btn-sm" onClick={() => setOpenPanel(null)}>
                View all subnets →
              </Link>
            </div>
          )}
        </SlidePanel>
      )}
      {openPanel === 'scan_alerts' && (
        <SlidePanel
          title="Scan Alerts"
          subtitle={`${scanAlerts?.length ?? 0} unacknowledged`}
          onClose={() => setOpenPanel(null)}
        >
          <div>
            {scanAlerts && scanAlerts.length > 0 && (
              <div style={{ marginBottom: '0.75rem' }}>
                <button
                  className="btn-ghost btn-sm"
                  onClick={() => acknowledgeAllMutation.mutate()}
                  disabled={acknowledgeAllMutation.isPending}
                >
                  {acknowledgeAllMutation.isPending ? 'Acknowledging…' : 'Acknowledge all'}
                </button>
              </div>
            )}
            {!scanAlerts ? (
              <p className="loading">Loading…</p>
            ) : scanAlerts.length === 0 ? (
              <p style={{ fontSize: '0.8rem', color: 'var(--text-muted)' }}>No unacknowledged alerts.</p>
            ) : (
              <div className="detail-fields">
                {scanAlerts.map(a => {
                  const details = (() => { try { return JSON.parse(a.details ?? '{}') } catch { return {} } })()
                  return (
                    <div key={a.id} className="detail-field">
                      <span className="detail-field-label" style={{ fontSize: '0.75rem' }}>
                        <span style={{ color: a.event_type === 'went_unreachable' ? 'var(--danger, #f87171)' : 'var(--success, #4ade80)', marginRight: '0.3rem' }}>
                          {a.event_type === 'went_unreachable' ? '▼' : '▲'}
                        </span>
                        <span className="font-mono">{a.ip_address}</span>
                        {details.hostname && <span style={{ color: 'var(--text-muted)', marginLeft: '0.3rem' }}>{details.hostname}</span>}
                      </span>
                      <span className="detail-field-value" style={{ fontSize: '0.72rem', color: 'var(--text-muted)' }}>
                        {formatRelative(a.detected_at)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </div>
        </SlidePanel>
      )}
      {resolveTarget && (
        <CollisionResolveDialog
          collision={resolveTarget}
          queryKeys={[['collisions-dashboard']]}
          onClose={() => setResolveTarget(null)}
        />
      )}
    </div>
  )
}
