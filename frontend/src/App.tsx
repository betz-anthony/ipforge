import { Routes, Route, NavLink } from 'react-router-dom'
import Subnets from './pages/Subnets'
import Addresses from './pages/Addresses'
import DHCP from './pages/DHCP'
import DNS from './pages/DNS'
import Search from './pages/Search'

export default function App() {
  return (
    <div>
      <nav>
        <NavLink to="/">Subnets</NavLink>
        <NavLink to="/addresses">Addresses</NavLink>
        <NavLink to="/dhcp">DHCP</NavLink>
        <NavLink to="/dns">DNS</NavLink>
        <NavLink to="/search">Search</NavLink>
      </nav>
      <main>
        <Routes>
          <Route path="/" element={<Subnets />} />
          <Route path="/addresses" element={<Addresses />} />
          <Route path="/dhcp" element={<DHCP />} />
          <Route path="/dns" element={<DNS />} />
          <Route path="/search" element={<Search />} />
        </Routes>
      </main>
    </div>
  )
}
