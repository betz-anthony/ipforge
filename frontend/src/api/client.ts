import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

// Attach JWT from localStorage
api.interceptors.request.use(cfg => {
  const token = localStorage.getItem('ipam_token')
  if (token) cfg.headers.Authorization = `Bearer ${token}`
  return cfg
})

// On 401, clear token and redirect to login
api.interceptors.response.use(
  r => r,
  err => {
    if (err.response?.status === 401) {
      localStorage.removeItem('ipam_token')
      localStorage.removeItem('ipam_user')
      window.location.href = '/login'
    }
    return Promise.reject(err)
  }
)

export interface AuthUser {
  username: string
  role: 'readonly' | 'operator' | 'admin'
}

export const authApi = {
  login: (username: string, password: string) => {
    const form = new URLSearchParams({ username, password })
    return api.post<{ access_token: string; username: string; role: string }>(
      '/auth/login',
      form,
      { headers: { 'Content-Type': 'application/x-www-form-urlencoded' } }
    ).then(r => r.data)
  },
  me: () => api.get<AuthUser>('/auth/me').then(r => r.data),
  changePassword: (current_password: string, new_password: string) =>
    api.post('/auth/change-password', { current_password, new_password }),
}

export interface UserRecord {
  id: number
  username: string
  role: string
  enabled: boolean
  auth_source: string   // "local" | "ldap"
}

export const usersApi = {
  list:   ()                                                      => api.get<UserRecord[]>('/users').then(r => r.data),
  create: (username: string, password: string, role: string)     => api.post<UserRecord>('/users', { username, password, role }).then(r => r.data),
  update: (id: number, data: Partial<{ role: string; enabled: boolean; password: string }>) =>
    api.put<UserRecord>(`/users/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/users/${id}`),
}

export interface Subnet {
  id: number
  name: string
  cidr: string
  ip_version: 4 | 6
  vlan_id: number | null
  description: string | null
  notes: string | null
  created_at: string
  parent_id: number | null
  used_count: number
  total_count: number
  utilization_pct: number
  rollup_used_count: number
  rollup_total_count: number
  rollup_utilization_pct: number
  scan_interval_minutes: number | null
  dns_provider_name: string | null
  dhcp_provider_name: string | null
}

export interface IPAddress {
  id: number
  address: string
  subnet_id: number
  hostname: string | null
  status: 'available' | 'reserved' | 'assigned' | 'deprecated' | 'discovered'
  mac_address: string | null
  description: string | null
  notes: string | null
  created_at: string
  updated_at: string
  last_seen: string | null
  dns_provider?: string | null
  dns_zone?: string | null
  dhcp_provider?: string | null
  dhcp_scope_id?: string | null
}

export interface DeletePreviewItem {
  key: string
  type: 'dns' | 'dhcp'
  provider: string
  zone?: string
  record_type?: string
  name?: string
  value?: string
  scope_id?: string
  ip_address?: string
  mac_address?: string
}

export interface DeletePreview {
  address: string
  hostname: string | null
  items: DeletePreviewItem[]
}

export interface StaleAddress {
  id: number
  address: string
  subnet_id: number
  subnet_cidr: string
  hostname: string | null
  status: 'reserved' | 'assigned'
  mac_address: string | null
  last_seen: string | null
  days_stale: number
}

export type ReclaimAction = 'deprecate' | 'extend' | 'dismiss'

export const subnetsApi = {
  list: () => api.get<Subnet[]>('/subnets').then(r => r.data),
  create: (data: Omit<Subnet, 'id' | 'created_at' | 'notes' | 'used_count' | 'total_count' | 'utilization_pct' | 'rollup_used_count' | 'rollup_total_count' | 'rollup_utilization_pct' | 'parent_id' | 'scan_interval_minutes'> & { notes?: string | null; parent_id?: number | null; scan_interval_minutes?: number | null }) =>
    api.post<Subnet>('/subnets', data).then(r => r.data),
  update: (id: number, data: Partial<Omit<Subnet, 'id' | 'created_at' | 'used_count' | 'total_count' | 'utilization_pct' | 'rollup_used_count' | 'rollup_total_count' | 'rollup_utilization_pct'>>) =>
    api.put<Subnet>(`/subnets/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/subnets/${id}`),
  suggestParent: (cidr: string) =>
    api.get<Subnet[]>('/subnets/suggest-parent', { params: { cidr } }).then(r => r.data),
}

