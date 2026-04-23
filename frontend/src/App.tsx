import { Routes, Route, NavLink } from 'react-router-dom'
import {
  LayoutDashboard, Network, List, Server, Globe, Search, Settings
} from 'lucide-react'
import Dashboard from './pages/Dashboard'
import Subnets from './pages/Subnets'
import Addresses from './pages/Addresses'
import DHCP from './pages/DHCP'
import DNS from './pages/DNS'
import SearchPage from './pages/Search'
import SettingsPage from './pages/Settings'

const NAV = [
  { to: '/',         label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/subnets',  label: 'Subnets',   icon: Network },
  { to: '/addresses',label: 'Addresses', icon: List },
  { to: '/dhcp',     label: 'DHCP',      icon: Server },
  { to: '/dns',      label: 'DNS',       icon: Globe },
]

const NAV_BOTTOM = [
  { to: '/search',   label: 'Search',    icon: Search },
  { to: '/settings', label: 'Settings',  icon: Settings },
]

export default function App() {
  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="sidebar-logo">
          <Network size={18} />
          IPAM<span className="sidebar-logo-dot">.app</span>
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

          {NAV_BOTTOM.map(({ to, label, icon: Icon }) => (
            <NavLink key={to} to={to} className={({ isActive }) =>
              'nav-link' + (isActive ? ' active' : '')
            }>
              <Icon size={15} strokeWidth={1.75} />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="sidebar-footer">
          IP Address Management
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
          <Route path="/settings"  element={<SettingsPage />} />
        </Routes>
      </main>
    </div>
  )
}
