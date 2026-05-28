import { Fragment, useEffect, useState } from 'react'
import { Routes, Route, NavLink, useLocation } from 'react-router-dom'
import {
  LayoutDashboard, Network, List, Server, Globe, Search, Settings, LogOut, ClipboardList,
  ArchiveRestore, KeyRound, Users, Bell, Tag, Menu, Sun, Moon, Keyboard,
} from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAuth } from './contexts/AuthContext'
import { useTheme } from './contexts/ThemeContext'
import { useGlobalShortcuts, SHORTCUT_LIST } from './hooks/useGlobalShortcuts'
import { reclaimApi } from './api/client'
import Dashboard from './pages/Dashboard'
import Subnets from './pages/Subnets'
import Addresses from './pages/Addresses'
import DHCP from './pages/DHCP'
import DNS from './pages/DNS'
import SearchPage from './pages/Search'
import SettingsPage from './pages/Settings'
import AuditPage from './pages/Audit'
import AlertsPage from './pages/Alerts'
import ApiTokens from './pages/ApiTokens'
import ReclaimPage from './pages/Reclaim'
import Groups from './pages/Groups'
import Login from './pages/Login'
import Requests from './pages/Requests'
import Vlans from './pages/Vlans'

const NAV = [
  { to: '/',          label: 'Dashboard', icon: LayoutDashboard, end: true },
  { to: '/subnets',   label: 'Subnets',   icon: Network },
  { to: '/vlans',     label: 'VLANs',     icon: Tag },
  { to: '/addresses', label: 'Addresses', icon: List },
  { to: '/dhcp',      label: 'DHCP',      icon: Server },
  { to: '/dns',       label: 'DNS',       icon: Globe },
]

