import axios from 'axios'

const api = axios.create({ baseURL: '/api' })

export interface Subnet {
  id: number
  name: string
  cidr: string
  ip_version: 4 | 6
  vlan_id: number | null
  description: string | null
  created_at: string
}

export interface IPAddress {
  id: number
  address: string
  subnet_id: number
  hostname: string | null
  status: 'available' | 'reserved' | 'assigned' | 'deprecated'
  mac_address: string | null
  description: string | null
  created_at: string
  updated_at: string
}

export const subnetsApi = {
  list: () => api.get<Subnet[]>('/subnets').then(r => r.data),
  create: (data: Omit<Subnet, 'id' | 'created_at'>) =>
    api.post<Subnet>('/subnets', data).then(r => r.data),
  update: (id: number, data: Partial<Subnet>) =>
    api.put<Subnet>(`/subnets/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/subnets/${id}`),
}

export const addressesApi = {
  list: (params?: { subnet_id?: number; status?: string }) =>
    api.get<IPAddress[]>('/addresses', { params }).then(r => r.data),
  create: (data: Omit<IPAddress, 'id' | 'created_at' | 'updated_at'>) =>
    api.post<IPAddress>('/addresses', data).then(r => r.data),
  update: (id: number, data: Partial<IPAddress>) =>
    api.put<IPAddress>(`/addresses/${id}`, data).then(r => r.data),
  delete: (id: number) => api.delete(`/addresses/${id}`),
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
  synced_at?: string | null
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
}

export const providersApi = {
  get: () => api.get<{ dns: string[]; dhcp: string[] }>('/providers').then(r => r.data),
}

export const dnsApi = {
  listZones: () => api.get<string[]>('/dns/zones').then(r => r.data),
  listRecords: (zone: string) =>
    api.get<DNSRecord[]>(`/dns/zones/${zone}/records`).then(r => r.data),
  createRecord: (zone: string, data: Omit<DNSRecord, 'zone'>) =>
    api.post<DNSRecord>(`/dns/zones/${zone}/records`, data).then(r => r.data),
  deleteRecord: (zone: string, record: DNSRecord) =>
    api.delete(`/dns/zones/${zone}/records`, { data: record }),
}

export interface AppSettings {
  dns_provider: string
  dhcp_provider: string
  // MS
  ms_winrm_host: string
  ms_winrm_user: string
  ms_winrm_password_set: boolean
  ms_winrm_port: number
  ms_winrm_transport: string
  ms_dns_server: string
  ms_dhcp_server: string
  // Pi-hole
  pihole_url: string
  pihole_password_set: boolean
  // BIND
  bind_host: string
  bind_port: number
  bind_tsig_key_name: string
  bind_tsig_key_secret_set: boolean
  bind_tsig_algorithm: string
  bind_zones: string
  // Kea
  kea_url: string
  kea_secret_set: boolean
}

export interface AppSettingsUpdate {
  dns_provider?: string
  dhcp_provider?: string
  // MS
  ms_winrm_host?: string
  ms_winrm_user?: string
  ms_winrm_password?: string
  ms_winrm_port?: number
  ms_winrm_transport?: string
  ms_dns_server?: string
  ms_dhcp_server?: string
  // Pi-hole
  pihole_url?: string
  pihole_password?: string
  // BIND
  bind_host?: string
  bind_port?: number
  bind_tsig_key_name?: string
  bind_tsig_key_secret?: string
  bind_tsig_algorithm?: string
  bind_zones?: string
  // Kea
  kea_url?: string
  kea_secret?: string
}

export const settingsApi = {
  get: () => api.get<AppSettings>('/settings').then(r => r.data),
  update: (data: AppSettingsUpdate) => api.put<AppSettings>('/settings', data).then(r => r.data),
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
