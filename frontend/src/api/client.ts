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
  role: 'readonly' | 'operator' | 'admin' | 'scoped' | 'requester'
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

export interface ApiTokenRecord {
  id: number
  name: string
  token_prefix: string
  read_only: boolean
  expires_at: string | null
  last_used_at: string | null
  created_at: string
}

export interface ApiTokenCreated extends ApiTokenRecord {
  token: string
}

export const tokensApi = {
  list: () => api.get<ApiTokenRecord[]>('/auth/tokens').then(r => r.data),
  create: (body: { name: string; read_only: boolean; expires_at: string | null }) =>
    api.post<ApiTokenCreated>('/auth/tokens', body).then(r => r.data),
  remove: (id: number) => api.delete(`/auth/tokens/${id}`),
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

export interface GroupRecord {
  id: number
  name: string
  description: string | null
}

export interface GrantRecord {
  id: number
  user_id: number | null
  group_id: number | null
  subnet_id: number
  permission: 'view' | 'manage'
}

export const groupsApi = {
  list: () => api.get<GroupRecord[]>('/groups').then(r => r.data),
  create: (body: { name: string; description: string | null }) =>
    api.post<GroupRecord>('/groups', body).then(r => r.data),
  update: (id: number, body: { name?: string; description?: string | null }) =>
    api.put<GroupRecord>(`/groups/${id}`, body).then(r => r.data),
  remove: (id: number) => api.delete(`/groups/${id}`),
  members: (id: number) =>
    api.get<{ id: number; username: string; role: string }[]>(`/groups/${id}/members`).then(r => r.data),
  addMember: (id: number, user_id: number) =>
    api.post(`/groups/${id}/members`, { user_id }),
  removeMember: (id: number, user_id: number) =>
    api.request({ method: 'delete', url: `/groups/${id}/members`, data: { user_id } }),
}

export const grantsApi = {
  list: (params: { subnet_id?: number; user_id?: number; group_id?: number }) =>
    api.get<GrantRecord[]>('/subnet-grants', { params }).then(r => r.data),
  create: (body: {
    user_id?: number; group_id?: number; subnet_id: number; permission: 'view' | 'manage'
  }) => api.post<GrantRecord>('/subnet-grants', body).then(r => r.data),
  remove: (id: number) => api.delete(`/subnet-grants/${id}`),
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
  request_eligible?: boolean
  custom_fields?: Record<string, string>
  tags?: string[]
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
  custom_fields?: Record<string, string>
  tags?: string[]
}

export interface CustomFieldDef {
  id: number
  entity_type: 'subnet' | 'address'
  name: string
  label: string
  field_type: 'text' | 'select' | 'date'
  options: string[] | null
}

export interface TagRecord {
  id: number
  name: string
  usage_count: number
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

export interface SubnetForecast {
  subnet_id: number
  cidr: string
  name: string
  slope_per_day: number
  current_used: number
  total_count: number
  data_points: number
  warn_pct: number
  critical_pct: number
  days_to_warn: number | null
  days_to_critical: number | null
  projected_warn_date: string | null
  projected_critical_date: string | null
  confidence: 'none' | 'low' | 'medium' | 'high'
}

export const subnetsApi = {
  list: () => api.get<Subnet[]>('/subnets').then(r => r.data),
  forecast: (id: number) => api.get<SubnetForecast>(`/subnets/${id}/forecast`).then(r => r.data),
  forecasts: (limit = 5) =>
    api.get<SubnetForecast[]>('/subnets/forecasts', { params: { limit } }).then(r => r.data),
  create: (data: Omit<Subnet, 'id' | 'created_at' | 'notes' | 'used_count' | 'total_count' | 'utilization_pct' | 'rollup_used_count' | 'rollup_total_count' | 'rollup_utilization_pct' | 'parent_id' | 'scan_interval_minutes'> & { notes?: string | null; parent_id?: number | null; scan_interval_minutes?: number | null }) =>
    api.post<Subnet>('/subnets', data).then(r => r.data),
  update: (id: number, data: Partial<Omit<Subnet, 'id' | 'created_at' | 'used_count' | 'total_count' | 'utilization_pct' | 'rollup_used_count' | 'rollup_total_count' | 'rollup_utilization_pct'>>) =>
    api.put<Subnet>(`/subnets/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/subnets/${id}`),
  suggestParent: (cidr: string) =>
    api.get<Subnet[]>('/subnets/suggest-parent', { params: { cidr } }).then(r => r.data),
  listFiltered: (params: Record<string, string>) =>
    api.get<Subnet[]>('/subnets', { params }).then(r => r.data),
}

export const customFieldsApi = {
  list: (entity_type?: 'subnet' | 'address') =>
    api.get<CustomFieldDef[]>('/custom-fields', { params: entity_type ? { entity_type } : {} }).then(r => r.data),
  create: (body: Omit<CustomFieldDef, 'id'>) =>
    api.post<CustomFieldDef>('/custom-fields', body).then(r => r.data),
  remove: (id: number) => api.delete(`/custom-fields/${id}`),
}

export const tagsApi = {
  list: () => api.get<TagRecord[]>('/tags').then(r => r.data),
  create: (name: string) => api.post<TagRecord>('/tags', { name }).then(r => r.data),
  remove: (id: number) => api.delete(`/tags/${id}`),
}

export const addressesApi = {
  list: (params?: { subnet_id?: number; status?: string; tag?: string }) =>
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
  createRecord: (zone: string, data: Omit<DNSRecord, 'zone'> & { register_ptr?: boolean }) =>
    api.post<DNSRecord>(`/dns/zones/${zone}/records`, data).then(r => r.data),
  deleteRecord: (zone: string, record: DNSRecord, opts?: { delete_ptr?: boolean }) =>
    api.delete(`/dns/zones/${zone}/records`, { data: { ...record, ...opts } }),
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

export interface AlertChannel {
  id: number
  name: string
  kind: 'smtp' | 'generic' | 'slack' | 'teams' | 'pagerduty'
  config: Record<string, any>
  has_secret: boolean
  enabled: boolean
}

export interface AlertChannelIn {
  name: string
  kind: AlertChannel['kind']
  config: Record<string, any>
  secret?: string | null
  enabled: boolean
}

export const alertChannelsApi = {
  list:   ()                                 => api.get<AlertChannel[]>('/alerts/channels').then(r => r.data),
  create: (body: AlertChannelIn)             => api.post<AlertChannel>('/alerts/channels', body).then(r => r.data),
  update: (id: number, body: AlertChannelIn) => api.put<AlertChannel>(`/alerts/channels/${id}`, body).then(r => r.data),
  delete: (id: number)                       => api.delete(`/alerts/channels/${id}`),
  test:   (id: number)                       => api.post<{ status: string; error?: string }>(`/alerts/channels/${id}/test`).then(r => r.data),
}

export interface AlertRule {
  id: number
  name: string
  trigger_type: 'collision' | 'utilization' | 'rogue' | 'sync_error' | 'stale_queue' | 'ip_request_submitted' | 'ip_request_resolved'
  condition: Record<string, any>
  channel_ids: number[]
  recipients: string[]
  renotify_minutes: number | null
  enabled: boolean
}

export interface AlertRuleIn {
  name: string
  trigger_type: AlertRule['trigger_type']
  condition: Record<string, any>
  channel_ids: number[]
  recipients: string[]
  renotify_minutes: number | null
  enabled: boolean
}

export const alertRulesApi = {
  list:   ()                                 => api.get<AlertRule[]>('/alerts/rules').then(r => r.data),
  create: (body: AlertRuleIn)                => api.post<AlertRule>('/alerts/rules', body).then(r => r.data),
  update: (id: number, body: AlertRuleIn)    => api.put<AlertRule>(`/alerts/rules/${id}`, body).then(r => r.data),
  delete: (id: number)                       => api.delete(`/alerts/rules/${id}`),
}

export interface AlertingEvent {
  id: number
  rule_id: number | null
  resource_key: string
  state: 'firing' | 'resolved'
  first_fired_at: string
  last_fired_at: string
  resolved_at: string | null
  payload: Record<string, any>
  deliveries: {
    channel_id: number
    status: string
    error?: string | null
    attempted_at: string
  }[]
}

export const alertEventsApi = {
  list: (params: { state?: string; trigger_type?: string; limit?: number } = {}) =>
    api.get<AlertingEvent[]>('/alerts/events', { params }).then(r => r.data),
  ack: (id: number) =>
    api.post<AlertingEvent>(`/alerts/events/${id}/ack`).then(r => r.data),
}

export interface IPRequest {
  id: number
  requester_username: string
  subnet_id: number | null
  subnet_cidr: string | null
  hostname: string
  mac_address: string | null
  purpose: string
  status: 'pending' | 'approved' | 'denied'
  reviewer_username: string | null
  reviewed_at: string | null
  review_notes: string | null
  allocated_ip: string | null
  created_at: string
  updated_at: string
}

export interface IPRequestIn {
  subnet_id: number
  hostname: string
  mac_address?: string | null
  purpose: string
}

export interface EligibleSubnet {
  id: number
  cidr: string
  name: string | null
  description: string | null
}

export interface ApproveIn {
  description?: string
  register_dns: boolean
  register_dhcp: boolean
  dns_zone?: string
  dns_provider?: string
  dhcp_provider?: string
  register_ptr: boolean
}

export const ipRequestsApi = {
  list:    (status?: string)             => api.get<IPRequest[]>('/requests', { params: { status } }).then(r => r.data),
  get:     (id: number)                  => api.get<IPRequest>(`/requests/${id}`).then(r => r.data),
  submit:  (body: IPRequestIn)           => api.post<IPRequest>('/requests', body).then(r => r.data),
  approve: (id: number, body: ApproveIn) => api.put<IPRequest>(`/requests/${id}/approve`, body).then(r => r.data),
  deny:    (id: number, review_notes: string) => api.put<IPRequest>(`/requests/${id}/deny`, { review_notes }).then(r => r.data),
  delete:  (id: number)                  => api.delete(`/requests/${id}`),
  eligibleSubnets: () => api.get<EligibleSubnet[]>('/requests/eligible-subnets').then(r => r.data),
}

export interface Vlan {
  id: number
  vlan_id: number
  name: string
  description: string | null
  notes: string | null
  subnet_count: number
  created_at: string | null
  updated_at: string | null
}

export interface VlanIn {
  vlan_id: number
  name: string
  description?: string | null
  notes?: string | null
}

export const vlansApi = {
  list:   ()                                  => api.get<Vlan[]>('/vlans').then(r => r.data),
  get:    (id: number)                        => api.get<Vlan>(`/vlans/${id}`).then(r => r.data),
  create: (body: VlanIn)                      => api.post<Vlan>('/vlans', body).then(r => r.data),
  update: (id: number, body: Partial<VlanIn>) => api.put<Vlan>(`/vlans/${id}`, body).then(r => r.data),
  delete: (id: number)                        => api.delete(`/vlans/${id}`),
}
