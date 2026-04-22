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