export const addressesApi = {
  list: (params?: { subnet_id?: number; status?: string }) =>
    api.get<IPAddress[]>('/addresses', { params }).then(r => r.data),
  create: (data: Omit<IPAddress, 'id' | 'created_at' | 'updated_at' | 'notes' | 'last_seen'> & { notes?: string | null }) =>
    api.post<IPAddress>('/addresses', data).then(r => r.data),
  update: (id: number, data: Partial<IPAddress>) =>
    api.put<IPAddress>(`/addresses/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/addresses/${id}`),
  byIp: (address: string) =>
    api.get<IPAddress>(`/addresses/by-ip/${encodeURIComponent(address)}`).then(r => r.data),
  deletePreview: (id: number) =>
    api.get<DeletePreview>(`/addresses/${id}/delete-preview`).then(r => r.data),
  deleteWithCleanup: (id: number, cleanupKeys: string[]) =>
    api.delete(`/addresses/${id}`, { data: { cleanup_keys: cleanupKeys } }),
}

export interface DHCPScope {
  scope_id: string
  name: string
  subnet_mask: string
  start_range: string
  end_range: string
  description: string
  active: boolean
  ip_version: number
  source: string
}

export interface DHCPReservation {
  scope_id: string
  ip_address: string
  mac_address: string  // IPv4
  client_duid: string  // IPv6
  iaid: number         // IPv6
  name: string
  description: string
  source?: string
  synced_at?: string | null
}

export interface DNSZone {
  zone: string
  source: string
}

export interface DNSRecord {
  name: string
  record_type: string
  value: string
  zone: string
  ttl: number
  source: string
  synced_at?: string | null
}

export interface PingResult {
  host: string
  reachable: boolean
  min_ms: number | null
  avg_ms: number | null
  max_ms: number | null
  loss_pct: number
}

export const toolsApi = {
  ping: (host: string) =>
    api.get<PingResult>('/tools/ping', { params: { host } }).then(r => r.data),
}

export const dhcpApi = {
  listScopes: () => api.get<DHCPScope[]>('/dhcp/scopes').then(r => r.data),
  listLeases: (scope_id: string, source: string) =>
    api.get<DHCPReservation[]>(`/dhcp/scopes/${scope_id}/leases`, { params: { source } }).then(r => r.data),
  addReservation: (scope_id: string, data: Omit<DHCPReservation, 'scope_id'>, source: string) =>
    api.post<DHCPReservation>(`/dhcp/scopes/${scope_id}/reservations`, data, { params: { source } }).then(r => r.data),
  deleteReservation: (scope_id: string, ip_address: string, source: string) =>
    api.delete(`/dhcp/scopes/${scope_id}/reservations/${ip_address}`, { params: { source } }),
  byIp: (address: string) =>
    api.get<DHCPReservation[]>(`/dhcp/by-ip/${encodeURIComponent(address)}`).then(r => r.data),
}

export const providersApi = {
  get: () => api.get<{ dns: string[]; dhcp: string[] }>('/providers').then(r => r.data),
}

export const dnsApi = {
  listZones: () => api.get<DNSZone[]>('/dns/zones').then(r => r.data),
  listRecords: (zone: string) =>
    api.get<DNSRecord[]>(`/dns/zones/${zone}/records`).then(r => r.data),
  createRecord: (zone: string, data: Omit<DNSRecord, 'zone'>) =>
    api.post<DNSRecord>(`/dns/zones/${zone}/records`, data).then(r => r.data),
  deleteRecord: (zone: string, record: DNSRecord) =>
    api.delete(`/dns/zones/${zone}/records`, { data: record }),
  byIp: (address: string) =>
    api.get<DNSRecord[]>(`/dns/by-ip/${encodeURIComponent(address)}`).then(r => r.data),
}

