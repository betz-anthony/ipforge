import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export interface Subnet {
  id: number
  name: string
  cidr: string
  ip_version: 4 | 6
  vlan_id: number | null
  description: string | null
  notes: string | null
  created_at: string
  used_count: number
  total_count: number
  utilization_pct: number
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
}

export const subnetsApi = {
  list: () => api.get<Subnet[]>('/subnets').then(r => r.data),
  create: (data: Omit<Subnet, 'id' | 'created_at' | 'notes' | 'used_count' | 'total_count' | 'utilization_pct'> & { notes?: string | null }) =>
    api.post<Subnet>('/subnets', data).then(r => r.data),
  update: (id: number, data: Partial<Subnet>) =>
    api.put<Subnet>(`/subnets/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/subnets/${id}`),
}

export const addressesApi = {
  list: (params?: { subnet_id?: number; status?: string }) =>
    api.get<IPAddress[]>('/addresses', { params }).then(r => r.data),
  create: (data: Omit<IPAddress, 'id' | 'created_at' | 'updated_at' | 'notes'> & { notes?: string | null }) =>
    api.post<IPAddress>('/addresses', data).then(r => r.data),
  update: (id: number, data: Partial<IPAddress>) =>
    api.put<IPAddress>(`/addresses/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/addresses/${id}`),
  byIp: (address: string) =>
    api.get<IPAddress>(`/addresses/by-ip/${encodeURIComponent(address)}`).then(r => r.data),
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
}

export interface AppSettingsUpdate {
  util_warn_threshold?:     number
  util_critical_threshold?: number
  util_dashboard_top_n?:    number
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

export const providerConfigsApi = {
  list:   ()                                     => api.get<ProviderConfig[]>('/provider-configs').then(r => r.data),
  create: (data: ProviderConfigCreate)           => api.post<ProviderConfig>('/provider-configs', data).then(r => r.data),
  update: (id: number, data: ProviderConfigUpdate) => api.put<ProviderConfig>(`/provider-configs/${id}`, data).then(r => r.data),
  delete: (id: number)                           => api.delete(`/provider-configs/${id}`),
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
  detected_at: string
  resolved: boolean
  resolved_at: string | null
}

export const scanApi = {
  trigger: (subnet_id: number, body?: { start_ip?: string; end_ip?: string }) =>
    api.post<{ status: string }>(`/scan/subnets/${subnet_id}`, body ?? {}).then(r => r.data),
  status: (subnet_id: number) =>
    api.get<ScanStatus>(`/scan/subnets/${subnet_id}`).then(r => r.data),
  collisions: (params?: { resolved?: boolean; subnet_id?: number }) =>
    api.get<Collision[]>('/scan/collisions', { params }).then(r => r.data),
  resolveCollision: (id: number) =>
    api.put<{ id: number; resolved: boolean }>(`/scan/collisions/${id}/resolve`).then(r => r.data),
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
