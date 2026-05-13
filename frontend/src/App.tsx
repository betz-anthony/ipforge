import { Routes, Route, NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Network, List, Server, Globe, Search, Settings, LogOut
} from 'lucide-react'
import { useAuth } from './contexts/AuthContext'
import Dashboard from './pages/Dashboard'
import Subnets from './pages/Subnets'
import Addresses from './pages/Addresses'
import DHCP from './pages/DHCP'
import DNS from './pages/DNS'
import SearchPage from './pages/Search'
import SettingsPage from './pages/Settings'
import Login from './pages/Login'

const NAV = [
  { to: '/',          label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/subnets',   label: 'Subnets',   icon: Network },
  { to: '/addresses', label: 'Addresses', icon: List },
  { to: '/dhcp',      label: 'DHCP',      icon: Server },
  { to: '/dns',       label: 'DNS',       icon: Globe },
]

export default function App() {
  const { user, loading, logout } = useAuth()

  if (loading) return null
  if (!user)   return <Login />

  const isAdmin = user.role === 'admin'

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <Network size={18} />
          IPAM Forge
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, label, icon: Icon, end }) => (
            <NavLink key={to} to={to} end={end} className={({ isActive }) =>
              'nav-link' + (isActive ? ' active' : '')
            }>
              <Icon size={15} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}

          <div className="nav-divider" />

          <NavLink to="/search" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
            <Search size={15} strokeWidth={1.75} />
            Search
          </NavLink>

          {isAdmin && (
            <NavLink to="/settings" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <Settings size={15} strokeWidth={1.75} />
              Settings
            </NavLink>
          )}
        </nav>

        <div className="sidebar-footer" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
          <div style={{ flex: 1, minWidth: 0 }}>
            <div style={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', fontSize: '0.8rem' }}>
              {user.username}
            </div>
            <div style={{ fontSize: '0.65rem', color: 'var(--text-muted)', textTransform: 'capitalize' }}>
              {user.role}
            </div>
          </div>
          <button
            className="btn-ghost btn-sm"
            onClick={logout}
            title="Sign out"
            style={{ padding: '0.25rem', flexShrink: 0 }}
          >
            <LogOut size={14} />
          </button>
        </div>
      </aside>

      <main className="main">
        <Routes>
          <Route path="/"          element={<Dashboard />} />
          <Route path="/subnets"   element={<Subnets />} />
          <Route path="/addresses" element={<Addresses />} />
          <Route path="/dhcp"      element={<DHCP />} />
          <Route path="/dns"       element={<DNS />} />
          <Route path="/search"    element={<SearchPage />} />
          {isAdmin && <Route path="/settings" element={<SettingsPage />} />}
        </Routes>
      </main>
    </div>
  )
}