export interface AppSettings {
  util_warn_threshold:     number
  util_critical_threshold: number
  util_dashboard_top_n:    number
  scan_interval_minutes:   number
  stale_reclaim_days:      number
}

export interface AppSettingsUpdate {
  util_warn_threshold?:     number
  util_critical_threshold?: number
  util_dashboard_top_n?:    number
  scan_interval_minutes?:   number
  stale_reclaim_days?:      number
}

export interface ProviderConfig {
  id:            number
  category:      'dns' | 'dhcp'
  provider_type: string
  name:          string
  config:        Record<string, unknown>
  secrets_set:   Record<string, boolean>
  enabled:       boolean
  sort_order:    number
}

export interface ProviderConfigCreate {
  category:      'dns' | 'dhcp'
  provider_type: string
  name:          string
  config:        Record<string, unknown>
  enabled?:      boolean
  sort_order?:   number
}

export interface ProviderConfigUpdate {
  name?:       string
  config?:     Record<string, unknown>
  enabled?:    boolean
  sort_order?: number
}

export const settingsApi = {
  get: () => api.get<AppSettings>('/settings').then(r => r.data),
  update: (data: AppSettingsUpdate) => api.put<AppSettings>('/settings', data).then(r => r.data),
}

export interface LdapSettings {
  ldap_enabled:        boolean
  ldap_host:           string
  ldap_port:           number
  ldap_use_ssl:        boolean
  ldap_bind_dn:        string
  ldap_bind_password:  string
  ldap_base_dn:        string
  ldap_user_filter:    string
  ldap_group_admin:    string
  ldap_group_operator: string
  ldap_group_readonly: string
  ldap_default_role:   string
}

export const ldapApi = {
  get:    () => api.get<LdapSettings>('/settings/ldap').then(r => r.data),
  update: (data: Partial<LdapSettings>) =>
    api.put<LdapSettings>('/settings/ldap', data).then(r => r.data),
}

export const providerConfigsApi = {
  list:   ()                                     => api.get<ProviderConfig[]>('/provider-configs').then(r => r.data),
  create: (data: ProviderConfigCreate)           => api.post<ProviderConfig>('/provider-configs', data).then(r => r.data),
  update: (id: number, data: ProviderConfigUpdate) => api.put<ProviderConfig>(`/provider-configs/${id}`, data).then(r => r.data),
  delete: (id: number)                           => api.delete(`/provider-configs/${id}`),
}

export const cacheApi = {
  purge: (category: 'dns' | 'dhcp', source: string) =>
    api.delete<{ category: string; source: string; deleted: number }>(`/cache/${category}`, { params: { source } }).then(r => r.data),
}

export interface SyncInfo {
  synced_at: string | null
  age_seconds: number | null
  status: 'ok' | 'error' | 'running' | 'never'
  error: string | null
}

export const syncApi = {
  status: () => api.get<{ dns: SyncInfo; dhcp: SyncInfo }>('/sync/status').then(r => r.data),
  trigger: (type?: 'dns' | 'dhcp') =>
    api.post('/sync/trigger', null, { params: type ? { type } : {} }).then(r => r.data),
}

export interface AppStats {
  dns_zones:   number
  dns_records: number
  dhcp_scopes: number
  dhcp_leases: number
}

export const statsApi = {
  get: () => api.get<AppStats>('/stats').then(r => r.data),
}

export interface ScanHostResult {
  ip: string
  reachable: boolean
  latency_ms: number | null
}

export interface ScanStatus {
  status: 'ok' | 'error' | 'running' | 'never'
  scanned_at: string | null
  age_seconds: number | null
  error: string | null
  results: ScanHostResult[]
}

export interface Collision {
  id: number
  ip_address: string
  collision_type: 'active_but_available' | 'multi_dhcp_scope' | 'hostname_mismatch'
  details: string | null
  detected_at: string | null
  resolved: boolean
  resolved_at: string | null
}

export interface CollisionResolveRequest {
  new_status?:         string
  canonical_hostname?: string
  sources_to_remove?:  string[]
}

