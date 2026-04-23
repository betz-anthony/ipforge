import { Routes, Route, NavLink } from 'react-router-dom'
import Dashboard from './pages/Dashboard'
import Subnets from './pages/Subnets'
import Addresses from './pages/Addresses'
import DHCP from './pages/DHCP'
import DNS from './pages/DNS'
import Search from './pages/Search'
import Settings from './pages/Settings'

export default function App() {
  return (
    <div>
      <nav>
        <NavLink to="/" end>Home</NavLink>
        <NavLink to="/subnets">Subnets</NavLink>
        <NavLink to="/addresses">Addresses</NavLink>
        <NavLink to="/dhcp">DHCP</NavLink>
        <NavLink to="/dns">DNS</NavLink>
        <NavLink to="/search">Search</NavLink>
        <NavLink to="/settings">Settings</NavLink>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Dashboard />} />
          <Route path="/subnets" element={<Subnets />} />
          <Route path="/addresses" element={<Addresses />} />
          <Route path="/dhcp" element={<DHCP />} />
          <Route path="/dns" element={<DNS />} />
          <Route path="/search" element={<Search />} />
          <Route path="/settings" element={<Settings />} />
        </Routes>
      </main>
    </div>
  )
}