export default function App() {
  const { user, loading, logout } = useAuth()
  const { theme, toggle: toggleTheme } = useTheme()
  const { cheatsheetOpen, closeCheatsheet } = useGlobalShortcuts()
  const [mobileNavOpen, setMobileNavOpen] = useState(false)
  const location = useLocation()

  // Apply mobile-nav state to <body> so the CSS @media rule can react.
  useEffect(() => {
    if (mobileNavOpen) document.body.setAttribute('data-mobile-nav', 'open')
    else document.body.removeAttribute('data-mobile-nav')
  }, [mobileNavOpen])

  // Close mobile nav on every route change.
  useEffect(() => { setMobileNavOpen(false) }, [location.pathname])

  const { data: staleCount } = useQuery({
    queryKey: ['stale-count'],
    queryFn: reclaimApi.countStale,
    enabled: !!user && user.role !== 'readonly',
    refetchInterval: 5 * 60 * 1000,
  })

  if (loading) return null
  if (!user)   return <Login />

  const isAdmin    = user.role === 'admin'
  const isOperator = user.role !== 'readonly'
  const isScoped   = user.role === 'scoped'

  return (
    <div className="app-shell">
      <div className="mobile-topbar">
        <button
          className="mobile-topbar-burger"
          aria-label="Open navigation"
          onClick={() => setMobileNavOpen(o => !o)}
        >
          <Menu size={22} />
        </button>
        <span className="mobile-topbar-title">IPForge</span>
      </div>
      {mobileNavOpen && (
        <div
          className="mobile-nav-backdrop"
          onClick={() => setMobileNavOpen(false)}
          aria-hidden="true"
        />
      )}

      <aside className="sidebar">
        <div className="sidebar-logo">
          <Network size={18} />
          IPForge
        </div>

        <nav className="sidebar-nav">
          {NAV.map(({ to, label, icon: Icon, end }) => {
            const scopedHidden = isScoped && (to === '/' || to === '/dhcp' || to === '/dns')
            if (scopedHidden) return null
            return (
              <NavLink key={to} to={to} end={end} className={({ isActive }) =>
                'nav-link' + (isActive ? ' active' : '')
              }>
                <Icon size={15} strokeWidth={1.75} />
                {label}
              </NavLink>
            )
          })}

          <div className="nav-divider" />

          {!isScoped && (
            <NavLink to="/search" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <Search size={15} strokeWidth={1.75} />
              Search
            </NavLink>
          )}

          {!isScoped && (
            <NavLink to="/audit" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <ClipboardList size={15} strokeWidth={1.75} />
              Audit
            </NavLink>
          )}

          {!isScoped && (
            <NavLink to="/alerts" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <Bell size={15} strokeWidth={1.75} />
              Alerts
            </NavLink>
          )}

          {!isScoped && (
            <NavLink to="/requests" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <ClipboardList size={15} strokeWidth={1.75} />
              Requests
            </NavLink>
          )}

          <NavLink to="/tokens" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
            <KeyRound size={15} strokeWidth={1.75} />
            API Tokens
          </NavLink>

          {isOperator && !isScoped && (
            <NavLink to="/reclaim" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <ArchiveRestore size={15} strokeWidth={1.75} />
              Reclaim
              {staleCount && staleCount.count > 0 && (
                <span style={{
                  marginLeft: 'auto',
                  background: 'var(--warning, #f59e0b)',
                  color: '#000',
                  borderRadius: '9999px',
                  fontSize: '0.6rem',
                  fontWeight: 700,
                  padding: '0.05rem 0.35rem',
                  minWidth: '1.2rem',
                  textAlign: 'center',
                }}>
                  {staleCount.count > 99 ? '99+' : staleCount.count}
                </span>
              )}
            </NavLink>
          )}

          {isAdmin && (
            <NavLink to="/groups" className={({ isActive }) => 'nav-link' + (isActive ? ' active' : '')}>
              <Users size={15} strokeWidth={1.75} />
              Groups
            </NavLink>
          )}

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
            onClick={toggleTheme}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
            aria-label="Toggle theme"
            style={{ padding: '0.25rem', flexShrink: 0 }}
          >
            {theme === 'dark' ? <Sun size={14} /> : <Moon size={14} />}
          </button>
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
          <Route path="/"          element={isScoped ? <Subnets /> : <Dashboard />} />
          <Route path="/subnets"   element={<Subnets />} />
          <Route path="/vlans"     element={<Vlans />} />
          <Route path="/addresses" element={<Addresses />} />
          <Route path="/dhcp"      element={<DHCP />} />
          <Route path="/dns"       element={<DNS />} />
          <Route path="/search"    element={<SearchPage />} />
          <Route path="/audit"     element={<AuditPage />} />
          {!isScoped && <Route path="/alerts" element={<AlertsPage />} />}
          {!isScoped && <Route path="/requests" element={<Requests />} />}
          <Route path="/tokens"    element={<ApiTokens />} />
          {isOperator && <Route path="/reclaim" element={<ReclaimPage />} />}
          {isAdmin && <Route path="/groups" element={<Groups />} />}
          {isAdmin && <Route path="/settings" element={<SettingsPage />} />}
        </Routes>
      </main>

      {cheatsheetOpen && (
        <div className="modal-backdrop" onClick={closeCheatsheet}>
          <div className="modal" onClick={e => e.stopPropagation()}>
            <h2 className="modal-title" style={{ display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
              <Keyboard size={16} /> Keyboard Shortcuts
            </h2>
            <div className="shortcut-cheatsheet">
              {SHORTCUT_LIST.map(([key, desc]) => (
                <Fragment key={key}>
                  <span>
                    {key.split(' ').map((part, i, arr) => (
                      <Fragment key={i}>
                        <kbd>{part}</kbd>
                        {i < arr.length - 1 && <span style={{ margin: '0 0.25rem', color: 'var(--text-muted)' }}>then</span>}
                      </Fragment>
                    ))}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>{desc}</span>
                </Fragment>
              ))}
            </div>
            <div className="modal-actions">
              <button className="btn btn-ghost" onClick={closeCheatsheet}>Close</button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