export const scanApi = {
  trigger: (subnet_id: number, body?: { start_ip?: string; end_ip?: string }) =>
    api.post<{ status: string }>(`/scan/subnets/${subnet_id}`, body ?? {}).then(r => r.data),
  status: (subnet_id: number) =>
    api.get<ScanStatus>(`/scan/subnets/${subnet_id}`).then(r => r.data),
  collisions: (params?: { resolved?: boolean; subnet_id?: number }) =>
    api.get<Collision[]>('/scan/collisions', { params }).then(r => r.data),
  resolveCollision: (id: number, body?: CollisionResolveRequest) =>
    api.put<{ id: number; resolved: boolean }>(`/scan/collisions/${id}/resolve`, body ?? {}).then(r => r.data),
}

export interface SearchResults {
  subnets: Array<{
    id: number
    name: string
    cidr: string
    ip_version: number
    description: string | null
  }>
  addresses: Array<{
    id: number
    address: string
    hostname: string | null
    status: string
    mac_address: string | null
    subnet_id: number
  }>
  leases: Array<{
    ip_address: string
    name: string | null
    mac_address: string | null
    scope_id: string
    source: string
  }>
  records: Array<{
    name: string
    record_type: string
    value: string
    zone: string
    source: string
  }>
}

export const searchApi = {
  search: (q: string) =>
    api.get<SearchResults>('/search', { params: { q } }).then(r => r.data),
}

export interface AuditEntry {
  id:            number
  timestamp:     string
  username:      string
  action:        'create' | 'update' | 'delete' | 'resolve'
  resource_type: string
  resource_id:   string
  summary:       string | null
  before_state:  string | null
  after_state:   string | null
}

export const auditApi = {
  list: (params?: {
    resource_type?: string
    username?: string
    from_date?: string
    to_date?: string
    limit?: number
    offset?: number
  }) => api.get<AuditEntry[]>('/audit', { params }).then(r => r.data),
}

export interface ScanHistoryDay {
  date: string
  up_count: number
  total_count: number
  uptime_pct: number
  avg_latency_ms: number | null
}

export interface AlertEvent {
  id: number
  event_type: 'went_unreachable' | 'came_back'
  ip_address: string
  subnet_id: number
  detected_at: string
  details: string | null
  acknowledged: boolean
  acknowledged_at: string | null
}

export const scanHistoryApi = {
  list: (address_id: number) =>
    api.get<ScanHistoryDay[]>(`/addresses/${address_id}/scan-history`).then(r => r.data),
}

export const scanAlertsApi = {
  list: (params?: { acknowledged?: boolean; subnet_id?: number; limit?: number }) =>
    api.get<AlertEvent[]>('/scan/alerts', { params }).then(r => r.data),
  acknowledge: (id: number) =>
    api.put<AlertEvent>(`/scan/alerts/${id}/acknowledge`).then(r => r.data),
  acknowledgeAll: (subnet_id?: number) =>
    api.post<{ count: number }>('/scan/alerts/acknowledge-all', null,
      { params: subnet_id !== undefined ? { subnet_id } : {} }).then(r => r.data),
}

export const reclaimApi = {
  listStale: (params?: { subnet_id?: number; limit?: number; offset?: number }) =>
    api.get<StaleAddress[]>('/addresses/stale', { params }).then(r => r.data),
  countStale: () =>
    api.get<{ count: number }>('/addresses/stale/count').then(r => r.data),
  reclaim: (id: number, action: ReclaimAction) =>
    api.put<StaleAddress>(`/addresses/${id}/reclaim`, { action }).then(r => r.data),
  bulkDeprecate: (subnet_id: number) =>
    api.post<{ deprecated: number }>('/addresses/stale/bulk-deprecate', { subnet_id }).then(r => r.data),
}

export interface ImportResult {
  created: number
  updated: number
  skipped: number
  errors: string[]
}

export const importExportApi = {
  exportSubnetsUrl: () => '/api/importexport/subnets.csv',
  exportAddressesUrl: () => '/api/importexport/addresses.csv',
  importSubnets: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ImportResult>('/importexport/subnets', form).then(r => r.data)
  },
  importAddresses: (file: File) => {
    const form = new FormData()
    form.append('file', file)
    return api.post<ImportResult>('/importexport/addresses', form).then(r => r.data)
  },
}
